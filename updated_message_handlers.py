# message_handlers.py - Updated with Charging Profile Integration
"""OCPP 1.6 Message Handlers with Charging Profile Support"""

import asyncio
from typing import Dict, Any
from ocpp_enums import OCPPAction, ChargerStatus
import logging

logger = logging.getLogger(__name__)


class MessageHandlers:
    """Handles incoming OCPP messages with charging profile support"""
    
    def __init__(self, simulator):
        self.simulator = simulator
    
    async def handle_reset(self, message_id: str, payload: dict):
        """Handle Reset request"""
        self.simulator.log(f"Reset request received: {payload}")
        await self.simulator.send_call_result(message_id, {"status": "Accepted"})
        
        # Simulate reset
        await asyncio.sleep(2)
        self.simulator.log("Simulating reset...")
        self.simulator.is_connected = False
        await self.simulator.websocket.close()
    
    async def handle_remote_start_transaction(self, message_id: str, payload: dict):
        """Handle RemoteStartTransaction request"""
        self.simulator.log(f"RemoteStartTransaction received: {payload}")
        
        # Check if charging profile is included
        charging_profile = payload.get("chargingProfile")
        connector_id = payload.get("connectorId", 1)
        
        await self.simulator.send_call_result(message_id, {"status": "Accepted"})
        
        # If charging profile is provided, set it first
        if charging_profile and hasattr(self.simulator, 'charging_profile_handler'):
            self.simulator.log(f"Setting charging profile from RemoteStartTransaction", "INFO")
            profile_status = self.simulator.charging_profile_handler.handle_set_charging_profile(
                connector_id, charging_profile
            )
            self.simulator.log(f"Charging profile status: {profile_status}", "INFO")
        
        # Start transaction
        await self.simulator.start_transaction(
            payload.get("idTag"),
            connector_id
        )
    
    async def handle_remote_stop_transaction(self, message_id: str, payload: dict):
        """Handle RemoteStopTransaction request"""
        self.simulator.log(f"RemoteStopTransaction received: {payload}")
        await self.simulator.send_call_result(message_id, {"status": "Accepted"})
        
        # Stop transaction
        await self.simulator.stop_transaction(payload.get("transactionId"))
    
    async def handle_get_configuration(self, message_id: str, payload: dict):
        """Handle GetConfiguration request"""
        self.simulator.log(f"GetConfiguration received: {payload}")
        
        requested_keys = payload.get("key", [])
        
        configuration_keys = []
        unknown_keys = []
        
        if not requested_keys:
            # Return all keys
            for config_key in self.simulator.config_manager.configuration_keys.values():
                configuration_keys.append({
                    "key": config_key.key,
                    "readonly": config_key.readonly,
                    "value": config_key.value
                })
        else:
            # Return only requested keys
            for key_name in requested_keys:
                if key_name in self.simulator.config_manager.configuration_keys:
                    config_key = self.simulator.config_manager.configuration_keys[key_name]
                    configuration_keys.append({
                        "key": config_key.key,
                        "readonly": config_key.readonly,
                        "value": config_key.value
                    })
                else:
                    unknown_keys.append(key_name)
        
        response = {
            "configurationKey": configuration_keys
        }
        
        if unknown_keys:
            response["unknownKey"] = unknown_keys
        
        await self.simulator.send_call_result(message_id, response)
        self.simulator.log(f"Sent {len(configuration_keys)} configuration keys")
    
    async def handle_change_configuration(self, message_id: str, payload: dict):
        """Handle ChangeConfiguration request"""
        self.simulator.log(f"ChangeConfiguration received: {payload}")
        
        key = payload.get("key")
        value = payload.get("value")
        
        if not key or value is None:
            await self.simulator.send_call_result(message_id, {"status": "Rejected"})
            return
        
        status = self.simulator.config_manager.update_configuration_key(key, value)
        
        await self.simulator.send_call_result(message_id, {"status": status})
        
        if status == "Accepted":
            self.simulator.log(f"Configuration key '{key}' updated to '{value}'")
            
            # Handle special cases for certain configuration keys
            if key == "MeterValueSampleInterval":
                self.simulator.log("MeterValueSampleInterval changed, meter value loops will use new interval on next cycle")
            elif key == "MeterValuesSampledData":
                self.simulator.log("MeterValuesSampledData changed, meter values will include new measurands on next cycle")
            elif key == "HeartbeatInterval":
                self.simulator.heartbeat_interval = self.simulator.config_manager.heartbeat_interval
                self.simulator.log(f"HeartbeatInterval updated to {self.simulator.heartbeat_interval}")
                
        elif status == "RebootRequired":
            self.simulator.log(f"Configuration key '{key}' updated to '{value}' (reboot required)")
        elif status == "NotSupported":
            self.simulator.log(f"Configuration key '{key}' not supported", "WARNING")
        else:
            self.simulator.log(f"Failed to update configuration key '{key}'", "WARNING")
    
    async def handle_clear_cache(self, message_id: str, payload: dict):
        """Handle ClearCache request"""
        self.simulator.log(f"ClearCache received: {payload}")
        await self.simulator.send_call_result(message_id, {"status": "Accepted"})
    
    async def handle_trigger_message(self, message_id: str, payload: dict):
        """Handle TriggerMessage request"""
        self.simulator.log(f"TriggerMessage received: {payload}")
        
        requested_message = payload.get("requestedMessage")
        
        if requested_message == "BootNotification":
            await self.simulator.send_call_result(message_id, {"status": "Accepted"})
            await self.simulator.send_boot_notification()
        elif requested_message == "Heartbeat":
            await self.simulator.send_call_result(message_id, {"status": "Accepted"})
            await self.simulator.send_call(OCPPAction.HEARTBEAT.value, {})
        elif requested_message == "StatusNotification":
            await self.simulator.send_call_result(message_id, {"status": "Accepted"})
            connector_id = payload.get("connectorId", 1)
            await self.simulator.send_status_notification(
                connector_id, 
                self.simulator.connector_status.get(connector_id, ChargerStatus.AVAILABLE)
            )
        elif requested_message == "MeterValues":
            await self.simulator.send_call_result(message_id, {"status": "Accepted"})
            # Trigger immediate meter values for the specified connector
            connector_id = payload.get("connectorId", 1)
            if hasattr(self.simulator, 'meter_handler'):
                await self.simulator.meter_handler.send_immediate_meter_values(connector_id)
        else:
            await self.simulator.send_call_result(message_id, {"status": "NotImplemented"})
    
    async def handle_set_charging_profile(self, message_id: str, payload: dict):
        """Handle SetChargingProfile request"""
        self.simulator.log(f"SetChargingProfile received for connector {payload.get('connectorId', 'unknown')}", "INFO")
        
        connector_id = payload.get("connectorId", 0)
        cs_charging_profiles = payload.get("csChargingProfiles", {})
        
        if hasattr(self.simulator, 'charging_profile_handler'):
            try:
                status = self.simulator.charging_profile_handler.handle_set_charging_profile(
                    connector_id, cs_charging_profiles
                )
                
                await self.simulator.send_call_result(message_id, {"status": status})
                
                if status == "Accepted":
                    self.simulator.log(f"Charging profile {cs_charging_profiles.get('chargingProfileId', 'unknown')} applied successfully", "INFO")
                    
                    # Show current effective limits
                    limits = self.simulator.charging_profile_handler.get_current_charging_limit(connector_id)
                    if limits["power_limit"] is not None:
                        self.simulator.log(f"Effective power limit for connector {connector_id}: {limits['power_limit']}W", "INFO")
                    if limits["current_limit"] is not None:
                        self.simulator.log(f"Effective current limit for connector {connector_id}: {limits['current_limit']:.1f}A", "INFO")
                        
                elif status == "Rejected":
                    self.simulator.log(f"Charging profile rejected for connector {connector_id}", "WARNING")
                elif status == "NotSupported":
                    self.simulator.log(f"Charging profile not supported for connector {connector_id}", "WARNING")
                    
            except Exception as e:
                self.simulator.log(f"Error processing SetChargingProfile: {e}", "ERROR")
                await self.simulator.send_call_result(message_id, {"status": "Rejected"})
        else:
            self.simulator.log("Charging profile handler not initialized", "ERROR")
            await self.simulator.send_call_result(message_id, {"status": "NotSupported"})
    
    async def handle_clear_charging_profile(self, message_id: str, payload: dict):
        """Handle ClearChargingProfile request"""
        self.simulator.log(f"ClearChargingProfile received: {payload}")
        
        if hasattr(self.simulator, 'charging_profile_handler'):
            try:
                status = self.simulator.charging_profile_handler.handle_clear_charging_profile(payload)
                await self.simulator.send_call_result(message_id, {"status": status})
                
                if status == "Accepted":
                    self.simulator.log(f"Charging profile(s) cleared successfully", "INFO")
                else:
                    self.simulator.log(f"No matching charging profiles found to clear", "INFO")
                    
            except Exception as e:
                self.simulator.log(f"Error processing ClearChargingProfile: {e}", "ERROR")
                await self.simulator.send_call_result(message_id, {"status": "Unknown"})
        else:
            self.simulator.log("Charging profile handler not initialized", "ERROR")
            await self.simulator.send_call_result(message_id, {"status": "Unknown"})
    
    async def handle_get_composite_schedule(self, message_id: str, payload: dict):
        """Handle GetCompositeSchedule request"""
        self.simulator.log(f"GetCompositeSchedule received: {payload}")
        
        connector_id = payload.get("connectorId", 0)
        duration = payload.get("duration", 86400)  # Default 24 hours
        charging_rate_unit = payload.get("chargingRateUnit")
        
        if hasattr(self.simulator, 'charging_profile_handler'):
            try:
                # Get active profiles for the connector
                profiles_info = self.simulator.charging_profile_handler.get_active_profiles_info()
                connector_profiles = profiles_info.get(connector_id, [])
                
                if connector_profiles:
                    # Build composite schedule from active profiles
                    # For simplicity, use the highest priority profile
                    highest_priority = max(connector_profiles, key=lambda p: p["stack_level"])
                    
                    response = {
                        "status": "Accepted",
                        "connectorId": connector_id,
                        "scheduleStart": datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
                        "chargingSchedule": {
                            "duration": duration,
                            "chargingRateUnit": charging_rate_unit or highest_priority["rate_unit"],
                            "chargingSchedulePeriod": [
                                {
                                    "startPeriod": period["start"],
                                    "limit": period["limit"],
                                    "numberPhases": period.get("phases")
                                }
                                for period in highest_priority["periods"]
                            ]
                        }
                    }
                else:
                    response = {"status": "Accepted"}
                
                await self.simulator.send_call_result(message_id, response)
                
            except Exception as e:
                self.simulator.log(f"Error processing GetCompositeSchedule: {e}", "ERROR")
                await self.simulator.send_call_result(message_id, {"status": "Rejected"})
        else:
            self.simulator.log("Charging profile handler not initialized", "ERROR")
            await self.simulator.send_call_result(message_id, {"status": "Rejected"})
    
    def get_handlers(self) -> Dict[str, Any]:
        """Get all message handlers"""
        return {
            "Reset": self.handle_reset,
            "RemoteStartTransaction": self.handle_remote_start_transaction,
            "RemoteStopTransaction": self.handle_remote_stop_transaction,
            "GetConfiguration": self.handle_get_configuration,
            "ChangeConfiguration": self.handle_change_configuration,
            "ClearCache": self.handle_clear_cache,
            "TriggerMessage": self.handle_trigger_message,
            "SetChargingProfile": self.handle_set_charging_profile,
            "ClearChargingProfile": self.handle_clear_charging_profile,
            "GetCompositeSchedule": self.handle_get_composite_schedule
        }