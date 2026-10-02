# Hardware Wiring & MQTT Communication Protocol 🔌⚡

## 1. Hardware Actuators & Specification

| Subsystem | Hardware Spec | Control Protocol / Signal |
| :--- | :--- | :--- |
| **Drive Motors** | 4WD 24V DC Geared Motors | Dual Channel Motor Driver (PWM / Direction Pins) |
| **Spraying Pump** | 12V/24V DC High-Pressure Pump | Relay / MOSFET Switch |
| **Solenoid Valve** | High-Speed Brass Solenoid Valve | PWM Pulse Trigger (e.g. 500ms pulse width) |
| **Nozzle Servo** | Rotatable Nozzle Actuator | Servo PWM Signal (-45° to +45°) |
| **Camera Mount** | Motorized Linear Actuator | Up/Down Relay H-Bridge |
| **Power System** | 24V LiFePO4 Battery + Solar Panel | Voltage Divider ADC & Current Sensor |
| **Location** | GPS Module | NMEA Serial TTL |

---

## 2. MQTT Command Protocol

All commands are published to MQTT topic: `agritech/rover/{ROVER_ID}/command`

### Payload Structure

```json
{
  "command": "START_SPRAYING",
  "params": {
    "pulse_ms": 500
  }
}
```

### Supported High-Level Commands

- `MOVE_FORWARD` (params: `speed_pct`: 0-100)
- `MOVE_BACKWARD` (params: `speed_pct`: 0-100)
- `TURN_LEFT`
- `TURN_RIGHT`
- `STOP`
- `EMERGENCY_STOP`
- `START_AUTONOMOUS_MISSION` (params: `mission_id`, `waypoints`)
- `PAUSE_MISSION`
- `RESUME_MISSION`
- `RETURN_HOME`
- `START_SPRAYING` (params: `pulse_ms`)
- `STOP_SPRAYING`
- `RAISE_CAMERA`
- `LOWER_CAMERA`
- `ROTATE_NOZZLE` (params: `angle_deg`: -45 to +45)
