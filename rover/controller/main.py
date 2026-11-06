import time
import logging
from rover.config.rover_config import settings
from rover.hardware.hal import RoverHAL
from rover.navigation.autonomous_driver import AutonomousDriver
from rover.communication.mqtt_client import RoverMQTTClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("RoverMain")

class RoverControllerApp:
    def __init__(self):
        logger.info(f"Initializing Rover Controller for {settings.rover_id}...")
        self.hal = RoverHAL()
        self.navigator = AutonomousDriver(self.hal)
        self.mqtt = RoverMQTTClient(
            broker=settings.mqtt_broker,
            port=settings.mqtt_port,
            rover_id=settings.rover_id,
            topic_prefix=settings.mqtt_prefix
        )
        self.mqtt.set_command_callback(self.handle_incoming_command)
        self.running = False

    def handle_incoming_command(self, cmd: str, params: dict):
        cmd_upper = cmd.upper()
        logger.info(f"Executing High-Level Command: {cmd_upper}")
        
        if cmd_upper == "START_AUTONOMOUS_MISSION":
            mission_id = params.get("mission_id", "MISSION-AUTONOMOUS-01")
            waypoints = params.get("waypoints", [])
            self.navigator.start_mission(mission_id, waypoints)
        elif cmd_upper == "PAUSE_MISSION":
            self.navigator.pause_mission()
        elif cmd_upper == "RESUME_MISSION":
            self.navigator.resume_mission()
        elif cmd_upper == "RETURN_HOME":
            home_wp = [{"lat": 36.778259, "lng": -119.417931, "name": "Home Base"}]
            self.navigator.start_mission("RETURN-HOME-MISSION", home_wp)
        else:
            self.hal.execute_high_level_command(cmd_upper, params)

    def run(self):
        self.mqtt.connect()
        self.running = True
        logger.info("Rover Controller Service active and listening for commands...")

        last_telemetry_time = 0
        try:
            while self.running:
                current_time = time.time()
                nav_status = self.navigator.step_navigation()
                sensor_data = self.hal.read_sensors()
                
                if current_time - last_telemetry_time >= 1.0:
                    sensor_data["nav_status"] = nav_status
                    self.mqtt.publish_telemetry(sensor_data)
                    last_telemetry_time = current_time

                time.sleep(0.1)
        except KeyboardInterrupt:
            logger.info("Shutdown signal received.")
        finally:
            self.hal.execute_high_level_command("EMERGENCY_STOP")

if __name__ == "__main__":
    app = RoverControllerApp()
    app.run()
