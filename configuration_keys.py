# configuration_keys.py
"""OCPP 1.6 Configuration Keys Management"""

from typing import Dict, List, Any


class ConfigurationKey:
    """Class to represent an OCPP configuration key"""
    def __init__(self, key: str, readonly: bool, value: str, reboot_required: bool = False):
        self.key = key
        self.readonly = readonly
        self.value = value
        self.reboot_required = reboot_required


class ConfigurationManager:
    """Manages OCPP 1.6 configuration keys"""
    
    def __init__(self, heartbeat_interval: int = 60, number_of_connectors: int = 1, max_power: int = 22000):
        self.heartbeat_interval = heartbeat_interval
        self.number_of_connectors = number_of_connectors
        self.max_power = max_power
        self.configuration_keys: Dict[str, ConfigurationKey] = self._initialize_default_config_keys()
    
    def _initialize_default_config_keys(self) -> Dict[str, ConfigurationKey]:
        """Initialize default OCPP 1.6 configuration keys"""
        keys = {
            # Core Profile
            "AllowOfflineTxForUnknownId": ConfigurationKey("AllowOfflineTxForUnknownId", False, "false"),
            "AuthorizationCacheEnabled": ConfigurationKey("AuthorizationCacheEnabled", False, "false"),
            "AuthorizeRemoteTxRequests": ConfigurationKey("AuthorizeRemoteTxRequests", False, "true"),
            "BlinkRepeat": ConfigurationKey("BlinkRepeat", False, "3"),
            "ClockAlignedDataInterval": ConfigurationKey("ClockAlignedDataInterval", False, "0"),
            "ConnectionTimeOut": ConfigurationKey("ConnectionTimeOut", False, "120"),
            "GetConfigurationMaxKeys": ConfigurationKey("GetConfigurationMaxKeys", False, "100"),
            "HeartbeatInterval": ConfigurationKey("HeartbeatInterval", False, str(self.heartbeat_interval)),
            "LightIntensity": ConfigurationKey("LightIntensity", False, "50"),
            "LocalAuthorizeOffline": ConfigurationKey("LocalAuthorizeOffline", False, "true"),
            "LocalPreAuthorize": ConfigurationKey("LocalPreAuthorize", False, "false"),
            "MaxEnergyOnInvalidId": ConfigurationKey("MaxEnergyOnInvalidId", False, "0"),
            "MeterValuesAlignedData": ConfigurationKey("MeterValuesAlignedData", False, "Energy.Active.Import.Register"),
            "MeterValuesSampledData": ConfigurationKey("MeterValuesSampledData", False, "Energy.Active.Import.Register,Power.Active.Import"),
            "MeterValueSampleInterval": ConfigurationKey("MeterValueSampleInterval", False, "60"),
            "MinimumStatusDuration": ConfigurationKey("MinimumStatusDuration", False, "0"),
            "NumberOfConnectors": ConfigurationKey("NumberOfConnectors", True, str(self.number_of_connectors)),
            "ResetRetries": ConfigurationKey("ResetRetries", False, "3"),
            "ConnectorPhaseRotation": ConfigurationKey("ConnectorPhaseRotation", False, "0.RST,1.RST"),
            "StopTransactionOnEVSideDisconnect": ConfigurationKey("StopTransactionOnEVSideDisconnect", False, "true"),
            "StopTransactionOnInvalidId": ConfigurationKey("StopTransactionOnInvalidId", False, "true"),
            "StopTxnAlignedData": ConfigurationKey("StopTxnAlignedData", False, "Energy.Active.Import.Register"),
            "StopTxnSampledData": ConfigurationKey("StopTxnSampledData", False, "Energy.Active.Import.Register"),
            "SupportedFeatureProfiles": ConfigurationKey("SupportedFeatureProfiles", True, "Core,FirmwareManagement,LocalAuthListManagement,Reservation,SmartCharging,RemoteTrigger"),
            "TransactionMessageAttempts": ConfigurationKey("TransactionMessageAttempts", False, "3"),
            "TransactionMessageRetryInterval": ConfigurationKey("TransactionMessageRetryInterval", False, "10"),
            "UnlockConnectorOnEVSideDisconnect": ConfigurationKey("UnlockConnectorOnEVSideDisconnect", False, "true"),
            "WebSocketPingInterval": ConfigurationKey("WebSocketPingInterval", False, "0"),
            
            # Local Auth List Management Profile
            "LocalAuthListEnabled": ConfigurationKey("LocalAuthListEnabled", False, "false"),
            "LocalAuthListMaxLength": ConfigurationKey("LocalAuthListMaxLength", True, "100"),
            "SendLocalListMaxLength": ConfigurationKey("SendLocalListMaxLength", True, "20"),
            
            # Reservation Profile
            "ReserveConnectorZeroSupported": ConfigurationKey("ReserveConnectorZeroSupported", True, "false"),
            
            # Smart Charging Profile
            "ChargeProfileMaxStackLevel": ConfigurationKey("ChargeProfileMaxStackLevel", True, "10"),
            "ChargingScheduleAllowedChargingRateUnit": ConfigurationKey("ChargingScheduleAllowedChargingRateUnit", True, "Current,Power"),
            "ChargingScheduleMaxPeriods": ConfigurationKey("ChargingScheduleMaxPeriods", True, "6"),
            "ConnectorSwitch3to1PhaseSupported": ConfigurationKey("ConnectorSwitch3to1PhaseSupported", True, "false"),
            "MaxChargingProfilesInstalled": ConfigurationKey("MaxChargingProfilesInstalled", True, "10"),
            
            # Custom configuration keys
            "MaxChargingPower": ConfigurationKey("MaxChargingPower", True, str(self.max_power)),
        }
        
        return keys
    
    def load_custom_config_keys(self, custom_keys: List[Dict[str, Any]]):
        """Load custom configuration keys from config"""
        for key_data in custom_keys:
            key_name = key_data.get('key')
            if key_name:
                self.configuration_keys[key_name] = ConfigurationKey(
                    key_name,
                    key_data.get('readonly', False),
                    key_data.get('value', ''),
                    key_data.get('reboot_required', False)
                )
    
    def get_configuration_keys_list(self) -> List[Dict[str, Any]]:
        """Get list of configuration keys for display"""
        return [
            {
                'key': config_key.key,
                'readonly': config_key.readonly,
                'value': config_key.value,
                'reboot_required': config_key.reboot_required
            }
            for config_key in self.configuration_keys.values()
        ]
    
    def update_configuration_key(self, key: str, value: str) -> str:
        """Update a configuration key value. Returns status: Accepted, Rejected, RebootRequired, or NotSupported"""
        if key not in self.configuration_keys:
            return "NotSupported"
        
        config_key = self.configuration_keys[key]
        
        if config_key.readonly:
            return "Rejected"
        
        # Validate specific keys
        if key == "HeartbeatInterval":
            try:
                new_interval = int(value)
                if new_interval < 0:
                    return "Rejected"
                self.heartbeat_interval = new_interval
            except ValueError:
                return "Rejected"
        
        # Update the value
        config_key.value = value
        
        # Return appropriate status
        if config_key.reboot_required:
            return "RebootRequired"
        else:
            return "Accepted"
    
    def get_value(self, key: str, default: str = "") -> str:
        """Get configuration key value"""
        if key in self.configuration_keys:
            return self.configuration_keys[key].value
        return default
    
    def get_int_value(self, key: str, default: int = 0) -> int:
        """Get configuration key value as integer"""
        try:
            return int(self.get_value(key, str(default)))
        except ValueError:
            return default
