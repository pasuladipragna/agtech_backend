import time
import logging
import math
from typing import Dict, Any, Optional

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("RoverHAL")

class MotorDriverHAL:
    def __init__(self):
        self.left_speed = 0
        self.right_speed = 0
        self.is_moving = False

    def set_motors(self, left_pct: float, right_pct: float):
        self.left_speed = max(-100.0, min(100.0, left_pct))
        self.right_speed = max(-100.0, min(100.0, right_pct))
        self.is_moving = (self.left_speed != 0 or self.right_speed != 0)
        logger.info(f"[HAL] Motor PWM Set -> Left: {self.left_speed}%, Right: {self.right_speed}%")

    def stop(self):
        self.set_motors(0, 0)
        logger.info("[HAL] Motor Stop Activated")


class SpraySystemHAL:
    def __init__(self, capacity_liters: float = 25.0):
        self.capacity_liters = capacity_liters
        self.current_liters = capacity_liters
        self.pump_active = False
        self.solenoid_open = False
        self.nozzle_angle_deg = 0.0

    def start_pump(self):
        self.pump_active = True
        logger.info("[HAL] DC Spraying Pump -> ON")

    def stop_pump(self):
        self.pump_active = False
        self.solenoid_open = False
        logger.info("[HAL] DC Spraying Pump -> OFF")

    def pulse_solenoid(self, open_duration_ms: int = 500):
        self.solenoid_open = True
        logger.info(f"[HAL] Solenoid Valve OPEN ({open_duration_ms} ms)")
        if self.current_liters > 0.05:
            self.current_liters -= 0.05

    def set_nozzle_angle(self, angle: float):
        self.nozzle_angle_deg = max(-45.0, min(45.0, angle))
        logger.info(f"[HAL] Rotatable Nozzle Servo -> {self.nozzle_angle_deg}°")


class CameraMountHAL:
    def __init__(self, min_height_cm: float = 50.0, max_height_cm: float = 180.0):
        self.min_height = min_height_cm
        self.max_height = max_height_cm
        self.current_height_cm = 100.0

    def adjust_height(self, target_height_cm: float):
        self.current_height_cm = max(self.min_height, min(self.max_height, target_height_cm))
        logger.info(f"[HAL] Camera Height Linear Actuator -> {self.current_height_cm} cm")


class BatteryAndPowerHAL:
    def __init__(self, nominal_voltage: float = 25.6):
        self.battery_pct = 95.0
        self.voltage = nominal_voltage
        self.solar_charging_current = 2.4

    def update_telemetry(self, is_moving: bool, pump_active: bool):
        drain = 0.02 if is_moving else 0.005
        if pump_active:
            drain += 0.03
        recharge = 0.01
        net_change = recharge - drain
        self.battery_pct = max(5.0, min(100.0, self.battery_pct + net_change))
        self.voltage = 21.0 + (self.battery_pct / 100.0) * (28.8 - 21.0)


class RoverHAL:
    def __init__(self):
        self.motors = MotorDriverHAL()
        self.spray = SpraySystemHAL()
        self.camera_mount = CameraMountHAL()
        self.power = BatteryAndPowerHAL()
        
        self.latitude = 36.778259
        self.longitude = -119.417931
        self.heading_deg = 45.0
        self.speed_kmh = 0.0

    def execute_high_level_command(self, cmd: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        cmd = cmd.upper()
        params = params or {}
        
        if cmd == "MOVE_FORWARD":
            speed = params.get("speed_pct", 60.0)
            self.motors.set_motors(speed, speed)
            self.speed_kmh = (speed / 100.0) * 4.5
        elif cmd == "MOVE_BACKWARD":
            speed = params.get("speed_pct", 40.0)
            self.motors.set_motors(-speed, -speed)
            self.speed_kmh = -(speed / 100.0) * 3.0
        elif cmd == "TURN_LEFT":
            self.motors.set_motors(-35.0, 35.0)
            self.heading_deg = (self.heading_deg - 15.0) % 360
        elif cmd == "TURN_RIGHT":
            self.motors.set_motors(35.0, -35.0)
            self.heading_deg = (self.heading_deg + 15.0) % 360
        elif cmd == "STOP":
            self.motors.stop()
            self.speed_kmh = 0.0
        elif cmd == "START_SPRAYING":
            self.spray.start_pump()
            self.spray.pulse_solenoid(params.get("pulse_ms", 500))
        elif cmd == "STOP_SPRAYING":
            self.spray.stop_pump()
        elif cmd == "RAISE_CAMERA":
            self.camera_mount.adjust_height(self.camera_mount.current_height_cm + 15.0)
        elif cmd == "LOWER_CAMERA":
            self.camera_mount.adjust_height(self.camera_mount.current_height_cm - 15.0)
        elif cmd == "ROTATE_NOZZLE":
            angle = params.get("angle_deg", 0.0)
            self.spray.set_nozzle_angle(angle)
        elif cmd == "EMERGENCY_STOP":
            self.motors.stop()
            self.spray.stop_pump()
            self.speed_kmh = 0.0
            logger.critical("[HAL] EMERGENCY STOP TRIGGERED!")
            return {"status": "EMERGENCY_STOPPED", "success": True}
        else:
            logger.warning(f"[HAL] Unknown command: {cmd}")
            return {"status": "UNKNOWN_COMMAND", "success": False}

        return {"status": "EXECUTED", "command": cmd, "success": True}

    def read_sensors(self) -> Dict[str, Any]:
        self.power.update_telemetry(self.motors.is_moving, self.spray.pump_active)
        if self.motors.is_moving and self.speed_kmh != 0:
            rad = math.radians(self.heading_deg)
            dist_delta = (self.speed_kmh / 3600.0) * 1.0
            self.latitude += (dist_delta * math.cos(rad)) / 111.0
            self.longitude += (dist_delta * math.sin(rad)) / (111.0 * math.cos(math.radians(self.latitude)))

        return {
            "battery_pct": round(self.power.battery_pct, 1),
            "voltage": round(self.power.voltage, 2),
            "spray_tank_liters": round(self.spray.current_liters, 2),
            "spray_tank_pct": round((self.spray.current_liters / self.spray.capacity_liters) * 100, 1),
            "pump_active": self.spray.pump_active,
            "solenoid_open": self.spray.solenoid_open,
            "nozzle_angle_deg": self.spray.nozzle_angle_deg,
            "camera_height_cm": self.camera_mount.current_height_cm,
            "latitude": round(self.latitude, 6),
            "longitude": round(self.longitude, 6),
            "heading_deg": round(self.heading_deg, 1),
            "speed_kmh": round(self.speed_kmh, 2),
            "left_motor_pwm": self.motors.left_speed,
            "right_motor_pwm": self.motors.right_speed,
        }
