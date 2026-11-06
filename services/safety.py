"""
Smart AgriTech Rover — Safety Rule Engine
Validates all pre-spray conditions before allowing spraying to start.
This is a deterministic safety layer — not AI-driven.
AI may inform decisions, but NEVER bypasses safety rules.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class SafetyCheckResult:
    passed: bool
    reason: str = ""


class SafetyRuleEngine:
    """
    Evaluates safety conditions before allowing any physical action.
    All checks are deterministic. No AI model involved.
    
    Usage:
        result = safety_engine.check_spray_conditions(rover, telemetry, product, field_id)
        if not result.passed:
            raise HTTPException(400, result.reason)
    """

    def check_spray_conditions(
        self,
        rover,
        rover_telemetry: Optional[dict],
        product=None,
        field_id: Optional[str] = None,
    ) -> SafetyCheckResult:
        """
        Validate all conditions required before spraying can begin.
        Returns first failed condition with a farmer-friendly message.
        """

        # 1. Rover must exist
        if rover is None:
            return SafetyCheckResult(False, "No rover is available for spraying.")

        # 2. Rover must be active
        if not rover.is_active:
            return SafetyCheckResult(False, "This rover is not currently active.")

        # 3. Rover must be connected (we must have live telemetry)
        if rover_telemetry is None:
            return SafetyCheckResult(
                False,
                "Spraying cannot start because the rover is not connected. "
                "Please ensure the rover is powered on and in range."
            )

        # 4. Rover must NOT be in emergency stop
        rover_status = rover_telemetry.get("rover_status")
        if rover_status == "EMERGENCY_STOP":
            return SafetyCheckResult(
                False,
                "Spraying cannot start because the rover is in Emergency Stop mode. "
                "Please release the emergency stop before continuing."
            )

        # 5. Tank must have sufficient liquid
        tank_pct = rover_telemetry.get("spray_tank_pct")
        if tank_pct is not None and tank_pct < 5.0:
            return SafetyCheckResult(
                False,
                f"Spraying cannot start because the spray tank is almost empty ({tank_pct:.0f}%). "
                "Please refill the tank before spraying."
            )

        # 6. Battery must be sufficient for spraying
        battery_pct = rover_telemetry.get("battery_pct")
        if battery_pct is not None and battery_pct < 15.0:
            return SafetyCheckResult(
                False,
                f"Spraying cannot start because the rover battery is critically low ({battery_pct:.0f}%). "
                "Please charge the rover before spraying."
            )

        # 7. Rover must not already be spraying
        if rover_status == "SPRAYING":
            return SafetyCheckResult(
                False,
                "A spray session is already in progress. Please stop the current session first."
            )

        # 8. Product must be specified and valid
        if product is None:
            return SafetyCheckResult(
                False,
                "No spray product has been selected. Please select a product before spraying."
            )

        if not product.is_active:
            return SafetyCheckResult(
                False,
                f"The selected product '{product.name}' is currently not available. "
                "Please select a different product."
            )

        # 9. Field must be specified
        if field_id is None:
            return SafetyCheckResult(
                False,
                "No field has been selected for spraying. Please select a field."
            )

        # All checks passed
        return SafetyCheckResult(True, "All safety conditions met.")

    def check_movement_conditions(
        self,
        rover,
        rover_telemetry: Optional[dict],
        command: str,
    ) -> SafetyCheckResult:
        """Validate conditions for movement commands."""

        if rover is None or not rover.is_active:
            return SafetyCheckResult(False, "Rover is not available.")

        if rover_telemetry is None:
            return SafetyCheckResult(False, "Rover is not connected.")

        rover_status = rover_telemetry.get("rover_status")
        if rover_status == "EMERGENCY_STOP" and command != "EMERGENCY_STOP":
            return SafetyCheckResult(
                False,
                "The rover is in Emergency Stop mode. "
                "Release emergency stop before issuing movement commands."
            )

        battery_pct = rover_telemetry.get("battery_pct")
        if battery_pct is not None and battery_pct < 5.0:
            return SafetyCheckResult(
                False,
                "Cannot move rover — battery is critically low. "
                "Please charge the rover immediately."
            )

        return SafetyCheckResult(True, "Movement conditions met.")


# Singleton
safety_engine = SafetyRuleEngine()
