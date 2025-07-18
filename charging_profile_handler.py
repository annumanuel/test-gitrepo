# charging_profile_handler.py
"""OCPP 1.6 SetChargingProfile Handler Module"""

from datetime import datetime, timedelta, timezone
from typing import Dict, List, Any, Optional
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class ChargingProfilePurpose(Enum):
    CHARGE_POINT_MAX_PROFILE = "ChargePointMaxProfile"
    TX_DEFAULT_PROFILE = "TxDefaultProfile"
    TX_PROFILE = "TxProfile"


class ChargingProfileKind(Enum):
    ABSOLUTE = "Absolute"
    RECURRING = "Recurring"
    RELATIVE = "Relative"


class RecurrencyKind(Enum):
    DAILY = "Daily"
    WEEKLY = "Weekly"


class ChargingRateUnit(Enum):
    WATTS = "W"
    AMPERES = "A"


class ChargingSchedulePeriod:
    """Represents a charging schedule period"""
    def __init__(self, period_data: Dict[str, Any]):
        self.start_period = period_data.get("startPeriod", 0)  # seconds from start
        self.limit = period_data.get("limit", 0)  # W or A
        self.number_phases = period_data.get("numberPhases")  # optional


class ChargingSchedule:
    """Represents a charging schedule"""
    def __init__(self, schedule_data: Dict[str, Any]):
        self.duration = schedule_data.get("duration")  # seconds
        self.start_schedule = schedule_data.get("startSchedule")  # ISO8601
        self.charging_rate_unit = schedule_data.get("chargingRateUnit", "W")
        self.min_charging_rate = schedule_data.get("minChargingRate")
        
        # Parse charging schedule periods
        self.periods = []
        for period_data in schedule_data.get("chargingSchedulePeriod", []):
            self.periods.append(ChargingSchedulePeriod(period_data))
        
        # Sort periods by start time
        self.periods.sort(key=lambda p: p.start_period)


class ChargingProfile:
    """Represents a complete charging profile"""
    def __init__(self, profile_data: Dict[str, Any]):
        self.charging_profile_id = profile_data.get("chargingProfileId")
        self.transaction_id = profile_data.get("transactionId")
        self.stack_level = profile_data.get("stackLevel", 0)
        self.charging_profile_purpose = profile_data.get("chargingProfilePurpose")
        self.charging_profile_kind = profile_data.get("chargingProfileKind")
        self.recurrency_kind = profile_data.get("recurrencyKind")
        self.valid_from = profile_data.get("validFrom")
        self.valid_to = profile_data.get("validTo")
        
        # Parse charging schedule
        schedule_data = profile_data.get("chargingSchedule", {})
        self.charging_schedule = ChargingSchedule(schedule_data)
        
        # Profile creation time
        self.created_at = datetime.now(timezone.utc)


class ChargingProfileHandler:
    """Handles SetChargingProfile requests and applies limits to meter values"""
    
    def __init__(self, simulator):
        self.simulator = simulator
        # Store active profiles by connector ID
        self.active_profiles: Dict[int, List[ChargingProfile]] = {}
        # Store current effective limits by connector
        self.current_limits: Dict[int, Dict[str, float]] = {}
        
        # Initialize for all connectors (0 = charge point, 1+ = connectors)
        for i in range(self.simulator.number_of_connectors + 1):
            self.active_profiles[i] = []
            self.current_limits[i] = {
                "power_limit": None,  # in Watts
                "current_limit": None,  # in Amperes
                "min_charging_rate": None  # minimum rate
            }
    
    def handle_set_charging_profile(self, connector_id: int, cs_charging_profiles: Dict[str, Any]) -> str:
        """
        Handle SetChargingProfile request
        Returns: Accepted, Rejected, or NotSupported
        """
        try:
            self.simulator.log(f"Processing SetChargingProfile for connector {connector_id}", "INFO")
            
            # Validate connector ID
            if connector_id < 0 or connector_id > self.simulator.number_of_connectors:
                self.simulator.log(f"Invalid connector ID: {connector_id}", "ERROR")
                return "Rejected"
            
            # Create charging profile object
            profile = ChargingProfile(cs_charging_profiles)
            
            # Validate the profile
            validation_result = self._validate_charging_profile(profile, connector_id)
            if validation_result != "Valid":
                self.simulator.log(f"Charging profile validation failed: {validation_result}", "WARNING")
                return "Rejected"
            
            # Check if charging rate unit is supported
            allowed_units = self.simulator.config_manager.get_value("ChargingScheduleAllowedChargingRateUnit", "Current,Power")
            allowed_units_list = [u.strip() for u in allowed_units.split(",")]
            
            if profile.charging_schedule.charging_rate_unit == "W" and "Power" not in allowed_units_list:
                self.simulator.log("Power-based charging profiles not supported", "WARNING")
                return "NotSupported"
            elif profile.charging_schedule.charging_rate_unit == "A" and "Current" not in allowed_units_list:
                self.simulator.log("Current-based charging profiles not supported", "WARNING")
                return "NotSupported"
            
            # Check against charger's maximum power capability
            max_charger_power = getattr(self.simulator, 'max_power', 22000)  # Default 22kW
            for period in profile.charging_schedule.periods:
                if profile.charging_schedule.charging_rate_unit == "W":
                    if period.limit > max_charger_power:
                        self.simulator.log(f"Profile power limit {period.limit}W exceeds charger maximum {max_charger_power}W", "ERROR")
                        return "Rejected"
                elif profile.charging_schedule.charging_rate_unit == "A":
                    # Convert to power assuming 230V per phase (3-phase = 400V line-to-line)
                    phases = period.number_phases or 3
                    estimated_power = period.limit * 230 * phases
                    if estimated_power > max_charger_power:
                        self.simulator.log(f"Profile current limit {period.limit}A ({estimated_power}W estimated) exceeds charger maximum {max_charger_power}W", "ERROR")
                        return "Rejected"
            
            # Remove conflicting profiles (same ID or stack level)
            self._remove_conflicting_profiles(connector_id, profile)
            
            # Add the new profile
            self.active_profiles[connector_id].append(profile)
            
            # Sort by stack level (higher level = higher priority)
            self.active_profiles[connector_id].sort(key=lambda p: p.stack_level, reverse=True)
            
            # Apply the profile limits immediately
            self._apply_charging_limits(connector_id)
            
            self.simulator.log(f"Charging profile {profile.charging_profile_id} accepted for connector {connector_id}", "INFO")
            
            return "Accepted"
            
        except Exception as e:
            self.simulator.log(f"Error handling SetChargingProfile: {e}", "ERROR")
            return "Rejected"
    
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
            
            for profile in self.active_profiles[conn_id]:
                # Check if profile matches clearing criteria
                if profile_id is not None and profile.charging_profile_id == profile_id:
                    profiles_to_remove.append(profile)
                elif (charging_profile_purpose is not None and 
                      profile.charging_profile_purpose == charging_profile_purpose):
                    if stack_level is None or profile.stack_level == stack_level:
                        profiles_to_remove.append(profile)
            
            # Remove matching profiles
            for profile in profiles_to_remove:
                self.active_profiles[conn_id].remove(profile)
                profiles_cleared = True
                self.simulator.log(f"Cleared charging profile {profile.charging_profile_id} from connector {conn_id}", "INFO")
            
            # Reapply limits after clearing profiles
            if profiles_to_remove:
                self._apply_charging_limits(conn_id)
        
        return "Accepted" if profiles_cleared else "Unknown"
    
    def get_current_charging_limit(self, connector_id: int) -> Dict[str, Optional[float]]:
        """Get current effective charging limits for a connector"""
        if connector_id not in self.current_limits:
            return {"power_limit": None, "current_limit": None, "min_charging_rate": None}
        
        return self.current_limits[connector_id].copy()
    
    def _validate_charging_profile(self, profile: ChargingProfile, connector_id: int) -> str:
        """Validate a charging profile"""
        # Check stack level
        max_stack_level = self.simulator.config_manager.get_int_value("ChargeProfileMaxStackLevel", 10)
        if profile.stack_level > max_stack_level:
            return f"Stack level {profile.stack_level} exceeds maximum {max_stack_level}"
        
        # Check number of periods
        max_periods = self.simulator.config_manager.get_int_value("ChargingScheduleMaxPeriods", 6)
        if len(profile.charging_schedule.periods) > max_periods:
            return f"Number of periods {len(profile.charging_schedule.periods)} exceeds maximum {max_periods}"
        
        # Validate periods
        last_start = -1
        for period in profile.charging_schedule.periods:
            if period.start_period <= last_start:
                return "Schedule periods must have increasing start times"
            if period.limit < 0:
                return "Period limits must be non-negative"
            last_start = period.start_period
        
        # Check transaction-specific profiles
        if profile.charging_profile_purpose == "TxProfile":
            if profile.transaction_id:
                # Verify transaction exists on this connector
                if self.simulator.connector_transactions.get(connector_id) != profile.transaction_id:
                    return f"Transaction {profile.transaction_id} not active on connector {connector_id}"
            elif connector_id == 0:
                return "TxProfile cannot be set on connector 0 without transaction ID"
        
        return "Valid"
    
    def _remove_conflicting_profiles(self, connector_id: int, new_profile: ChargingProfile):
        """Remove profiles that conflict with the new profile"""
        profiles_to_remove = []
        
        for existing_profile in self.active_profiles[connector_id]:
            # Remove profile with same ID
            if existing_profile.charging_profile_id == new_profile.charging_profile_id:
                profiles_to_remove.append(existing_profile)
            # Remove profile with same stack level and purpose
            elif (existing_profile.stack_level == new_profile.stack_level and
                  existing_profile.charging_profile_purpose == new_profile.charging_profile_purpose):
                profiles_to_remove.append(existing_profile)
        
        for profile in profiles_to_remove:
            self.active_profiles[connector_id].remove(profile)
            self.simulator.log(f"Removed conflicting profile {profile.charging_profile_id}", "INFO")
    
    def _apply_charging_limits(self, connector_id: int):
        """Apply charging profile limits to meter values"""
        # Get effective limits from active profiles
        effective_limits = self._calculate_effective_limits(connector_id)
        
        # Store the limits
        self.current_limits[connector_id] = effective_limits
        
        # Apply limits to meter values handler
        if hasattr(self.simulator, 'meter_handler'):
            self._apply_limits_to_meter_values(connector_id, effective_limits)
        
        # Log the applied limits
        if effective_limits["power_limit"] is not None:
            self.simulator.log(f"Applied power limit {effective_limits['power_limit']}W to connector {connector_id}", "INFO")
        if effective_limits["current_limit"] is not None:
            self.simulator.log(f"Applied current limit {effective_limits['current_limit']}A to connector {connector_id}", "INFO")
    
    def _calculate_effective_limits(self, connector_id: int) -> Dict[str, Optional[float]]:
        """Calculate effective charging limits based on active profiles"""
        current_time = datetime.now(timezone.utc)
        
        # Get all active profiles for this connector (including connector 0 profiles)
        all_profiles = []
        
        # Add connector-specific profiles
        for profile in self.active_profiles[connector_id]:
            if self._is_profile_active(profile, current_time):
                all_profiles.append(profile)
        
        # Add connector 0 profiles (charge point level) if this is not connector 0
        if connector_id > 0:
            for profile in self.active_profiles[0]:
                if self._is_profile_active(profile, current_time):
                    all_profiles.append(profile)
        
        if not all_profiles:
            return {"power_limit": None, "current_limit": None, "min_charging_rate": None}
        
        # Sort by stack level (highest first)
        all_profiles.sort(key=lambda p: p.stack_level, reverse=True)
        
        # Apply the highest priority (highest stack level) profile
        for profile in all_profiles:
            current_limit = self._get_current_period_limit(profile, current_time)
            if current_limit is not None:
                limits = {"power_limit": None, "current_limit": None, "min_charging_rate": None}
                
                if profile.charging_schedule.charging_rate_unit == "W":
                    limits["power_limit"] = current_limit
                    # Convert to current (assuming 230V single phase or 400V 3-phase)
                    limits["current_limit"] = current_limit / 230.0  # Simplified conversion
                elif profile.charging_schedule.charging_rate_unit == "A":
                    limits["current_limit"] = current_limit
                    # Convert to power (assuming 230V single phase or 400V 3-phase)
                    limits["power_limit"] = current_limit * 230.0  # Simplified conversion
                
                # Add minimum charging rate if specified
                if profile.charging_schedule.min_charging_rate is not None:
                    limits["min_charging_rate"] = profile.charging_schedule.min_charging_rate
                
                return limits
        
        return {"power_limit": None, "current_limit": None, "min_charging_rate": None}
    
    def _is_profile_active(self, profile: ChargingProfile, current_time: datetime) -> bool:
        """Check if a charging profile is currently active"""
        # Check validity period
        if profile.valid_from:
            try:
                valid_from = datetime.fromisoformat(profile.valid_from.replace('Z', '+00:00'))
                if current_time < valid_from:
                    return False
            except (ValueError, AttributeError):
                pass
        
        if profile.valid_to:
            try:
                valid_to = datetime.fromisoformat(profile.valid_to.replace('Z', '+00:00'))
                if current_time > valid_to:
                    return False
            except (ValueError, AttributeError):
                pass
        
        # Check transaction-specific profiles
        if profile.charging_profile_purpose == "TxProfile" and profile.transaction_id:
            # Check if transaction is still active
            for conn_id, trans_id in self.simulator.connector_transactions.items():
                if trans_id == profile.transaction_id:
                    return True
            return False
        
        return True
    
    def _get_current_period_limit(self, profile: ChargingProfile, current_time: datetime) -> Optional[float]:
        """Get the current charging limit from a profile's schedule"""
        if not profile.charging_schedule.periods:
            return None
        
        # Determine schedule start time
        if profile.charging_schedule.start_schedule:
            try:
                schedule_start = datetime.fromisoformat(profile.charging_schedule.start_schedule.replace('Z', '+00:00'))
            except (ValueError, AttributeError):
                schedule_start = current_time
        elif profile.charging_profile_kind == "Relative":
            # For relative profiles, start from transaction start or profile creation
            schedule_start = profile.created_at
        else:
            schedule_start = current_time
        
        # Calculate elapsed time
        elapsed_seconds = (current_time - schedule_start).total_seconds()
        
        # Handle recurring profiles
        if profile.charging_profile_kind == "Recurring":
            if profile.recurrency_kind == "Daily":
                elapsed_seconds = elapsed_seconds % 86400  # 24 hours
            elif profile.recurrency_kind == "Weekly":
                elapsed_seconds = elapsed_seconds % 604800  # 7 days
        
        # Find the applicable period
        applicable_period = None
        for period in profile.charging_schedule.periods:
            if elapsed_seconds >= period.start_period:
                applicable_period = period
            else:
                break
        
        return applicable_period.limit if applicable_period else None
    
    def _apply_limits_to_meter_values(self, connector_id: int, limits: Dict[str, Optional[float]]):
        """Apply charging limits to meter values"""
        if not hasattr(self.simulator.meter_handler, 'meter_values'):
            return
        
        # Initialize meter values for connector if not exists
        if connector_id not in self.simulator.meter_handler.meter_values:
            self.simulator.meter_handler.initialize_connector(connector_id)
        
        meter_vals = self.simulator.meter_handler.meter_values[connector_id]
        
        # Apply power limit
        if limits["power_limit"] is not None:
            current_power = meter_vals.get("Power.Active.Import", 7400)
            limited_power = min(current_power, limits["power_limit"])
            meter_vals["Power.Active.Import"] = limited_power
            meter_vals["Power.Offered"] = limited_power  # Update offered power too
        
        # Apply current limit
        if limits["current_limit"] is not None:
            current_current = meter_vals.get("Current.Import", 32.0)
            limited_current = min(current_current, limits["current_limit"])
            meter_vals["Current.Import"] = limited_current
            meter_vals["Current.Offered"] = limited_current  # Update offered current too
        
        # Apply minimum charging rate if specified
        if limits["min_charging_rate"] is not None:
            if limits["power_limit"] is not None:
                meter_vals["Power.Active.Import"] = max(meter_vals["Power.Active.Import"], limits["min_charging_rate"])
        
        # Update related meter values
        if "Power.Active.Import" in meter_vals and "Current.Import" in meter_vals:
            # Update voltage to maintain consistency (P = V * I)
            voltage = meter_vals["Power.Active.Import"] / meter_vals["Current.Import"] if meter_vals["Current.Import"] > 0 else 230.0
            meter_vals["Voltage"] = min(voltage, 250.0)  # Cap at reasonable voltage
    
    def get_active_profiles_info(self) -> Dict[int, List[Dict[str, Any]]]:
        """Get information about all active charging profiles"""
        profiles_info = {}
        
        for connector_id, profiles in self.active_profiles.items():
            if profiles:
                profiles_info[connector_id] = []
                for profile in profiles:
                    profile_info = {
                        "id": profile.charging_profile_id,
                        "stack_level": profile.stack_level,
                        "purpose": profile.charging_profile_purpose,
                        "kind": profile.charging_profile_kind,
                        "rate_unit": profile.charging_schedule.charging_rate_unit,
                        "periods": [
                            {
                                "start": period.start_period,
                                "limit": period.limit,
                                "phases": period.number_phases
                            }
                            for period in profile.charging_schedule.periods
                        ],
                        "current_limit": self._get_current_period_limit(profile, datetime.now(timezone.utc))
                    }
                    profiles_info[connector_id].append(profile_info)
        
        return profiles_info