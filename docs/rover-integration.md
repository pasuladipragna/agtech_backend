# Rover Integration Guide

This guide outlines how physical Smart AgriTech Rovers connect to the software platform. The system is designed to be hardware-agnostic; as long as the physical rover can communicate via HTTPS REST (and eventually WebSockets), it can be controlled and monitored.

## 1. Authentication

Physical Rovers do not log in using usernames and passwords. Instead, they authenticate using hardware tokens (simulated in the current architecture).

**Planned Implementation**:
Each physical rover is assigned a cryptographic token upon manufacturing or registration. All requests from the rover to the backend must include this token in the `Authorization: Bearer <TOKEN>` header. The backend validates this token to identify the specific rover instance and its assigned farm.

## 2. Telemetry and Check-ins

Rovers must periodically report their status to the backend. This heartbeat ensures the frontend can display live metrics.

**Endpoint**: `POST /api/v1/rover/telemetry`

**Payload Example**:
```json
{
  "serial_number": "ROVER-4WD-001",
  "battery_pct": 85.5,
  "spray_tank_pct": 60.0,
  "location": {
    "lat": 18.5204,
    "lng": 73.8567
  },
  "current_status": "IDLE" // IDLE, SPRAYING, CHARGING, OFFLINE, ERROR
}
```

## 3. Command Polling vs. Push

Currently, commands (like "START_SPRAYING" or "EMERGENCY_STOP") are enqueued in the database via the `CommunicationService`.

**How hardware executes this**:
1. **Polling (Current Design)**: The rover queries `GET /api/v1/rover/commands` every X seconds to retrieve pending tasks.
2. **Push (Future Design)**: Implement an MQTT broker or FastAPI WebSocket endpoint. The rover maintains a persistent connection, and commands are pushed instantly to the hardware.

## 4. Safety Constraints

The backend `SafetyRuleEngine` is the final arbiter of action. Even if a farmer manually requests a spray session from the UI, the engine evaluates:
- **Wind Speed**: Pulled from weather APIs. If > 15 km/h, spraying is blocked.
- **Human Presence**: If the rover's on-board camera (via `VideoAnalysisService`) detects a human in the vicinity, the engine issues an automatic `EMERGENCY_STOP` command.

Hardware must be programmed to respect the `EMERGENCY_STOP` command with the highest priority and cut power to the nozzles immediately.

## 5. Mocking for Development

During UI development, the hardware is mocked. The backend endpoints in `agtech_backend/modules/rover.py` provide simulated responses to allow frontend testing without physical robots. To test real hardware against local dev, point the hardware's API URL to your machine's local IP address (e.g., `http://192.168.1.50:8000/api/v1`).
