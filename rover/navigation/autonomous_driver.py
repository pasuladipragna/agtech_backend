import math
import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger("RoverNavigation")

class AutonomousDriver:
    def __init__(self, hal):
        self.hal = hal
        self.is_active = False
        self.is_paused = False
        self.waypoints: List[Dict[str, float]] = []
        self.current_waypoint_idx = 0
        self.mission_id: Optional[str] = None
        self.total_distance_meters = 0.0

    def start_mission(self, mission_id: str, waypoints: List[Dict[str, float]]):
        if not waypoints:
            logger.warning("Attempted to start autonomous mission with 0 waypoints")
            return False
        
        self.mission_id = mission_id
        self.waypoints = waypoints
        self.current_waypoint_idx = 0
        self.is_active = True
        self.is_paused = False
        logger.info(f"Autonomous mission '{mission_id}' started with {len(waypoints)} waypoints.")
        return True

    def pause_mission(self):
        if self.is_active:
            self.is_paused = True
            self.hal.execute_high_level_command("STOP")
            logger.info("Autonomous mission paused.")

    def resume_mission(self):
        if self.is_active and self.is_paused:
            self.is_paused = False
            logger.info("Autonomous mission resumed.")

    def stop_mission(self):
        self.is_active = False
        self.is_paused = False
        self.hal.execute_high_level_command("STOP")
        logger.info("Autonomous mission stopped.")

    def step_navigation(self) -> Dict[str, Any]:
        if not self.is_active or self.is_paused or not self.waypoints:
            return {"status": "IDLE" if not self.is_active else "PAUSED"}

        if self.current_waypoint_idx >= len(self.waypoints):
            logger.info("All waypoints reached. Mission complete!")
            self.stop_mission()
            return {"status": "COMPLETED", "mission_id": self.mission_id}

        target = self.waypoints[self.current_waypoint_idx]
        curr_lat = self.hal.latitude
        curr_lng = self.hal.longitude

        d_lat = math.radians(target["lat"] - curr_lat)
        d_lng = math.radians(target["lng"] - curr_lng)
        distance_meters = math.sqrt((d_lat * 6371000)**2 + (d_lng * 6371000 * math.cos(math.radians(curr_lat)))**2)

        if distance_meters < 1.5:
            logger.info(f"Reached Waypoint {self.current_waypoint_idx + 1}/{len(self.waypoints)}")
            if target.get("spray_on_arrival", False):
                self.hal.execute_high_level_command("START_SPRAYING")
            
            self.current_waypoint_idx += 1
            if self.current_waypoint_idx >= len(self.waypoints):
                self.stop_mission()
                return {"status": "COMPLETED", "mission_id": self.mission_id}
            target = self.waypoints[self.current_waypoint_idx]

        y = math.sin(d_lng) * math.cos(math.radians(target["lat"]))
        x = math.cos(math.radians(curr_lat)) * math.sin(math.radians(target["lat"])) - \
            math.sin(math.radians(curr_lat)) * math.cos(math.radians(target["lat"])) * math.cos(d_lng)
        target_bearing = (math.degrees(math.atan2(y, x)) + 360) % 360
        heading_error = (target_bearing - self.hal.heading_deg + 540) % 360 - 180

        if abs(heading_error) > 20:
            if heading_error > 0:
                self.hal.execute_high_level_command("TURN_RIGHT")
            else:
                self.hal.execute_high_level_command("TURN_LEFT")
        else:
            self.hal.execute_high_level_command("MOVE_FORWARD", {"speed_pct": 50.0})

        return {
            "status": "NAVIGATING",
            "current_waypoint_index": self.current_waypoint_idx,
            "total_waypoints": len(self.waypoints),
            "distance_to_target_m": round(distance_meters, 2),
            "heading_error_deg": round(heading_error, 1)
        }
