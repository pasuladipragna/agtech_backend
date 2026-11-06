# Smart AgriTech Rover — Raspberry Pi Setup Guide

## Overview

This folder contains everything needed to run the rover client on a Raspberry Pi.
The Pi connects to the same MQTT broker as the AgriTech backend.
Commands flow: **Web Dashboard → Backend API → MQTT Broker → Raspberry Pi → GPIO Hardware**

---

## 1. Hardware Wiring

### Motor Driver (L298N / L293D Dual H-Bridge)

| Pi GPIO (BCM) | Physical Pin | L298N Pin | Notes                  |
|---------------|-------------|-----------|------------------------|
| GPIO 12 (PWM) | Pin 32      | ENA       | Left  motor speed PWM  |
| GPIO 20       | Pin 38      | IN1       | Left  motor direction A|
| GPIO 21       | Pin 40      | IN2       | Left  motor direction B|
| GPIO 13 (PWM) | Pin 33      | ENB       | Right motor speed PWM  |
| GPIO 23       | Pin 16      | IN3       | Right motor direction A|
| GPIO 24       | Pin 18      | IN4       | Right motor direction B|
| GND           | Pin 6       | GND       | Shared ground          |

### Spray System

| Pi GPIO (BCM) | Physical Pin | Device        | Notes                        |
|---------------|-------------|---------------|------------------------------|
| GPIO 25       | Pin 22      | Pump Relay IN | Active HIGH, controls DC pump|
| GPIO 8        | Pin 24      | Solenoid Relay| Active HIGH, controls valve  |
| GPIO 18 (PWM) | Pin 12      | Nozzle Servo  | 50Hz, 500-2500us pulse width |

### Sensors (Optional)

| Component       | Pi Pin        | Connection     |
|-----------------|---------------|----------------|
| INA219 Battery  | GPIO 2 (SDA)  | I2C (address 0x40)|
| INA219 Battery  | GPIO 3 (SCL)  | I2C            |
| GPS NEO-6M TX   | GPIO 15 (RX)  | UART0          |
| Pi Camera V2    | CSI Port      | Ribbon cable   |

---

## 2. Raspberry Pi Software Setup

### Step 1 - Enable required interfaces
```bash
sudo raspi-config
# Enable: Camera, I2C, Serial (disable login shell, keep serial port)
```

### Step 2 - Update and install system packages
```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3-pip python3-dev gpsd gpsd-clients
```

### Step 3 - Install Python dependencies
```bash
pip3 install paho-mqtt RPi.GPIO pigpio Pillow pi-ina219
pip3 install picamera2    # for Pi Camera V2
pip3 install gps          # if using GPS
```

### Step 4 - Start the pigpio daemon (required for hardware PWM)
```bash
sudo pigpiod
# To start automatically on boot:
sudo systemctl enable pigpiod
sudo systemctl start pigpiod
```

### Step 5 - Configure GPS (if fitted)
```bash
sudo systemctl stop serial-getty@ttyS0.service
sudo systemctl disable serial-getty@ttyS0.service
sudo gpsd /dev/ttyS0 -F /var/run/gpsd.sock
sudo systemctl enable gpsd
sudo systemctl start gpsd
```

---

## 3. Network Setup

The Pi and your backend server MUST be on the **same local network** (same WiFi router).

### Find your backend server LAN IP (run on the backend PC):
**Windows:**
```powershell
ipconfig | findstr "IPv4"
```
**Linux/Mac:**
```bash
hostname -I
```

### Set the environment variable on the Pi:
```bash
export ROVER_MQTT_BROKER=192.168.1.100   # ← replace with your server LAN IP
export ROVER_ID=ROVER-4WD-01
```

Or create a `.env` file:
```bash
ROVER_MQTT_BROKER=192.168.1.100
ROVER_ID=ROVER-4WD-01
TELEMETRY_HZ=2
CAMERA_ENABLED=true
GPS_ENABLED=false
INA219_ENABLED=false
```

---

## 4. Running on the Raspberry Pi

### Copy files to Pi (from your PC):
```powershell
scp -r C:\Users\Hello\Desktop\agtech\raspberry_pi\* pi@<PI_IP>:/home/pi/agtech_rover/
```

### Run on Pi:
```bash
cd /home/pi/agtech_rover
sudo pigpiod
ROVER_MQTT_BROKER=192.168.1.100 python3 pi_rover.py
```

### Run as a systemd service (auto-start on boot):
```bash
sudo nano /etc/systemd/system/agtech-rover.service
```
Paste:
```ini
[Unit]
Description=Smart AgriTech Rover Client
After=network.target pigpiod.service

[Service]
User=pi
WorkingDirectory=/home/pi/agtech_rover
Environment=ROVER_MQTT_BROKER=192.168.1.100
Environment=ROVER_ID=ROVER-4WD-01
Environment=CAMERA_ENABLED=true
ExecStart=/usr/bin/python3 pi_rover.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```
```bash
sudo systemctl enable agtech-rover
sudo systemctl start agtech-rover
sudo systemctl status agtech-rover
```

---

## 5. MQTT Broker on the Backend Server (Windows)

Install Mosquitto MQTT broker on your backend PC:

### Option A - Install Mosquitto on Windows
1. Download from https://mosquitto.org/download/
2. Install and use the provided `mosquitto.conf`
3. Run: `mosquitto -c mosquitto.conf`

### Option B - Use Docker (recommended)
```powershell
docker run -d -p 1883:1883 --name mqtt-broker eclipse-mosquitto
```

---

## 6. Test Connection

### From the Pi, test MQTT connectivity:
```bash
mosquitto_sub -h 192.168.1.100 -t "agritech/rover/#" -v &
python3 pi_rover.py
```
You should see telemetry messages flowing in real-time.

### From the backend PC, test sending a command:
```powershell
# Install: pip install paho-mqtt
python -c "
import paho.mqtt.client as mqtt, json
c = mqtt.Client()
c.connect('localhost', 1883)
c.publish('agritech/rover/ROVER-4WD-01/command', json.dumps({'command':'MOVE_FORWARD','params':{'speed_pct':50}}))
c.disconnect()
"
```

---

## 7. Environment Variables Reference

| Variable          | Default           | Description                              |
|-------------------|-------------------|------------------------------------------|
| ROVER_ID          | ROVER-4WD-01      | Unique rover identifier                  |
| ROVER_MQTT_BROKER | 192.168.1.100     | Backend/broker server LAN IP             |
| ROVER_MQTT_PORT   | 1883              | MQTT port                                |
| MQTT_TOPIC_PREFIX | agritech/rover    | Topic namespace (must match backend)     |
| TELEMETRY_HZ      | 2                 | Telemetry updates per second             |
| CAMERA_ENABLED    | true              | Enable Pi Camera capture & streaming     |
| GPS_ENABLED       | false             | Enable GPS via gpsd                      |
| INA219_ENABLED    | false             | Enable INA219 battery monitor            |
| SIMULATE_HARDWARE | false             | Use simulation (no real GPIO needed)     |

---

## 8. Supported Commands

| Command            | Description                         |
|--------------------|-------------------------------------|
| MOVE_FORWARD       | Drive forward (speed_pct: 0-100)    |
| MOVE_BACKWARD      | Drive backward (speed_pct: 0-100)   |
| TURN_LEFT          | Spin left in place                  |
| TURN_RIGHT         | Spin right in place                 |
| STOP               | Stop all motors                     |
| EMERGENCY_STOP     | Immediate stop + pump off           |
| START_SPRAYING     | Start pump + pulse solenoid valve   |
| STOP_SPRAYING      | Stop pump + close solenoid          |
| ROTATE_NOZZLE      | Set nozzle angle (angle_deg: -45 to +45) |
| RETURN_HOME        | Stop rover (autonomous nav via backend)|
| SET_MODE           | Set rover mode (MANUAL/AUTONOMOUS)  |

All commands are sent from the Web Dashboard -> Backend API -> MQTT -> Pi automatically.
