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

    def start(self, event_loop):
        self.loop = event_loop

        def on_connect(client, userdata, flags, rc):
            if rc == 0:
                topic = f"{settings.MQTT_TOPIC_PREFIX}/+/telemetry"
                client.subscribe(topic)
                logger.info(f"Backend MQTT Bridge subscribed to: {topic}")

        def on_message(client, userdata, msg):
            try:
                payload = json.loads(msg.payload.decode("utf-8"))
                rover_id = payload.get("rover_id")
                data = payload.get("data", {})
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
            except Exception as e:
                logger.error(f"Error parsing incoming MQTT telemetry: {e}")

        self.client.on_connect = on_connect
        self.client.on_message = on_message

        try:
            self.client.connect(settings.MQTT_BROKER_HOST, settings.MQTT_BROKER_PORT, keepalive=60)
            self.client.loop_start()
            logger.info("Backend MQTT Loop started successfully.")
        except Exception as e:
            logger.warning(f"Backend MQTT Bridge connect failed ({e}). Running with in-memory telemetry pool.")

    def dispatch_command(self, rover_id: str, command: str, params: dict = None):
        if not self.client.is_connected():
            logger.warning("Cannot dispatch command; MQTT broker is disconnected")
            return False
        topic = f"{settings.MQTT_TOPIC_PREFIX}/{rover_id}/command"
        payload = json.dumps({
            "command": command.upper(),
            "params": params or {}
        })
        try:
            self.client.publish(topic, payload)
            logger.info(f"Dispatched high-level command '{command}' to topic '{topic}'")
            return True
        except Exception as e:
            logger.error(f"Failed to publish command over MQTT: {e}")
            return False

mqtt_bridge = BackendMQTTBridge()
