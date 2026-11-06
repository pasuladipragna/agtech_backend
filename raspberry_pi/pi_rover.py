"""
Smart AgriTech Rover - Raspberry Pi Client
============================================
Deploy this file on your Raspberry Pi.
It connects to the AgriTech backend via MQTT and controls real GPIO hardware.

Wiring Reference (BCM numbering):
  Motor Driver L298N:
    Left  Motor: ENA=PWM(12), IN1=20, IN2=21
    Right Motor: ENB=PWM(13), IN3=23, IN4=24

  Spray System:
    Pump relay:     GPIO 25
    Solenoid relay: GPIO 8
    Nozzle servo:   GPIO 18 (hardware PWM)

  Camera: Raspberry Pi Camera Module V2 (CSI port)
  GPS: NEO-6M via UART - install gpsd: sudo apt install gpsd gpsd-clients python3-gps
  Battery INA219 (I2C 0x40): SCL=GPIO3, SDA=GPIO2

Run on Pi:
  pip install paho-mqtt RPi.GPIO pigpio Pillow gps pi-ina219 picamera2
  sudo pigpiod
  python3 pi_rover.py
"""
import os, sys, json, time, logging, threading, base64, io
from datetime import datetime, timezone
from typing import Optional
import paho.mqtt.client as mqtt

logging.basicConfig(level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout), logging.FileHandler("pi_rover.log")])
logger = logging.getLogger("PiRover")

ROVER_ID       = os.getenv("ROVER_ID", "ROVER-4WD-01")
MQTT_BROKER    = os.getenv("ROVER_MQTT_BROKER", "192.168.0.109")
MQTT_PORT      = int(os.getenv("ROVER_MQTT_PORT", "1883"))
MQTT_PREFIX    = os.getenv("MQTT_TOPIC_PREFIX", "agritech/rover")
TELEMETRY_HZ   = float(os.getenv("TELEMETRY_HZ", "2"))
CAMERA_ENABLED = os.getenv("CAMERA_ENABLED", "true").lower() == "true"
GPS_ENABLED    = os.getenv("GPS_ENABLED", "false").lower() == "true"
INA219_ENABLED = os.getenv("INA219_ENABLED", "false").lower() == "true"
SIMULATE_HW    = os.getenv("SIMULATE_HARDWARE", "false").lower() == "true"

PIN_MOTOR_ENA=12; PIN_MOTOR_IN1=20; PIN_MOTOR_IN2=21
PIN_MOTOR_ENB=13; PIN_MOTOR_IN3=23; PIN_MOTOR_IN4=24
PIN_PUMP_RELAY=25; PIN_SOLENOID=8; PIN_NOZZLE_SRV=18

class SimGPIO:
    BCM="BCM"; OUT="OUT"; IN="IN"; HIGH=True; LOW=False
    def setmode(self,m): pass
    def setwarnings(self,v): pass
    def setup(self,p,m,initial=None): pass
    def output(self,p,v): logger.debug(f"[SIM GPIO] pin={p} val={v}")
    def cleanup(self): pass

class SimPigpio:
    def __init__(self): self._d={}
    def connected(self): return True
    def set_mode(self,p,m): pass
    def set_PWM_frequency(self,p,f): pass
    def set_PWM_dutycycle(self,p,d): logger.debug(f"[SIM PWM] pin={p} dc={d}")
    def set_servo_pulsewidth(self,p,w): logger.debug(f"[SIM SERVO] pin={p} pw={w}")
    def stop(self): pass

def _load_gpio():
    if SIMULATE_HW: return SimGPIO()
    try:
        import RPi.GPIO as G; return G
    except ImportError:
        logger.warning("RPi.GPIO not found - simulation mode"); return SimGPIO()

def _load_pigpio():
    if SIMULATE_HW: return SimPigpio()
    try:
        import pigpio; pi=pigpio.pi()
        if not pi.connected: logger.warning("pigpio daemon not running - start: sudo pigpiod"); return SimPigpio()
        return pi
    except ImportError:
        logger.warning("pigpio not installed - simulation mode"); return SimPigpio()

class MotorController:
    PIGPIO_FREQ=20000
    def __init__(self, gpio, pi):
        self.gpio=gpio; self.pi=pi; self.left_pct=0.0; self.right_pct=0.0
        for p in [PIN_MOTOR_IN1,PIN_MOTOR_IN2,PIN_MOTOR_IN3,PIN_MOTOR_IN4]:
            gpio.setup(p, gpio.OUT, initial=gpio.LOW)
        for p in [PIN_MOTOR_ENA, PIN_MOTOR_ENB]:
            pi.set_mode(p,1); pi.set_PWM_frequency(p,self.PIGPIO_FREQ); pi.set_PWM_dutycycle(p,0)
    def set_motors(self, L, R):
        self.left_pct=max(-100.0,min(100.0,L)); self.right_pct=max(-100.0,min(100.0,R))
        for pct,in1,in2 in [(self.left_pct,PIN_MOTOR_IN1,PIN_MOTOR_IN2),(self.right_pct,PIN_MOTOR_IN3,PIN_MOTOR_IN4)]:
            if pct>0: self.gpio.output(in1,self.gpio.HIGH); self.gpio.output(in2,self.gpio.LOW)
            elif pct<0: self.gpio.output(in1,self.gpio.LOW); self.gpio.output(in2,self.gpio.HIGH)
            else: self.gpio.output(in1,self.gpio.LOW); self.gpio.output(in2,self.gpio.LOW)
        self.pi.set_PWM_dutycycle(PIN_MOTOR_ENA, int(abs(self.left_pct)/100*255))
        self.pi.set_PWM_dutycycle(PIN_MOTOR_ENB, int(abs(self.right_pct)/100*255))
        logger.info(f"[MOTOR] L={self.left_pct:.0f}% R={self.right_pct:.0f}%")
    def stop(self): self.set_motors(0,0)

class SprayController:
    SMID=1500; SRANGE=45.0
    def __init__(self, gpio, pi):
        self.gpio=gpio; self.pi=pi; self.pump_active=False; self.solenoid_open=False
        self.nozzle_angle=0.0; self.tank_liters=25.0
        gpio.setup(PIN_PUMP_RELAY, gpio.OUT, initial=gpio.LOW)
        gpio.setup(PIN_SOLENOID, gpio.OUT, initial=gpio.LOW)
        pi.set_mode(PIN_NOZZLE_SRV,1); pi.set_servo_pulsewidth(PIN_NOZZLE_SRV,1500)
    def start_pump(self):
        self.pump_active=True; self.gpio.output(PIN_PUMP_RELAY,self.gpio.HIGH); logger.info("[SPRAY] Pump ON")
    def stop_pump(self):
        self.pump_active=False; self.solenoid_open=False
        self.gpio.output(PIN_PUMP_RELAY,self.gpio.LOW); self.gpio.output(PIN_SOLENOID,self.gpio.LOW)
        logger.info("[SPRAY] Pump OFF")
    def pulse_solenoid(self, ms=500):
        self.solenoid_open=True; self.gpio.output(PIN_SOLENOID,self.gpio.HIGH)
        if self.tank_liters>0.05: self.tank_liters-=0.05
        def close():
            if not self.pump_active: self.solenoid_open=False; self.gpio.output(PIN_SOLENOID,self.gpio.LOW)
        threading.Timer(ms/1000.0, close).start()
    def set_nozzle(self, angle):
        self.nozzle_angle=max(-45.0,min(45.0,angle))
        pw=self.SMID+int((self.nozzle_angle/self.SRANGE)*1000); self.pi.set_servo_pulsewidth(PIN_NOZZLE_SRV,pw)

class GPSReader:
    def __init__(self):
        self.lat=0.0; self.lng=0.0; self.speed_kmh=0.0; self.fix=False
        threading.Thread(target=self._run, daemon=True).start()
    def _run(self):
        try:
            import gps as gpsd; s=gpsd.gps(mode=gpsd.WATCH_ENABLE|gpsd.WATCH_NEWSTYLE)
            for r in s:
                if r["class"]=="TPV":
                    self.lat=getattr(r,"lat",0.0) or 0.0; self.lng=getattr(r,"lon",0.0) or 0.0
                    self.speed_kmh=round((getattr(r,"speed",0.0) or 0.0)*3.6,2); self.fix=self.lat!=0.0
        except Exception as e: logger.warning(f"[GPS] {e}")

class BatteryReader:
    def __init__(self):
        self.voltage=25.6; self.battery_pct=100.0; self._ina=None
        try:
            from ina219 import INA219; self._ina=INA219(0.1,address=0x40); self._ina.configure()
            logger.info("[BATTERY] INA219 initialized")
        except Exception as e: logger.warning(f"[BATTERY] {e}")
    def read(self):
        if self._ina is None: return self.voltage, self.battery_pct
        try:
            self.voltage=round(self._ina.voltage(),2)
            self.battery_pct=round(max(0.0,min(100.0,(self.voltage-21.0)/(28.8-21.0)*100.0)),1)
        except: pass
        return self.voltage, self.battery_pct

class PiCamera:
    def __init__(self):
        self._cam=None; self._lock=threading.Lock()
        try:
            from picamera2 import Picamera2; self._cam=Picamera2()
            self._cam.configure(self._cam.create_still_configuration(main={"size":(640,480)}))
            self._cam.start(); time.sleep(1); logger.info("[CAMERA] PiCamera2 initialized")
        except Exception as e: logger.warning(f"[CAMERA] {e}")
    def capture_b64(self):
        if not self._cam: return None
        try:
            with self._lock:
                from PIL import Image; arr=self._cam.capture_array()
                buf=io.BytesIO(); Image.fromarray(arr).save(buf,"JPEG",quality=70)
                return "data:image/jpeg;base64,"+base64.b64encode(buf.getvalue()).decode()
        except: return None
    def stop(self):
        if self._cam:
            try: self._cam.stop()
            except: pass

class PiRoverClient:
    def __init__(self):
        logger.info(f"=== Pi Rover Client starting - ID: {ROVER_ID} ===")
        self.gpio=_load_gpio(); self.gpio.setmode(self.gpio.BCM); self.gpio.setwarnings(False)
        self.pi=_load_pigpio()
        self.motors=MotorController(self.gpio,self.pi)
        self.spray=SprayController(self.gpio,self.pi)
        self.battery=BatteryReader() if INA219_ENABLED else None
        self.gps=GPSReader() if GPS_ENABLED else None
        self.camera=PiCamera() if CAMERA_ENABLED else None
        self._lat=17.3850; self._lng=78.4867; self._heading=0.0; self._speed_kmh=0.0
        self._rover_status="IDLE"; self._mode="MANUAL"
        self._cmd=f"{MQTT_PREFIX}/{ROVER_ID}/command"; self._tel=f"{MQTT_PREFIX}/{ROVER_ID}/telemetry"
        self._cam=f"{MQTT_PREFIX}/{ROVER_ID}/camera"; self._evt=f"{MQTT_PREFIX}/{ROVER_ID}/events"
        self.client=mqtt.Client(client_id=f"PiRover-{ROVER_ID}")
        self.client.on_connect=self._on_connect; self.client.on_disconnect=self._on_disconnect
        self.client.on_message=self._on_message
        self._running=False; self._tel_int=1.0/TELEMETRY_HZ; self._cam_int=5.0
        self._last_tel=0.0; self._last_cam=0.0

    def _on_connect(self,c,u,f,rc):
        if rc==0:
            logger.info(f"[MQTT] Connected to {MQTT_BROKER}:{MQTT_PORT}")
            c.subscribe(self._cmd,qos=1); self._pub_evt("ONLINE",{"firmware":"pi_rover.py v1.0"})
        else: logger.error(f"[MQTT] Connection failed rc={rc}")

    def _on_disconnect(self,c,u,rc): logger.warning(f"[MQTT] Disconnected rc={rc}")

    def _on_message(self,c,u,msg):
        try:
            p=json.loads(msg.payload.decode()); cmd=p.get("command","").upper(); params=p.get("params",{})
            logger.info(f"[CMD] {cmd} params={params}"); self._execute(cmd,params)
        except Exception as e: logger.error(f"[CMD] parse error: {e}")

    def _execute(self, cmd, params):
        sp=float(params.get("speed_pct",params.get("speed",60)))
        if cmd=="MOVE_FORWARD": self.motors.set_motors(sp,sp); self._speed_kmh=sp/100*4.5; self._rover_status="MOVING"
        elif cmd=="MOVE_BACKWARD": self.motors.set_motors(-sp,-sp); self._speed_kmh=-sp/100*3.0; self._rover_status="MOVING"
        elif cmd=="TURN_LEFT": self.motors.set_motors(-35,35); self._heading=(self._heading-15)%360; self._rover_status="MOVING"
        elif cmd=="TURN_RIGHT": self.motors.set_motors(35,-35); self._heading=(self._heading+15)%360; self._rover_status="MOVING"
        elif cmd=="STOP": self.motors.stop(); self._speed_kmh=0.0; self._rover_status="IDLE"
        elif cmd=="EMERGENCY_STOP":
            self.motors.stop(); self.spray.stop_pump(); self._speed_kmh=0.0; self._rover_status="EMERGENCY_STOP"
            logger.critical("[CMD] *** EMERGENCY STOP ***"); self._pub_evt("EMERGENCY_STOP",{"triggered_by":"remote_command"})
        elif cmd=="START_SPRAYING": self.spray.start_pump(); self.spray.pulse_solenoid(int(params.get("pulse_ms",500))); self._rover_status="SPRAYING"
        elif cmd=="STOP_SPRAYING": self.spray.stop_pump(); self._rover_status="IDLE"
        elif cmd=="ROTATE_NOZZLE": self.spray.set_nozzle(float(params.get("angle_deg",0.0)))
        elif cmd=="RETURN_HOME": self.motors.stop(); self._rover_status="IDLE"
        elif cmd=="SET_MODE": self._mode=params.get("mode","MANUAL").upper()
        else: logger.warning(f"[CMD] Unknown: {cmd}")
        self._publish_telemetry()

    def _telemetry_data(self):
        v,b=(self.battery.read() if self.battery else (25.6,97.0))
        lat,lng=(self.gps.lat,self.gps.lng) if (self.gps and self.gps.fix) else (self._lat,self._lng)
        spd=(self.gps.speed_kmh if (self.gps and self.gps.fix) else abs(self._speed_kmh))
        return {"rover_id":ROVER_ID,"rover_status":self._rover_status,"speed_kmh":round(spd,2),
            "battery_pct":round(b,1),"voltage":round(v,2),"spray_tank_liters":round(self.spray.tank_liters,2),
            "spray_tank_pct":round(self.spray.tank_liters/25*100,1),"pump_active":self.spray.pump_active,
            "solenoid_open":self.spray.solenoid_open,"nozzle_angle_deg":self.spray.nozzle_angle,
            "latitude":round(lat,6),"longitude":round(lng,6),"heading_deg":round(self._heading,1),
            "left_motor_pwm":self.motors.left_pct,"right_motor_pwm":self.motors.right_pct,"mode":self._mode,
            "camera_active":self.camera is not None and self.camera._cam is not None,
            "gps_available":self.gps is not None and self.gps.fix,"imu_available":False,
            "spraying":self.spray.pump_active,"timestamp":datetime.now(timezone.utc).isoformat()}

    def _publish_telemetry(self):
        tel=self._telemetry_data()
        self.client.publish(self._tel,json.dumps({"rover_id":ROVER_ID,"timestamp":tel["timestamp"],"data":tel}),qos=0)

    def _pub_evt(self, ev, details):
        self.client.publish(self._evt,json.dumps({"rover_id":ROVER_ID,"event":ev,
            "timestamp":datetime.now(timezone.utc).isoformat(),"details":details}),qos=1)

    def _publish_camera(self):
        if not self.camera: return
        frame=self.camera.capture_b64()
        if not frame: return
        self.client.publish(self._cam,json.dumps({"rover_id":ROVER_ID,
            "timestamp":datetime.now(timezone.utc).isoformat(),"frame":frame}),qos=0)

    def run(self):
        logger.info(f"[MQTT] Connecting to {MQTT_BROKER}:{MQTT_PORT} ...")
        try: self.client.connect(MQTT_BROKER,MQTT_PORT,keepalive=60)
        except Exception as e:
            logger.error(f"[MQTT] Cannot connect: {e}"); logger.error("Set ROVER_MQTT_BROKER to your server LAN IP"); sys.exit(1)
        self.client.loop_start(); self._running=True
        logger.info("=== Pi Rover Client running - Ctrl+C to stop ===")
        try:
            while self._running:
                now=time.time()
                if now-self._last_tel>=self._tel_int: self._publish_telemetry(); self._last_tel=now
                if now-self._last_cam>=self._cam_int: self._publish_camera(); self._last_cam=now
                time.sleep(0.05)
        except KeyboardInterrupt: logger.info("Shutdown via Ctrl+C")
        finally: self._shutdown()

    def _shutdown(self):
        logger.info("[SHUTDOWN] Stopping rover ..."); self._running=False
        try:
            self.motors.stop(); self.spray.stop_pump()
            if self.camera: self.camera.stop()
            self._pub_evt("OFFLINE",{"reason":"graceful_shutdown"}); time.sleep(0.5)
            self.client.loop_stop(); self.client.disconnect(); self.pi.stop(); self.gpio.cleanup()
        except Exception as e: logger.error(f"[SHUTDOWN] {e}")
        logger.info("[SHUTDOWN] Done.")

if __name__=="__main__":
    client=PiRoverClient(); client.run()
