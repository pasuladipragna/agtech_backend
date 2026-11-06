import json
import logging
import time
import paho.mqtt.client as mqtt
from typing import Callable, Optional

logger = logging.getLogger("RoverMQTT")

class RoverMQTTClient:
    def __init__(self, broker: str, port: int, rover_id: str, topic_prefix: str = "agritech/rover"):
        self.broker = broker
        self.port = port
        self.rover_id = rover_id
        self.topic_prefix = topic_prefix
        
        self.telemetry_topic = f"{topic_prefix}/{rover_id}/telemetry"
        self.command_topic = f"{topic_prefix}/{rover_id}/command"
        self.events_topic = f"{topic_prefix}/{rover_id}/events"
        
        self.client = mqtt.Client(client_id=f"RoverController-{rover_id}")
        self.command_callback: Optional[Callable[[str, dict], None]] = None

    def set_command_callback(self, callback: Callable[[str, dict], None]):
        self.command_callback = callback

    def connect(self):
        def on_connect(client, userdata, flags, rc):
            if rc == 0:
                logger.info(f"Connected to MQTT Broker at {self.broker}:{self.port}")
                client.subscribe(self.command_topic)
            else:
                logger.error(f"MQTT Connection failed with return code {rc}")

        def on_message(client, userdata, msg):
            try:
                payload = json.loads(msg.payload.decode("utf-8"))
                cmd = payload.get("command")
                params = payload.get("params", {})
                logger.info(f"Received MQTT Command: {cmd} with params: {params}")
                if self.command_callback:
                    self.command_callback(cmd, params)
            except Exception as e:
                logger.error(f"Failed to process MQTT message: {e}")

        self.client.on_connect = on_connect
        self.client.on_message = on_message

        try:
            self.client.connect(self.broker, self.port, keepalive=60)
            self.client.loop_start()
            return True
        except Exception as e:
            logger.warning(f"Could not connect to MQTT broker ({e}). Standalone mode.")
            return False

    def publish_telemetry(self, telemetry_data: dict):
        try:
            payload = json.dumps({
                "rover_id": self.rover_id,
                "timestamp": time.time(),
                "data": telemetry_data
            })
            self.client.publish(self.telemetry_topic, payload)
        except Exception as e:
            logger.debug(f"Telemetry publish skipped/failed: {e}")

    def publish_event(self, event_type: str, details: dict):
        try:
            payload = json.dumps({
                "rover_id": self.rover_id,
                "event": event_type,
                "timestamp": time.time(),
                "details": details
            })
            self.client.publish(self.events_topic, payload)
        except Exception as e:
            logger.debug(f"Event publish failed: {e}")
