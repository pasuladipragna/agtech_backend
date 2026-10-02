import json
import logging
import asyncio
from datetime import datetime, timezone
import paho.mqtt.client as mqtt
from core.config import settings
from core.websocket_manager import ws_manager

logger = logging.getLogger("BackendMQTT")

class BackendMQTTBridge:
    def __init__(self):
        self.client = mqtt.Client(client_id="AgriTechBackendAPI")
        self.latest_telemetry = {}
        self.latest_telemetry_received_at = {}
        self.loop = None

    def _record_mock_telemetry(self, rover_id: str, command: str, params: dict = None):
        params = params or {}
        existing = self.latest_telemetry.get(rover_id, {})
        cmd = command.upper()

        status = existing.get("rover_status", "IDLE")
        speed_kmh = float(existing.get("speed_kmh", 0.0) or 0.0)
        speed_pct = float(params.get("speed_pct", params.get("speed", 50)) or 50)

        if cmd in {"MOVE_FORWARD", "MOVE_BACKWARD", "TURN_LEFT", "TURN_RIGHT"}:
            if cmd == "MOVE_FORWARD":
                speed_kmh = round(max(0.0, speed_pct / 100.0 * 5.0), 2)
            elif cmd == "MOVE_BACKWARD":
                speed_kmh = round(-max(0.0, speed_pct / 100.0 * 4.0), 2)
            elif cmd in {"TURN_LEFT", "TURN_RIGHT"}:
                speed_kmh = round(max(0.0, speed_pct / 100.0 * 2.0), 2)
            status = "MOVING"
        elif cmd == "STOP":
            speed_kmh = 0.0
            status = "IDLE"
        elif cmd == "EMERGENCY_STOP":
            speed_kmh = 0.0
            status = "EMERGENCY_STOP"
        elif cmd == "START_SPRAYING":
            status = "SPRAYING"
        elif cmd == "STOP_SPRAYING":
            status = "IDLE"

        mock_data = {
            "rover_id": rover_id,
            "rover_status": status,
            "speed_kmh": speed_kmh,
            "battery_pct": existing.get("battery_pct", 97.0),
            "spray_tank_pct": existing.get("spray_tank_pct", 100.0),
            "latitude": existing.get("latitude", 36.778259),
            "longitude": existing.get("longitude", -119.417931),
            "heading_deg": existing.get("heading_deg", 0.0),
            "camera_active": existing.get("camera_active", True),
            "gps_available": existing.get("gps_available", True),
            "mode": existing.get("mode", "MANUAL"),
            "spraying": cmd == "START_SPRAYING",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self.latest_telemetry[rover_id] = mock_data
        self.latest_telemetry_received_at[rover_id] = datetime.now(timezone.utc)

        if self.loop and self.loop.is_running():
            asyncio.run_coroutine_threadsafe(
                ws_manager.broadcast({
                    "type": "ROVER_TELEMETRY",
                    "rover_id": rover_id,
                    "telemetry": mock_data
                }),
                self.loop
            )

    def start(self, event_loop):
        self.loop = event_loop

        def on_connect(client, userdata, flags, rc):
            if rc == 0:
                telemetry_topic = f"{settings.MQTT_TOPIC_PREFIX}/+/telemetry"
                events_topic = f"{settings.MQTT_TOPIC_PREFIX}/+/events"
                client.subscribe(telemetry_topic, qos=0)
                client.subscribe(events_topic, qos=1)
                msg = (
                    f"[MQTT] ✅ Connected to broker {settings.MQTT_BROKER_HOST}:{settings.MQTT_BROKER_PORT} — "
                    f"subscribed to telemetry + events"
                )
                logger.info(msg)
                print(msg, flush=True)
            else:
                msg = f"[MQTT] ❌ Backend MQTT Bridge connection failed rc={rc}"
                logger.error(msg)
                print(msg, flush=True)

        def on_message(client, userdata, msg):
            try:
                payload = json.loads(msg.payload.decode("utf-8"))
                topic = msg.topic

                if topic.endswith("/telemetry"):
                    rover_id = payload.get("rover_id")
                    data = payload.get("data", payload)  # pi_rover wraps data; fallback to root
                    if rover_id:
                        self.latest_telemetry[rover_id] = data
                        self.latest_telemetry_received_at[rover_id] = datetime.now(timezone.utc)
                        if self.loop and self.loop.is_running():
                            asyncio.run_coroutine_threadsafe(
                                ws_manager.broadcast({
                                    "type": "ROVER_TELEMETRY",
                                    "rover_id": rover_id,
                                    "telemetry": data
                                }),
                                self.loop
                            )

                elif topic.endswith("/events"):
                    rover_id = payload.get("rover_id")
                    event = payload.get("event", "UNKNOWN")
                    details = payload.get("details", {})
                    logger.info(f"[ROVER EVENT] rover={rover_id} event={event} details={details}")
                    if self.loop and self.loop.is_running():
                        asyncio.run_coroutine_threadsafe(
                            ws_manager.broadcast({
                                "type": "ROVER_EVENT",
                                "rover_id": rover_id,
                                "event": event,
                                "details": details,
                                "timestamp": payload.get("timestamp")
                            }),
                            self.loop
                        )

            except Exception as e:
                logger.error(f"Error parsing incoming MQTT message on {msg.topic}: {e}")

        self.client.on_connect = on_connect
        self.client.on_message = on_message

        try:
            self.client.connect(settings.MQTT_BROKER_HOST, settings.MQTT_BROKER_PORT, keepalive=60)
            self.client.loop_start()
            print(
                f"[MQTT] Connecting to broker {settings.MQTT_BROKER_HOST}:{settings.MQTT_BROKER_PORT} ...",
                flush=True,
            )
            logger.info(
                f"Backend MQTT Bridge connecting to "
                f"{settings.MQTT_BROKER_HOST}:{settings.MQTT_BROKER_PORT} ..."
            )
        except Exception as e:
            msg = f"[MQTT] ⚠️  Broker connect failed ({e}). Running with in-memory telemetry pool."
            logger.warning(msg)
            print(msg, flush=True)

    def dispatch_command(self, rover_id: str, command: str, params: dict = None):
        print(
            f"[MQTT COMMAND] rover={rover_id} command={command.upper()} params={params or {}}",
            flush=True,
        )
        if not self.client.is_connected():
            logger.warning("MQTT broker is disconnected; updating mock rover telemetry for local development.")
            self._record_mock_telemetry(rover_id, command, params)
            print(f"[MQTT COMMAND] local mock dispatch=SUCCESS rover={rover_id} command={command.upper()}", flush=True)
            return True
        topic = f"{settings.MQTT_TOPIC_PREFIX}/{rover_id}/command"
        payload = json.dumps({
            "command": command.upper(),
            "params": params or {}
        })
        try:
            self.client.publish(topic, payload)
            logger.info(f"Dispatched high-level command '{command}' to topic '{topic}'")
            print(f"[MQTT COMMAND] topic={topic} publish=SUCCESS", flush=True)
            return True
        except Exception as e:
            logger.error(f"Failed to publish command over MQTT: {e}")
            print(f"[MQTT COMMAND] topic={topic} publish=FAILED error={e}", flush=True)
            return False

mqtt_bridge = BackendMQTTBridge()
