import os
from pydantic import BaseModel

class RoverSettings(BaseModel):
    rover_id: str = os.getenv("ROVER_ID", "ROVER-4WD-01")
    mqtt_broker: str = os.getenv("ROVER_MQTT_BROKER", "localhost")
    mqtt_port: int = int(os.getenv("ROVER_MQTT_PORT", "1883"))
    mqtt_prefix: str = os.getenv("MQTT_TOPIC_PREFIX", "agritech/rover")
    
    max_speed_rpm: int = 250
    wheel_diameter_meters: float = 0.35
    track_width_meters: float = 0.85
    
    max_tank_capacity_liters: float = 25.0
    pump_max_flow_rate_lpm: float = 3.5
    solenoid_pulse_ms: int = 500
    
    min_camera_height_cm: int = 50
    max_camera_height_cm: int = 180
    
    nominal_voltage: float = 25.6
    min_safe_voltage: float = 21.0
    max_full_voltage: float = 28.8

settings = RoverSettings()
