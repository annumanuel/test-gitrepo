# charging_profiles.py
"""OCPP 1.6 Charging Profiles Management"""

from datetime import datetime
from typing import Dict, Any, List, Optional
import logging

logger = logging.getLogger(__name__)


class ChargingProfile:
    """Represents an OCPP 1.6 Charging Profile"""
    
    def __init__(self, profile_data: Dict[str, Any]):
        self.charging_profile_id = profile_data.get("chargingProfileId")
        self.transaction_id = profile_data.get("transactionId")
        self.stack_level = profile_data.get("stackLevel", 0)
        self.charging_profile_purpose = profile_data.get("chargingProfilePurpose", "TxDefaultProfile")
        self.charging_profile_kind = profile_data.get("chargingProfileKind", "Absolute")
        self.recurrency_kind = profile_data.get("recurrencyKind")
        self.valid_from = profile_data.get("validFrom")
        self.valid_to = profile_data.get("validTo")
        
        # Charging Schedule
        charging_schedule = profile_data.get("chargingSchedule", {})
        self.duration = charging_schedule.get("duration")
        self.start_schedule = charging_schedule.get("startSchedule")
        self.charging_rate_unit = charging_schedule.get("chargingRateUnit", "A")
        self.charging_schedule_periods = charging_schedule.get("chargingSchedulePeriod", [])
        self.min_charging_rate = charging_schedule.get("minChargingRate")


class ChargingProfilesManager:
    """Manages charging profiles and applies power/current limits"""
    
    def __init__(self, simulator):
        self.simulator = simulator
        self.charging_profiles: Dict[int, List[ChargingProfile]] = {}
        self.current_limits: Dict[int, Dict[str, Optional[float]]] = {}
        
        # Initialize profiles for all connectors (including connector 0)
        for i in range(self.simulator.number_of_connectors + 1):
            self.charging_profiles[i] = []
            self.current_limits[i] = {"power": None, "current": None}
    
    def handle_set_charging_profile(self, connector_id: int, cs_charging_profiles: Dict[str, Any]) -> str:
        """
        Handle SetChargingProfile request
        Returns: Accepted, Rejected, or NotSupported
        """
        try:
            # Validate connector ID
            if connector_id < 0 or connector_id > self.simulator.number_of_connectors:
                self.simulator.log(f"Invalid connector ID: {connector_id}", "ERROR")
                return "Rejected"
            
            # Create charging profile object
            profile = ChargingProfile(cs_charging_profiles)
            
            # Validate charging profile
            validation_result = self._validate_charging_profile(profile, connector_id)
            if validation_result != "Valid":
                self.simulator.log(f"Charging profile validation failed: {validation_result}", "WARNING")
                return "Rejected"
            
            # Check if we support the charging rate unit
            allowed_units = self.simulator.config_manager.get_value("ChargingScheduleAllowedChargingRateUnit", "Current,Power")
            allowed_units_list = [u.strip() for u in allowed_units.split(",")]
            
            if profile.charging_rate_unit == "W" and "Power" not in allowed_units_list:
                self.simulator.log("Power-based charging profiles not supported", "WARNING")
                return "NotSupported"
            elif profile.charging_rate_unit == "A" and "Current" not in allowed_units_list:
                self.simulator.log("Current-based charging profiles not supported", "WARNING")
                return "NotSupported"
            
            # Validate power/current limits against charger maximum
            power_validation = self._validate_power_limits(profile)
            if power_validation != "Valid":
                self.simulator.log(f"Power validation failed: {power_validation}", "WARNING")
                return "Rejected"
            
            # Remove existing profiles with same ID or stack level
            self._remove_conflicting_profiles(connector_id, profile)
            
            # Add the new profile
            self.charging_profiles[connector_id].append(profile)
            
            # Sort profiles by stack level (higher stack level has priority)
            self.charging_profiles[connector_id].sort(key=lambda p: p.stack_level, reverse=True)
            
            # Update current limits based on active profiles
            self._update_current_limits(connector_id)
            
            self.simulator.log(f"Charging profile {profile.charging_profile_id} set for connector {connector_id}", "INFO")
            
            return "Accepted"
            
        except Exception as e:
            self.simulator.log(f"Error handling SetChargingProfile: {e}", "ERROR")
            return "Rejected"
    
    def _validate_power_limits(self, profile: ChargingProfile) -> str:
        """Validate that profile limits don't exceed charger maximum"""
        max_power = getattr(self.simulator, 'max_power', 11000)
        max_current = getattr(self.simulator, 'max_current', 48)
        
        for period in profile.charging_schedule_periods:
            limit = period.get("limit", 0)
            
            if profile.charging_rate_unit == "W":
                if limit > max_power:
                    return f"Power limit {limit}W exceeds charger maximum {max_power}W"
            elif profile.charging_rate_unit == "A":
                if limit > max_current:
                    return f"Current limit {limit}A exceeds charger maximum {max_current}A"
                    
        return "Valid"
    
    def handle_clear_charging_profile(self, request: Dict[str, Any]) -> str:
        """
        Handle ClearChargingProfile request
        Returns: Accepted or Unknown
        """
        profile_id = request.get("id")
        connector_id = request.get("connectorId")
        charging_profile_purpose = request.get("chargingProfilePurpose")
        stack_level = request.get("stackLevel")
        
        profiles_cleared = False
        
        # Determine which connectors to check
        if connector_id is not None:
            connectors_to_check = [connector_id]
        else:
            connectors_to_check = range(self.simulator.number_of_connectors + 1)
        
        for conn_id in connectors_to_check:
            profiles_to_remove = []
            
            for profile in self.charging_profiles[conn_id]:
                # Check if profile matches criteria
                if profile_id is not None and profile.charging_profile_id == profile_id:
                    profiles_to_remove.append(profile)
                elif (connector_id is not None and 
                      charging_profile_purpose is not None and 
                      profile.charging_profile_purpose == charging_profile_purpose):
                    if stack_level is None or profile.stack_level == stack_level:
                        profiles_to_remove.append(profile)
            
            # Remove matching profiles
            for profile in profiles_to_remove:
                self.charging_profiles[conn_id].remove(profile)
                profiles_cleared = True
                self.simulator.log(f"Cleared charging profile {profile.charging_profile_id} from connector {conn_id}", "INFO")
            
            # Update limits if profiles were removed
            if profiles_to_remove:
                self._update_current_limits(conn_id)
        
        return "Accepted" if profiles_cleared else "Unknown"
    
    def handle_get_composite_schedule(self, connector_id: int, duration: int, 
                                    charging_rate_unit: Optional[str] = None) -> Dict[str, Any]:
        """
        Handle GetCompositeSchedule request
        Returns composite schedule for the connector
        """
        if connector_id < 0 or connector_id > self.simulator.number_of_connectors:
            return {"status": "Rejected"}
        
        # Get active profiles for connector
        active_profiles = self._get_active_profiles(connector_id)
        
        if not active_profiles:
            return {"status": "Accepted"}
        
        # Generate composite schedule
        composite_schedule = self._generate_composite_schedule(
            active_profiles, duration, charging_rate_unit
        )
        
        if composite_schedule:
            return {
                "status": "Accepted",
                "connectorId": connector_id,
                "scheduleStart": datetime.utcnow().isoformat() + "Z",
                "chargingSchedule": composite_schedule
            }
        else:
            return {"status": "Accepted"}
    
    def get_current_limit(self, connector_id: int) -> Dict[str, Optional[float]]:
        """
        Get current power/current limit for a connector
        Returns dict with 'power' (W) and 'current' (A) limits
        """
        if connector_id not in self.current_limits:
            return {"power": None, "current": None}
        
        return self.current_limits[connector_id].copy()
    
    def _validate_charging_profile(self, profile: ChargingProfile, connector_id: int) -> str:
        """Validate a charging profile"""
        # Check stack level
        max_stack_level = self.simulator.config_manager.get_int_value("ChargeProfileMaxStackLevel", 10)
        if profile.stack_level > max_stack_level:
            return f"Stack level {profile.stack_level} exceeds maximum {max_stack_level}"
        
        # Check number of periods
        max_periods = self.simulator.config_manager.get_int_value("ChargingScheduleMaxPeriods", 6)
        if len(profile.charging_schedule_periods) > max_periods:
            return f"Number of periods {len(profile.charging_schedule_periods)} exceeds maximum {max_periods}"
        
        # Check if profile is for a specific transaction
        if profile.charging_profile_purpose == "TxProfile":
            if profile.transaction_id:
                # Check if transaction exists on this connector
                if self.simulator.connector_transactions.get(connector_id) != profile.transaction_id:
                    return f"Transaction {profile.transaction_id} not active on connector {connector_id}"
            elif connector_id == 0:
                return "TxProfile cannot be set on connector 0 without transaction ID"
        
        # Validate schedule periods
        last_start_period = -1
        for period in profile.charging_schedule_periods:
            start_period = period.get("startPeriod", 0)
            if start_period <= last_start_period:
                return "Schedule periods must have increasing startPeriod values"
            last_start_period = start_period
            
            # Check limit value
            limit = period.get("limit", 0)
            if limit < 0:
                return "Limit values must be non-negative"
        
        return "Valid"
    
    def _remove_conflicting_profiles(self, connector_id: int, new_profile: ChargingProfile):
        """Remove profiles that conflict with the new profile"""
        profiles_to_remove = []
        
        for existing_profile in self.charging_profiles[connector_id]:
            # Remove profile with same ID
            if existing_profile.charging_profile_id == new_profile.charging_profile_id:
                profiles_to_remove.append(existing_profile)
            # Remove profile with same stack level and purpose
            elif (existing_profile.stack_level == new_profile.stack_level and
                  existing_profile.charging_profile_purpose == new_profile.charging_profile_purpose):
                profiles_to_remove.append(existing_profile)
        
        for profile in profiles_to_remove:
            self.charging_profiles[connector_id].remove(profile)
    
    def _update_current_limits(self, connector_id: int):
        """Update current power/current limits based on active profiles"""
        active_profiles = self._get_active_profiles(connector_id)
        
        if not active_profiles:
            self.current_limits[connector_id] = {"power": None, "current": None}
            return
        
        # Get the highest priority profile (highest stack level)
        current_time = datetime.utcnow().replace(tzinfo=None)  # Ensure naive datetime
        
        for profile in active_profiles:
            # Find applicable schedule period
            applicable_period = self._get_applicable_period(profile, current_time)
            
            if applicable_period:
                limit_value = applicable_period.get("limit", 0)
                
                # Apply charger maximum limits
                max_power = getattr(self.simulator, 'max_power', 11000)
                max_current = getattr(self.simulator, 'max_current', 48)
                
                if profile.charging_rate_unit == "W":
                    # Ensure limit doesn't exceed charger maximum
                    actual_power = min(limit_value, max_power)
                    self.current_limits[connector_id]["power"] = actual_power
                    # Convert to current (assuming 230V single phase)
                    self.current_limits[connector_id]["current"] = actual_power / 230.0
                elif profile.charging_rate_unit == "A":
                    # Ensure limit doesn't exceed charger maximum
                    actual_current = min(limit_value, max_current)
                    self.current_limits[connector_id]["current"] = actual_current
                    # Convert to power (assuming 230V single phase)
                    self.current_limits[connector_id]["power"] = actual_current * 230.0
                
                # Apply limit to meter values handler
                if hasattr(self.simulator, 'meter_handler') and connector_id in self.simulator.meter_handler.meter_values:
                    if self.current_limits[connector_id]["power"]:
                        self.simulator.meter_handler.meter_values[connector_id]["Power.Active.Import"] = \
                            min(self.current_limits[connector_id]["power"], 
                                self.simulator.meter_handler.meter_values[connector_id].get("Power.Active.Import", max_power))
                    
                    if self.current_limits[connector_id]["current"]:
                        self.simulator.meter_handler.meter_values[connector_id]["Current.Import"] = \
                            min(self.current_limits[connector_id]["current"],
                                self.simulator.meter_handler.meter_values[connector_id].get("Current.Import", max_current))
                
                self.simulator.log(f"Updated limits for connector {connector_id}: "
                                 f"Power={self.current_limits[connector_id]['power']}W, "
                                 f"Current={self.current_limits[connector_id]['current']}A", "INFO")
                break
    
    def _get_active_profiles(self, connector_id: int) -> List[ChargingProfile]:
        """Get active profiles for a connector"""
        current_time = datetime.utcnow().replace(tzinfo=None)  # Ensure naive datetime
        active_profiles = []
        
        for profile in self.charging_profiles[connector_id]:
            # Check validity period
            if profile.valid_from:
                try:
                    # Parse and convert to naive datetime
                    valid_from_str = profile.valid_from.replace('Z', '+00:00') if profile.valid_from.endswith('Z') else profile.valid_from
                    valid_from = datetime.fromisoformat(valid_from_str).replace(tzinfo=None)
                    if current_time < valid_from:
                        continue
                except (ValueError, AttributeError):
                    # If parsing fails, skip this check
                    pass
            
            if profile.valid_to:
                try:
                    # Parse and convert to naive datetime
                    valid_to_str = profile.valid_to.replace('Z', '+00:00') if profile.valid_to.endswith('Z') else profile.valid_to
                    valid_to = datetime.fromisoformat(valid_to_str).replace(tzinfo=None)
                    if current_time > valid_to:
                        continue
                except (ValueError, AttributeError):
                    # If parsing fails, skip this check
                    pass
            
            active_profiles.append(profile)
        
        return active_profiles
    
    def _get_applicable_period(self, profile: ChargingProfile, current_time: datetime) -> Optional[Dict[str, Any]]:
        """Get the applicable schedule period for current time"""
        if not profile.charging_schedule_periods:
            return None
        
        # Ensure current_time is naive
        if current_time.tzinfo is not None:
            current_time = current_time.replace(tzinfo=None)
        
        # Calculate schedule start time
        if profile.start_schedule:
            try:
                # Parse and convert to naive datetime
                start_schedule_str = profile.start_schedule.replace('Z', '+00:00') if profile.start_schedule.endswith('Z') else profile.start_schedule
                schedule_start = datetime.fromisoformat(start_schedule_str).replace(tzinfo=None)
            except (ValueError, AttributeError):
                schedule_start = current_time
        elif profile.charging_profile_kind == "Relative":
            # For relative profiles, start from transaction start
            # This is simplified - in real implementation, you'd track transaction start times
            schedule_start = current_time
        else:
            schedule_start = current_time
        
        # Calculate elapsed time since schedule start
        elapsed_seconds = (current_time - schedule_start).total_seconds()
        
        # Handle recurring profiles
        if profile.charging_profile_kind == "Recurring":
            if profile.recurrency_kind == "Daily":
                elapsed_seconds = elapsed_seconds % 86400  # 24 hours
            elif profile.recurrency_kind == "Weekly":
                elapsed_seconds = elapsed_seconds % 604800  # 7 days
        
        # Find applicable period
        applicable_period = None
        for period in profile.charging_schedule_periods:
            if elapsed_seconds >= period.get("startPeriod", 0):
                applicable_period = period
            else:
                break
        
        return applicable_period
    
    def _generate_composite_schedule(self, profiles: List[ChargingProfile], 
                                   duration: int, charging_rate_unit: Optional[str]) -> Optional[Dict[str, Any]]:
        """Generate a composite schedule from active profiles"""
        if not profiles:
            return None
        
        # Use the unit from the highest priority profile if not specified
        if not charging_rate_unit:
            charging_rate_unit = profiles[0].charging_rate_unit
        
        # For simplicity, return the schedule of the highest priority profile
        # In a real implementation, you would merge all profiles considering their stack levels
        highest_profile = profiles[0]
        
        return {
            "duration": min(duration, highest_profile.duration) if highest_profile.duration else duration,
            "chargingRateUnit": charging_rate_unit,
            "chargingSchedulePeriod": highest_profile.charging_schedule_periods
        }