# message_handlers.py
"""OCPP 1.6 Message Handlers"""

import asyncio
from typing import Dict, Any
from ocpp_enums import OCPPAction, ChargerStatus
import logging

logger = logging.getLogger(__name__)


class MessageHandlers:
    """Handles incoming OCPP messages"""
    
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
        await self.simulator.send_call_result(message_id, {"status": "Accepted"})
        
        # Start transaction
        await self.simulator.start_transaction(
            payload.get("idTag"),
            payload.get("connectorId", 1)
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
        else:
            await self.simulator.send_call_result(message_id, {"status": "NotImplemented"})
    
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
    
    async def handle_set_charging_profile(self, message_id: str, payload: dict):
        """Handle SetChargingProfile request"""
        self.simulator.log(f"SetChargingProfile received: {payload}")
        
        connector_id = payload.get("connectorId", 0)
        cs_charging_profiles = payload.get("csChargingProfiles", {})
        
        if hasattr(self.simulator, 'charging_profiles_manager'):
            status = self.simulator.charging_profiles_manager.handle_set_charging_profile(
                connector_id, cs_charging_profiles
            )
        else:
            status = "NotSupported"
            self.simulator.log("Charging profiles manager not initialized", "ERROR")
        
        await self.simulator.send_call_result(message_id, {"status": status})
    
    async def handle_clear_charging_profile(self, message_id: str, payload: dict):
        """Handle ClearChargingProfile request"""
        self.simulator.log(f"ClearChargingProfile received: {payload}")
        
        if hasattr(self.simulator, 'charging_profiles_manager'):
            status = self.simulator.charging_profiles_manager.handle_clear_charging_profile(payload)
        else:
            status = "Unknown"
            self.simulator.log("Charging profiles manager not initialized", "ERROR")
        
        await self.simulator.send_call_result(message_id, {"status": status})
    
    async def handle_get_composite_schedule(self, message_id: str, payload: dict):
        """Handle GetCompositeSchedule request"""
        self.simulator.log(f"GetCompositeSchedule received: {payload}")
        
        connector_id = payload.get("connectorId", 0)
        duration = payload.get("duration", 86400)  # Default 24 hours
        charging_rate_unit = payload.get("chargingRateUnit")
        
        if hasattr(self.simulator, 'charging_profiles_manager'):
            response = self.simulator.charging_profiles_manager.handle_get_composite_schedule(
                connector_id, duration, charging_rate_unit
            )
        else:
            response = {"status": "Rejected"}
            self.simulator.log("Charging profiles manager not initialized", "ERROR")
        
        await self.simulator.send_call_result(message_id, response)
