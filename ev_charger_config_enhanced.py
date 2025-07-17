# ev_charger_simulator_gui.py

import asyncio
import json
import base64
import logging
from datetime import datetime
from typing import Dict, Any, Optional, List
import websockets
from enum import Enum
import sys
import platform
import urllib.parse
import threading
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox, filedialog
import ssl

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class MessageType(Enum):
    CALL = 2
    CALL_RESULT = 3
    CALL_ERROR = 4


class OCPPAction(Enum):
    BOOT_NOTIFICATION = "BootNotification"
    HEARTBEAT = "Heartbeat"
    STATUS_NOTIFICATION = "StatusNotification"
    START_TRANSACTION = "StartTransaction"
    STOP_TRANSACTION = "StopTransaction"
    METER_VALUES = "MeterValues"
    AUTHORIZE = "Authorize"


class ChargerStatus(Enum):
    AVAILABLE = "Available"
    PREPARING = "Preparing"
    CHARGING = "Charging"
    SUSPENDED_EV = "SuspendedEV"
    SUSPENDED_EVSE = "SuspendedEVSE"
    FINISHING = "Finishing"
    RESERVED = "Reserved"
    UNAVAILABLE = "Unavailable"
    FAULTED = "Faulted"


class ConfigurationKey:
    """Class to represent an OCPP configuration key"""
    def __init__(self, key: str, readonly: bool, value: str, reboot_required: bool = False):
        self.key = key
        self.readonly = readonly
        self.value = value
        self.reboot_required = reboot_required


class EVChargerSimulator:
    def __init__(self, config: Dict[str, Any] = None, gui_callback=None):
        if config is None:
            config = {}
            
        self.config = config
        self.gui_callback = gui_callback
        
        # Configuration
        self.charge_point_id = config.get('charge_point_id', 'd15charger2')
        self.password = config.get('password', '')
        self.central_system_url = config.get('central_system_url', 
                                            'ws://server.16.ocpp.us.qa.siemens.solidstudio.io')
        self.heartbeat_interval = config.get('heartbeat_interval', 60)
        self.use_tls = config.get('use_tls', False)
        self.ca_cert_path = config.get('ca_cert_path', None)
        
        # Charger properties
        self.charge_point_vendor = config.get('charge_point_vendor', 'SimulatorVendor')
        self.charge_point_model = config.get('charge_point_model', 'SimulatorModel')
        self.charge_point_serial_number = config.get('charge_point_serial_number', 'SIM001')
        self.firmware_version = config.get('firmware_version', '1.0.0')
        self.meter_type = config.get('meter_type', 'AC')
        self.meter_serial_number = config.get('meter_serial_number', 'METER001')
        
        # Number of connectors
        self.number_of_connectors = config.get('number_of_connectors', 1)
        
        self.websocket = None
        self.message_id = 0
        self.pending_requests: Dict[str, asyncio.Future] = {}
        self.is_connected = False
        self.boot_notification_accepted = False
        
        # Track transactions per connector
        self.connector_transactions: Dict[int, Optional[int]] = {}
        self.connector_status: Dict[int, ChargerStatus] = {}
        
        # Initialize connectors
        for i in range(1, self.number_of_connectors + 1):
            self.connector_status[i] = ChargerStatus.AVAILABLE
            self.connector_transactions[i] = None
        
        self.max_reconnect_attempts = 5
        self.reconnect_attempts = 0
        
        # Initialize configuration keys with default OCPP 1.6 values
        self.configuration_keys: Dict[str, ConfigurationKey] = self._initialize_default_config_keys()
        
        # Load custom configuration keys from config if provided
        if 'configuration_keys' in config:
            self._load_custom_config_keys(config['configuration_keys'])
    
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
            "MeterValueSampleInterval": ConfigurationKey("MeterValueSampleInterval", False, "20"),
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
        }
        
        return keys
    
    def _load_custom_config_keys(self, custom_keys: List[Dict[str, Any]]):
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
        """Get list of configuration keys for GUI display"""
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
        
    def log(self, message: str, level: str = "INFO"):
        """Log message and update GUI if callback is available"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_message = f"[{timestamp}] {level}: {message}"
        
        if level == "ERROR":
            logger.error(message)
        elif level == "WARNING":
            logger.warning(message)
        else:
            logger.info(message)
        
        if self.gui_callback:
            self.gui_callback(log_message)
        
    def get_next_message_id(self) -> str:
        """Generate unique message ID"""
        self.message_id += 1
        return str(self.message_id)
    
    def create_auth_uri(self) -> str:
        """Create URI with basic auth embedded for compatibility"""
        # Parse the URL
        parsed = urllib.parse.urlparse(self.central_system_url)
        
        # Create the auth string
        auth_string = f"{self.charge_point_id}:{self.password}"
        
        # Reconstruct URL with auth embedded
        if parsed.scheme == "ws":
            scheme = "ws"
        elif parsed.scheme == "wss":
            scheme = "wss"
        else:
            scheme = "ws"
            
        # Build the full URI with auth and path
        auth_uri = f"{scheme}://{auth_string}@{parsed.netloc}{parsed.path}/{self.charge_point_id}"
        
        return auth_uri
    
    def create_auth_header(self) -> str:
        """Create Basic Authentication header"""
        credentials = f"{self.charge_point_id}:{self.password}"
        encoded_credentials = base64.b64encode(credentials.encode()).decode()
        return f"Basic {encoded_credentials}"
    
    def _create_ssl_context(self) -> Optional[ssl.SSLContext]:
        """Create SSL context for TLS connection"""
        if not self.use_tls:
            return None
            
        context = ssl.create_default_context()
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        
        if self.ca_cert_path:
            try:
                context.load_verify_locations(self.ca_cert_path)
                self.log(f"Loaded CA certificate: {self.ca_cert_path}")
            except Exception as e:
                self.log(f"Failed to load CA certificate: {e}", "ERROR")
        
        return context
    
    async def connect(self):
        """Connect to the Central System"""
        # Try multiple connection methods for compatibility
        connection_methods = [
            self._connect_with_headers,
            self._connect_with_embedded_auth,
            self._connect_basic
        ]
        
        for i, method in enumerate(connection_methods):
            try:
                self.log(f"Trying connection method {i + 1}/3...")
                await method()
                if self.is_connected:
                    self.log("Successfully connected to Central System")
                    self.reconnect_attempts = 0
                    
                    # Start message handler and boot notification
                    await asyncio.gather(
                        self.message_handler(),
                        self.send_boot_notification(),
                        return_exceptions=True
                    )
                    return
                    
            except websockets.exceptions.InvalidStatus as e:
                if e.response.status_code == 401:
                    self.log("Authentication failed! Check your charge point ID and password.", "ERROR")
                    self.log(f"Charge Point ID: {self.charge_point_id}")
                    self.log("Please verify your credentials with the OCPP server administrator.", "ERROR")
                    return
                else:
                    self.log(f"Method {i + 1} failed with status {e.response.status_code}", "WARNING")
                    
            except Exception as e:
                self.log(f"Connection method {i + 1} failed: {e}", "WARNING")
        
        # If all methods failed
        self.log("All connection methods failed", "ERROR")
        await self.handle_connection_failure()
    
    async def _connect_with_headers(self):
        """Try connection with headers (newer websockets versions)"""
        uri = f"{self.central_system_url}/{self.charge_point_id}"
        headers = {
            "Authorization": self.create_auth_header()
        }
        ssl_context = self._create_ssl_context()
        
        self.log(f"Connecting with headers to: {uri}")
        
        try:
            # Try with additional_headers first
            self.websocket = await websockets.connect(
                uri,
                ssl=ssl_context,
                subprotocols=['ocpp1.6'],
                additional_headers=headers,
                ping_interval=20,
                ping_timeout=10
            )
        except TypeError:
            try:
                # Try with extra_headers
                self.websocket = await websockets.connect(
                    uri,
                    ssl=ssl_context,
                    subprotocols=['ocpp1.6'],
                    extra_headers=headers
                )
            except TypeError:
                # Neither parameter works
                raise Exception("Headers not supported in this websockets version")
        
        self.is_connected = True
    
    async def _connect_with_embedded_auth(self):
        """Try connection with embedded auth in URI"""
        auth_uri = self.create_auth_uri()
        ssl_context = self._create_ssl_context()
        self.log(f"Connecting with embedded auth to: {auth_uri}")
        
        self.websocket = await websockets.connect(
            auth_uri,
            ssl=ssl_context,
            subprotocols=['ocpp1.6']
        )
        self.is_connected = True
    
    async def _connect_basic(self):
        """Try basic connection without auth (some servers allow this)"""
        uri = f"{self.central_system_url}/{self.charge_point_id}"
        ssl_context = self._create_ssl_context()
        self.log(f"Connecting without auth to: {uri}")
        
        self.websocket = await websockets.connect(
            uri,
            ssl=ssl_context,
            subprotocols=['ocpp1.6']
        )
        self.is_connected = True
    
    async def handle_connection_failure(self):
        """Handle connection failures with limited retries"""
        self.reconnect_attempts += 1
        
        if self.reconnect_attempts >= self.max_reconnect_attempts:
            self.log(f"Max reconnection attempts ({self.max_reconnect_attempts}) reached. Giving up.", "ERROR")
            return
        
        self.log(f"Reconnection attempt {self.reconnect_attempts}/{self.max_reconnect_attempts} in 5 seconds...")
        await asyncio.sleep(5)
        await self.connect()
    
    async def message_handler(self):
        """Handle incoming messages from Central System"""
        try:
            async for message in self.websocket:
                await self.handle_message(message)
        except websockets.exceptions.ConnectionClosed:
            self.log("Connection closed by server", "WARNING")
            self.is_connected = False
            self.boot_notification_accepted = False
            await self.handle_connection_failure()
        except Exception as e:
            self.log(f"Message handler error: {e}", "ERROR")
            self.is_connected = False
            await self.handle_connection_failure()
    
    async def handle_message(self, raw_message: str):
        """Process incoming OCPP message"""
        try:
            message = json.loads(raw_message)
            self.log(f"Received: {message}")
            
            message_type = message[0]
            
            if message_type == MessageType.CALL.value:
                await self.handle_call(message)
            elif message_type == MessageType.CALL_RESULT.value:
                await self.handle_call_result(message)
            elif message_type == MessageType.CALL_ERROR.value:
                await self.handle_call_error(message)
                
        except Exception as e:
            self.log(f"Error handling message: {e}", "ERROR")
    
    async def handle_call(self, message: list):
        """Handle incoming request from Central System"""
        _, message_id, action, payload = message
        
        handlers = {
            "Reset": self.handle_reset,
            "RemoteStartTransaction": self.handle_remote_start_transaction,
            "RemoteStopTransaction": self.handle_remote_stop_transaction,
            "GetConfiguration": self.handle_get_configuration,
            "ChangeConfiguration": self.handle_change_configuration,
            "ClearCache": self.handle_clear_cache,
            "TriggerMessage": self.handle_trigger_message
        }
        
        handler = handlers.get(action)
        if handler:
            await handler(message_id, payload)
        else:
            await self.send_call_error(
                message_id,
                "NotImplemented",
                f"Action {action} not implemented"
            )
    
    async def handle_call_result(self, message: list):
        """Handle response from Central System"""
        _, message_id, payload = message
        
        if message_id in self.pending_requests:
            self.pending_requests[message_id].set_result(payload)
            del self.pending_requests[message_id]
    
    async def handle_call_error(self, message: list):
        """Handle error response from Central System"""
        _, message_id, error_code, error_description, error_details = message
        
        if message_id in self.pending_requests:
            self.pending_requests[message_id].set_exception(
                Exception(f"{error_code}: {error_description}")
            )
            del self.pending_requests[message_id]
    
    async def send_call(self, action: str, payload: dict) -> dict:
        """Send request to Central System and wait for response"""
        if not self.is_connected or not self.websocket:
            raise Exception("Not connected to Central System")
            
        message_id = self.get_next_message_id()
        message = [MessageType.CALL.value, message_id, action, payload]
        
        # Create future for response
        future = asyncio.get_event_loop().create_future()
        self.pending_requests[message_id] = future
        
        # Send message
        self.log(f"Sending: {message}")
        await self.websocket.send(json.dumps(message))
        
        # Wait for response
        try:
            response = await asyncio.wait_for(future, timeout=30)
            return response
        except asyncio.TimeoutError:
            if message_id in self.pending_requests:
                del self.pending_requests[message_id]
            raise Exception(f"Timeout waiting for response to {action}")
    
    async def send_call_result(self, message_id: str, payload: dict):
        """Send response to Central System"""
        if not self.is_connected or not self.websocket:
            return
            
        message = [MessageType.CALL_RESULT.value, message_id, payload]
        self.log(f"Sending response: {message}")
        await self.websocket.send(json.dumps(message))
    
    async def send_call_error(self, message_id: str, error_code: str, 
                            error_description: str, error_details: dict = None):
        """Send error response to Central System"""
        if not self.is_connected or not self.websocket:
            return
            
        message = [
            MessageType.CALL_ERROR.value,
            message_id,
            error_code,
            error_description,
            error_details or {}
        ]
        self.log(f"Sending error: {message}")
        await self.websocket.send(json.dumps(message))
    
    async def send_boot_notification(self):
        """Send BootNotification to Central System"""
        payload = {
            "chargePointVendor": self.charge_point_vendor,
            "chargePointModel": self.charge_point_model,
            "chargePointSerialNumber": self.charge_point_serial_number,
            "chargeBoxSerialNumber": self.charge_point_serial_number,
            "firmwareVersion": self.firmware_version,
            "iccid": "",
            "imsi": "",
            "meterType": self.meter_type,
            "meterSerialNumber": self.meter_serial_number
        }
        
        try:
            response = await self.send_call(OCPPAction.BOOT_NOTIFICATION.value, payload)
            
            if response.get("status") == "Accepted":
                self.log("BootNotification accepted")
                self.boot_notification_accepted = True
                asyncio.create_task(self.heartbeat_loop())
                # Send initial status for all connectors
                for connector_id in range(1, self.number_of_connectors + 1):
                    await self.send_status_notification(connector_id, ChargerStatus.AVAILABLE)
            else:
                self.log(f"BootNotification rejected: {response}", "WARNING")
                # Retry after interval
                await asyncio.sleep(response.get("interval", 60))
                await self.send_boot_notification()
                
        except Exception as e:
            self.log(f"Error sending BootNotification: {e}", "ERROR")
    
    async def heartbeat_loop(self):
        """Send periodic heartbeat messages"""
        while self.is_connected and self.boot_notification_accepted:
            try:
                await asyncio.sleep(self.heartbeat_interval)
                if self.is_connected:  # Check again after sleep
                    response = await self.send_call(OCPPAction.HEARTBEAT.value, {})
                    self.log(f"Heartbeat sent, current time: {response.get('currentTime')}")
            except Exception as e:
                self.log(f"Error sending heartbeat: {e}", "ERROR")
                break
    
    async def send_status_notification(self, connector_id: int, 
                                     status: ChargerStatus, 
                                     error_code: str = "NoError"):
        """Send StatusNotification to Central System"""
        # Validate connector ID
        if connector_id < 0 or connector_id > self.number_of_connectors:
            self.log(f"Invalid connector ID: {connector_id}. Valid range: 0-{self.number_of_connectors}", "ERROR")
            return
            
        payload = {
            "connectorId": connector_id,
            "status": status.value,
            "errorCode": error_code,
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }
        
        try:
            await self.send_call(OCPPAction.STATUS_NOTIFICATION.value, payload)
            if connector_id > 0:  # Only update status for actual connectors, not connector 0
                self.connector_status[connector_id] = status
            self.log(f"Status notification sent: Connector {connector_id} - {status.value}")
        except Exception as e:
            self.log(f"Error sending status notification: {e}", "ERROR")
    
    async def start_transaction(self, id_tag: str, connector_id: int = 1):
        """Start a charging transaction"""
        # Validate connector ID
        if connector_id < 1 or connector_id > self.number_of_connectors:
            self.log(f"Invalid connector ID: {connector_id}. Valid range: 1-{self.number_of_connectors}", "ERROR")
            return
            
        # Check if connector is available
        if self.connector_status.get(connector_id) != ChargerStatus.AVAILABLE:
            self.log(f"Connector {connector_id} is not available. Current status: {self.connector_status.get(connector_id).value}", "WARNING")
            return
            
        # Update status to Preparing
        await self.send_status_notification(connector_id, ChargerStatus.PREPARING)
        
        # Authorize the ID tag
        auth_payload = {"idTag": id_tag}
        auth_response = await self.send_call(OCPPAction.AUTHORIZE.value, auth_payload)
        
        if auth_response.get("idTagInfo", {}).get("status") != "Accepted":
            self.log(f"Authorization failed for {id_tag}", "WARNING")
            await self.send_status_notification(connector_id, ChargerStatus.AVAILABLE)
            return
        
        # Start transaction
        payload = {
            "connectorId": connector_id,
            "idTag": id_tag,
            "meterStart": 0,
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }
        
        try:
            response = await self.send_call(OCPPAction.START_TRANSACTION.value, payload)
            transaction_id = response.get("transactionId")
            self.connector_transactions[connector_id] = transaction_id
            self.log(f"Transaction started on connector {connector_id}: {transaction_id}")
            
            # Update status to Charging
            await self.send_status_notification(connector_id, ChargerStatus.CHARGING)
            
            # Start sending meter values
            asyncio.create_task(self.send_meter_values_loop(connector_id, transaction_id))
            
        except Exception as e:
            self.log(f"Error starting transaction: {e}", "ERROR")
            await self.send_status_notification(connector_id, ChargerStatus.AVAILABLE)
    
    async def stop_transaction(self, transaction_id: int = None, connector_id: int = None):
        """Stop a charging transaction"""
        # If no transaction ID provided, try to find it by connector ID
        if transaction_id is None:
            if connector_id is None:
                # Find first active transaction
                for conn_id, trans_id in self.connector_transactions.items():
                    if trans_id is not None:
                        transaction_id = trans_id
                        connector_id = conn_id
                        break
            else:
                transaction_id = self.connector_transactions.get(connector_id)
        
        if transaction_id is None:
            self.log("No active transaction to stop", "WARNING")
            return
        
        # Find connector ID if not provided
        if connector_id is None:
            for conn_id, trans_id in self.connector_transactions.items():
                if trans_id == transaction_id:
                    connector_id = conn_id
                    break
        
        payload = {
            "transactionId": transaction_id,
            "meterStop": 10000,  # Example meter value
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }
        
        try:
            response = await self.send_call(OCPPAction.STOP_TRANSACTION.value, payload)
            self.log(f"Transaction stopped on connector {connector_id}: {response}")
            
            if connector_id:
                self.connector_transactions[connector_id] = None
                # Update status to Available
                await self.send_status_notification(connector_id, ChargerStatus.AVAILABLE)
            
        except Exception as e:
            self.log(f"Error stopping transaction: {e}", "ERROR")
    
    async def send_meter_values_loop(self, connector_id: int, transaction_id: int):
        """Send periodic meter values during charging"""
        meter_value = 0
        
        while (self.connector_transactions.get(connector_id) == transaction_id and 
               self.connector_status.get(connector_id) == ChargerStatus.CHARGING):
            await asyncio.sleep(60)  # Send every minute
            
            meter_value += 100  # Increment meter value
            
            payload = {
                "connectorId": connector_id,
                "transactionId": transaction_id,
                "meterValue": [{
                    "timestamp": datetime.utcnow().isoformat() + "Z",
                    "sampledValue": [{
                        "value": str(meter_value),
                        "unit": "Wh",
                        "measurand": "Energy.Active.Import.Register"
                    }]
                }]
            }
            
            try:
                await self.send_call(OCPPAction.METER_VALUES.value, payload)
                self.log(f"Meter values sent for connector {connector_id}: {meter_value} Wh")
            except Exception as e:
                self.log(f"Error sending meter values: {e}", "ERROR")
                break
    
    # Request handlers
    async def handle_reset(self, message_id: str, payload: dict):
        """Handle Reset request"""
        self.log(f"Reset request received: {payload}")
        await self.send_call_result(message_id, {"status": "Accepted"})
        
        # Simulate reset
        await asyncio.sleep(2)
        self.log("Simulating reset...")
        self.is_connected = False
        await self.websocket.close()
    
    async def handle_remote_start_transaction(self, message_id: str, payload: dict):
        """Handle RemoteStartTransaction request"""
        self.log(f"RemoteStartTransaction received: {payload}")
        await self.send_call_result(message_id, {"status": "Accepted"})
        
        # Start transaction
        await self.start_transaction(
            payload.get("idTag"),
            payload.get("connectorId", 1)
        )
    
    async def handle_remote_stop_transaction(self, message_id: str, payload: dict):
        """Handle RemoteStopTransaction request"""
        self.log(f"RemoteStopTransaction received: {payload}")
        await self.send_call_result(message_id, {"status": "Accepted"})
        
        # Stop transaction
        await self.stop_transaction(payload.get("transactionId"))
    
    async def handle_get_configuration(self, message_id: str, payload: dict):
        """Handle GetConfiguration request"""
        self.log(f"GetConfiguration received: {payload}")
        
        requested_keys = payload.get("key", [])
        
        configuration_keys = []
        unknown_keys = []
        
        if not requested_keys:
            # Return all keys
            for config_key in self.configuration_keys.values():
                configuration_keys.append({
                    "key": config_key.key,
                    "readonly": config_key.readonly,
                    "value": config_key.value
                })
        else:
            # Return only requested keys
            for key_name in requested_keys:
                if key_name in self.configuration_keys:
                    config_key = self.configuration_keys[key_name]
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
        
        await self.send_call_result(message_id, response)
        self.log(f"Sent {len(configuration_keys)} configuration keys")
    
    async def handle_change_configuration(self, message_id: str, payload: dict):
        """Handle ChangeConfiguration request"""
        self.log(f"ChangeConfiguration received: {payload}")
        
        key = payload.get("key")
        value = payload.get("value")
        
        if not key or value is None:
            await self.send_call_result(message_id, {"status": "Rejected"})
            return
        
        status = self.update_configuration_key(key, value)
        
        await self.send_call_result(message_id, {"status": status})
        
        if status == "Accepted":
            self.log(f"Configuration key '{key}' updated to '{value}'")
        elif status == "RebootRequired":
            self.log(f"Configuration key '{key}' updated to '{value}' (reboot required)")
        elif status == "NotSupported":
            self.log(f"Configuration key '{key}' not supported", "WARNING")
        else:
            self.log(f"Failed to update configuration key '{key}'", "WARNING")
    
    async def handle_clear_cache(self, message_id: str, payload: dict):
        """Handle ClearCache request"""
        self.log(f"ClearCache received: {payload}")
        await self.send_call_result(message_id, {"status": "Accepted"})
    
    async def handle_trigger_message(self, message_id: str, payload: dict):
        """Handle TriggerMessage request"""
        self.log(f"TriggerMessage received: {payload}")
        
        requested_message = payload.get("requestedMessage")
        
        if requested_message == "BootNotification":
            await self.send_call_result(message_id, {"status": "Accepted"})
            await self.send_boot_notification()
        elif requested_message == "Heartbeat":
            await self.send_call_result(message_id, {"status": "Accepted"})
            await self.send_call(OCPPAction.HEARTBEAT.value, {})
        elif requested_message == "StatusNotification":
            await self.send_call_result(message_id, {"status": "Accepted"})
            connector_id = payload.get("connectorId", 1)
            await self.send_status_notification(
                connector_id, 
                self.connector_status.get(connector_id, ChargerStatus.AVAILABLE)
            )
        else:
            await self.send_call_result(message_id, {"status": "NotImplemented"})
    
    async def disconnect(self):
        """Disconnect from Central System"""
        self.is_connected = False
        if self.websocket:
            await self.websocket.close()
        self.log("Disconnected from Central System")
    
    def get_active_transactions(self) -> List[Dict[str, Any]]:
        """Get list of active transactions"""
        active_transactions = []
        for connector_id, transaction_id in self.connector_transactions.items():
            if transaction_id is not None:
                active_transactions.append({
                    'connector_id': connector_id,
                    'transaction_id': transaction_id,
                    'status': self.connector_status.get(connector_id, ChargerStatus.AVAILABLE).value
                })
        return active_transactions


class ConfigurationDialog(tk.Toplevel):
    """Dialog for managing configuration keys"""
    def __init__(self, parent, config_keys: List[Dict[str, Any]]):
        super().__init__(parent)
        self.parent = parent
        self.config_keys = config_keys.copy()
        self.result = None
        
        self.title("Configuration Keys Management")
        self.geometry("800x600")
        
        # Make dialog modal
        self.transient(parent)
        self.grab_set()
        
        self.setup_ui()
        
        # Center the dialog
        self.update_idletasks()
        x = (self.winfo_screenwidth() // 2) - (self.winfo_width() // 2)
        y = (self.winfo_screenheight() // 2) - (self.winfo_height() // 2)
        self.geometry(f"+{x}+{y}")

    def setup_ui(self):
        """Setup the dialog UI"""
        # Top frame with add button
        top_frame = ttk.Frame(self)
        top_frame.pack(fill=tk.X, padx=10, pady=5)
        
        ttk.Button(top_frame, text="Add Key", command=self.add_key).pack(side=tk.LEFT)
        ttk.Button(top_frame, text="Delete Selected", command=self.delete_selected).pack(side=tk.LEFT, padx=(5, 0))
        
        # Treeview for configuration keys
        tree_frame = ttk.Frame(self)
        tree_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        # Scrollbars
        vsb = ttk.Scrollbar(tree_frame, orient="vertical")
        hsb = ttk.Scrollbar(tree_frame, orient="horizontal")
        
        # Treeview
        self.tree = ttk.Treeview(tree_frame, 
                                columns=('value', 'readonly', 'reboot_required'),
                                yscrollcommand=vsb.set,
                                xscrollcommand=hsb.set)
        
        vsb.config(command=self.tree.yview)
        hsb.config(command=self.tree.xview)
        
        # Configure columns
        self.tree.heading('#0', text='Key')
        self.tree.heading('value', text='Value')
        self.tree.heading('readonly', text='Read Only')
        self.tree.heading('reboot_required', text='Reboot Required')
        
        self.tree.column('#0', width=250)
        self.tree.column('value', width=250)
        self.tree.column('readonly', width=100)
        self.tree.column('reboot_required', width=120)
        
        # Pack treeview and scrollbars
        self.tree.grid(row=0, column=0, sticky='nsew')
        vsb.grid(row=0, column=1, sticky='ns')
        hsb.grid(row=1, column=0, sticky='ew')
        
        tree_frame.grid_rowconfigure(0, weight=1)
        tree_frame.grid_columnconfigure(0, weight=1)
        
        # Populate tree
        self.populate_tree()
        
        # Bind double click for editing
        self.tree.bind('<Double-1>', self.on_double_click)
        
        # Bottom buttons
        button_frame = ttk.Frame(self)
        button_frame.pack(fill=tk.X, padx=10, pady=10)
        
        ttk.Button(button_frame, text="Save", command=self.save).pack(side=tk.RIGHT, padx=(5, 0))
        ttk.Button(button_frame, text="Cancel", command=self.destroy).pack(side=tk.RIGHT)

    def populate_tree(self):
        """Populate the tree with configuration keys"""
        # Clear tree
        for item in self.tree.get_children():
            self.tree.delete(item)
        
        # Add keys
        for key_data in sorted(self.config_keys, key=lambda x: x['key']):
            self.tree.insert('', 'end', 
                           text=key_data['key'],
                           values=(key_data['value'],
                                 'Yes' if key_data['readonly'] else 'No',
                                 'Yes' if key_data.get('reboot_required', False) else 'No'))

    def add_key(self):
        """Add a new configuration key"""
        dialog = KeyEditDialog(self, None)
        self.wait_window(dialog)
        
        if dialog.result:
            self.config_keys.append(dialog.result)
            self.populate_tree()

    def delete_selected(self):
        """Delete selected keys"""
        selected = self.tree.selection()
        if not selected:
            messagebox.showwarning("No Selection", "Please select keys to delete")
            return
        
        if messagebox.askyesno("Confirm Delete", "Delete selected configuration keys?"):
            for item in selected:
                key_name = self.tree.item(item)['text']
                self.config_keys = [k for k in self.config_keys if k['key'] != key_name]
            
            self.populate_tree()

    def on_double_click(self, event):
        """Handle double click on tree item"""
        item = self.tree.selection()
        if not item:
            return
        
        item = item[0]
        key_name = self.tree.item(item)['text']
        
        # Find the key data
        key_data = next((k for k in self.config_keys if k['key'] == key_name), None)
        if key_data:
            dialog = KeyEditDialog(self, key_data)
            self.wait_window(dialog)
            
            if dialog.result:
                # Update the key data
                for i, k in enumerate(self.config_keys):
                    if k['key'] == key_name:
                        self.config_keys[i] = dialog.result
                        break
                
                self.populate_tree()

    def save(self):
        """Save configuration keys"""
        self.result = self.config_keys
        self.destroy()


class KeyEditDialog(tk.Toplevel):
    """Dialog for editing a single configuration key"""
    def __init__(self, parent, key_data: Optional[Dict[str, Any]]):
        super().__init__(parent)
        self.parent = parent
        self.key_data = key_data
        self.result = None
        
        self.title("Edit Configuration Key" if key_data else "Add Configuration Key")
        self.geometry("400x250")
        
        # Make dialog modal
        self.transient(parent)
        self.grab_set()
        
        self.setup_ui()
        
        # Center the dialog
        self.update_idletasks()
        x = (self.winfo_screenwidth() // 2) - (self.winfo_width() // 2)
        y = (self.winfo_screenheight() // 2) - (self.winfo_height() // 2)
        self.geometry(f"+{x}+{y}")

    def setup_ui(self):
        """Setup the dialog UI"""
        frame = ttk.Frame(self, padding=20)
        frame.pack(fill=tk.BOTH, expand=True)
        
        # Key name
        ttk.Label(frame, text="Key Name:").grid(row=0, column=0, sticky=tk.W, pady=5)
        self.key_var = tk.StringVar(value=self.key_data['key'] if self.key_data else '')
        self.key_entry = ttk.Entry(frame, textvariable=self.key_var, width=40)
        self.key_entry.grid(row=0, column=1, pady=5)
        
        # Disable key editing for existing keys
        if self.key_data:
            self.key_entry.config(state='readonly')
        
        # Value
        ttk.Label(frame, text="Value:").grid(row=1, column=0, sticky=tk.W, pady=5)
        self.value_var = tk.StringVar(value=self.key_data['value'] if self.key_data else '')
        ttk.Entry(frame, textvariable=self.value_var, width=40).grid(row=1, column=1, pady=5)
        
        # Read only
        ttk.Label(frame, text="Read Only:").grid(row=2, column=0, sticky=tk.W, pady=5)
        self.readonly_var = tk.BooleanVar(value=self.key_data['readonly'] if self.key_data else False)
        ttk.Checkbutton(frame, variable=self.readonly_var).grid(row=2, column=1, sticky=tk.W, pady=5)
        
        # Reboot required
        ttk.Label(frame, text="Reboot Required:").grid(row=3, column=0, sticky=tk.W, pady=5)
        self.reboot_var = tk.BooleanVar(value=self.key_data.get('reboot_required', False) if self.key_data else False)
        ttk.Checkbutton(frame, variable=self.reboot_var).grid(row=3, column=1, sticky=tk.W, pady=5)
        
        # Buttons
        button_frame = ttk.Frame(frame)
        button_frame.grid(row=4, column=0, columnspan=2, pady=20)
        
        ttk.Button(button_frame, text="OK", command=self.ok_clicked).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Cancel", command=self.destroy).pack(side=tk.LEFT)

    def ok_clicked(self):
        """Handle OK button click"""
        key_name = self.key_var.get().strip()
        if not key_name:
            messagebox.showerror("Error", "Key name cannot be empty")
            return
        
        self.result = {
            'key': key_name,
            'value': self.value_var.get(),
            'readonly': self.readonly_var.get(),
            'reboot_required': self.reboot_var.get()
        }
        
        self.destroy()


class EVChargerSimulatorGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("EV Charger Simulator with OCPP 1.6")
        self.root.geometry("1000x700")
        
        self.simulator = None
        self.asyncio_thread = None
        self.loop = None
        self.config_keys = []
        
        self.setup_ui()
        
        # Handle window close
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

    def setup_ui(self):
        """Setup the GUI components"""
        # Create notebook for tabs
        notebook = ttk.Notebook(self.root)
        notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Configuration tab
        config_frame = ttk.Frame(notebook)
        notebook.add(config_frame, text="Configuration")
        self.setup_config_tab(config_frame)
        
        # Control tab
        control_frame = ttk.Frame(notebook)
        notebook.add(control_frame, text="Control")
        self.setup_control_tab(control_frame)
        
        # Log tab
        log_frame = ttk.Frame(notebook)
        notebook.add(log_frame, text="Logs")
        self.setup_log_tab(log_frame)

    def setup_config_tab(self, parent):
        """Setup configuration tab"""
        # Connection settings
        conn_frame = ttk.LabelFrame(parent, text="Connection Settings", padding=10)
        conn_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(conn_frame, text="Charge Point ID:").grid(row=0, column=0, sticky=tk.W, pady=2)
        self.cp_id_var = tk.StringVar(value="d15charger2")
        ttk.Entry(conn_frame, textvariable=self.cp_id_var, width=30).grid(row=0, column=1, sticky=tk.W, pady=2)
        
        ttk.Label(conn_frame, text="Central System URL:").grid(row=1, column=0, sticky=tk.W, pady=2)
        self.url_var = tk.StringVar(value="ws://server.16.ocpp.us.qa.siemens.solidstudio.io")# ev_charger_simulator_gui.py

import asyncio
import json
import base64
import logging
from datetime import datetime
from typing import Dict, Any, Optional, List
import websockets
from enum import Enum
import sys
import platform
import urllib.parse
import threading
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox, filedialog
import ssl

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class MessageType(Enum):
    CALL = 2
    CALL_RESULT = 3
    CALL_ERROR = 4


class OCPPAction(Enum):
    BOOT_NOTIFICATION = "BootNotification"
    HEARTBEAT = "Heartbeat"
    STATUS_NOTIFICATION = "StatusNotification"
    START_TRANSACTION = "StartTransaction"
    STOP_TRANSACTION = "StopTransaction"
    METER_VALUES = "MeterValues"
    AUTHORIZE = "Authorize"


class ChargerStatus(Enum):
    AVAILABLE = "Available"
    PREPARING = "Preparing"
    CHARGING = "Charging"
    SUSPENDED_EV = "SuspendedEV"
    SUSPENDED_EVSE = "SuspendedEVSE"
    FINISHING = "Finishing"
    RESERVED = "Reserved"
    UNAVAILABLE = "Unavailable"
    FAULTED = "Faulted"


class ConfigurationKey:
    """Class to represent an OCPP configuration key"""
    def __init__(self, key: str, readonly: bool, value: str, reboot_required: bool = False):
        self.key = key
        self.readonly = readonly
        self.value = value
        self.reboot_required = reboot_required


class EVChargerSimulator:
    def __init__(self, config: Dict[str, Any] = None, gui_callback=None):
        if config is None:
            config = {}
            
        self.config = config
        self.gui_callback = gui_callback
        
        # Configuration
        self.charge_point_id = config.get('charge_point_id', 'd15charger2')
        self.password = config.get('password', 'Annu12345!')
        self.central_system_url = config.get('central_system_url', 
                                            'ws://server.16.ocpp.us.qa.siemens.solidstudio.io')
        self.heartbeat_interval = config.get('heartbeat_interval', 60)
        self.use_tls = config.get('use_tls', False)
        self.ca_cert_path = config.get('ca_cert_path', None)
        
        # Charger properties
        self.charge_point_vendor = config.get('charge_point_vendor', 'SimulatorVendor')
        self.charge_point_model = config.get('charge_point_model', 'SimulatorModel')
        self.charge_point_serial_number = config.get('charge_point_serial_number', 'SIM001')
        self.firmware_version = config.get('firmware_version', '1.0.0')
        self.meter_type = config.get('meter_type', 'AC')
        self.meter_serial_number = config.get('meter_serial_number', 'METER001')
        
        # Number of connectors
        self.number_of_connectors = config.get('number_of_connectors', 1)
        
        self.websocket = None
        self.message_id = 0
        self.pending_requests: Dict[str, asyncio.Future] = {}
        self.is_connected = False
        self.boot_notification_accepted = False
        
        # Track transactions per connector
        self.connector_transactions: Dict[int, Optional[int]] = {}
        self.connector_status: Dict[int, ChargerStatus] = {}
        
        # Initialize connectors
        for i in range(1, self.number_of_connectors + 1):
            self.connector_status[i] = ChargerStatus.AVAILABLE
            self.connector_transactions[i] = None
        
        self.max_reconnect_attempts = 5
        self.reconnect_attempts = 0
        
        # Initialize configuration keys with default OCPP 1.6 values
        self.configuration_keys: Dict[str, ConfigurationKey] = self._initialize_default_config_keys()
        
        # Load custom configuration keys from config if provided
        if 'configuration_keys' in config:
            self._load_custom_config_keys(config['configuration_keys'])
    
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
        }
        
        return keys
    
    def _load_custom_config_keys(self, custom_keys: List[Dict[str, Any]]):
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
        """Get list of configuration keys for GUI display"""
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
        
    def log(self, message: str, level: str = "INFO"):
        """Log message and update GUI if callback is available"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_message = f"[{timestamp}] {level}: {message}"
        
        if level == "ERROR":
            logger.error(message)
        elif level == "WARNING":
            logger.warning(message)
        else:
            logger.info(message)
        
        if self.gui_callback:
            self.gui_callback(log_message)
        
    def get_next_message_id(self) -> str:
        """Generate unique message ID"""
        self.message_id += 1
        return str(self.message_id)
    
    def create_auth_uri(self) -> str:
        """Create URI with basic auth embedded for compatibility"""
        # Parse the URL
        parsed = urllib.parse.urlparse(self.central_system_url)
        
        # Create the auth string
        auth_string = f"{self.charge_point_id}:{self.password}"
        
        # Reconstruct URL with auth embedded
        if parsed.scheme == "ws":
            scheme = "ws"
        elif parsed.scheme == "wss":
            scheme = "wss"
        else:
            scheme = "ws"
            
        # Build the full URI with auth and path
        auth_uri = f"{scheme}://{auth_string}@{parsed.netloc}{parsed.path}/{self.charge_point_id}"
        
        return auth_uri
    
    def create_auth_header(self) -> str:
        """Create Basic Authentication header"""
        credentials = f"{self.charge_point_id}:{self.password}"
        encoded_credentials = base64.b64encode(credentials.encode()).decode()
        return f"Basic {encoded_credentials}"
    
    def _create_ssl_context(self) -> Optional[ssl.SSLContext]:
        """Create SSL context for TLS connection"""
        if not self.use_tls:
            return None
            
        context = ssl.create_default_context()
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        
        if self.ca_cert_path:
            try:
                context.load_verify_locations(self.ca_cert_path)
                self.log(f"Loaded CA certificate: {self.ca_cert_path}")
            except Exception as e:
                self.log(f"Failed to load CA certificate: {e}", "ERROR")
        
        return context
    
    async def connect(self):
        """Connect to the Central System"""
        # Try multiple connection methods for compatibility
        connection_methods = [
            self._connect_with_headers,
            self._connect_with_embedded_auth,
            self._connect_basic
        ]
        
        for i, method in enumerate(connection_methods):
            try:
                self.log(f"Trying connection method {i + 1}/3...")
                await method()
                if self.is_connected:
                    self.log("Successfully connected to Central System")
                    self.reconnect_attempts = 0
                    
                    # Start message handler and boot notification
                    await asyncio.gather(
                        self.message_handler(),
                        self.send_boot_notification(),
                        return_exceptions=True
                    )
                    return
                    
            except websockets.exceptions.InvalidStatus as e:
                if e.response.status_code == 401:
                    self.log("Authentication failed! Check your charge point ID and password.", "ERROR")
                    self.log(f"Charge Point ID: {self.charge_point_id}")
                    self.log("Please verify your credentials with the OCPP server administrator.", "ERROR")
                    return
                else:
                    self.log(f"Method {i + 1} failed with status {e.response.status_code}", "WARNING")
                    
            except Exception as e:
                self.log(f"Connection method {i + 1} failed: {e}", "WARNING")
        
        # If all methods failed
        self.log("All connection methods failed", "ERROR")
        await self.handle_connection_failure()
    
    async def _connect_with_headers(self):
        """Try connection with headers (newer websockets versions)"""
        uri = f"{self.central_system_url}/{self.charge_point_id}"
        headers = {
            "Authorization": self.create_auth_header()
        }
        ssl_context = self._create_ssl_context()
        
        self.log(f"Connecting with headers to: {uri}")
        
        try:
            # Try with additional_headers first
            self.websocket = await websockets.connect(
                uri,
                ssl=ssl_context,
                subprotocols=['ocpp1.6'],
                additional_headers=headers,
                ping_interval=20,
                ping_timeout=10
            )
        except TypeError:
            try:
                # Try with extra_headers
                self.websocket = await websockets.connect(
                    uri,
                    ssl=ssl_context,
                    subprotocols=['ocpp1.6'],
                    extra_headers=headers
                )
            except TypeError:
                # Neither parameter works
                raise Exception("Headers not supported in this websockets version")
        
        self.is_connected = True
    
    async def _connect_with_embedded_auth(self):
        """Try connection with embedded auth in URI"""
        auth_uri = self.create_auth_uri()
        ssl_context = self._create_ssl_context()
        self.log(f"Connecting with embedded auth to: {auth_uri}")
        
        self.websocket = await websockets.connect(
            auth_uri,
            ssl=ssl_context,
            subprotocols=['ocpp1.6']
        )
        self.is_connected = True
    
    async def _connect_basic(self):
        """Try basic connection without auth (some servers allow this)"""
        uri = f"{self.central_system_url}/{self.charge_point_id}"
        ssl_context = self._create_ssl_context()
        self.log(f"Connecting without auth to: {uri}")
        
        self.websocket = await websockets.connect(
            uri,
            ssl=ssl_context,
            subprotocols=['ocpp1.6']
        )
        self.is_connected = True
    
    async def handle_connection_failure(self):
        """Handle connection failures with limited retries"""
        self.reconnect_attempts += 1
        
        if self.reconnect_attempts >= self.max_reconnect_attempts:
            self.log(f"Max reconnection attempts ({self.max_reconnect_attempts}) reached. Giving up.", "ERROR")
            return
        
        self.log(f"Reconnection attempt {self.reconnect_attempts}/{self.max_reconnect_attempts} in 5 seconds...")
        await asyncio.sleep(5)
        await self.connect()
    
    async def message_handler(self):
        """Handle incoming messages from Central System"""
        try:
            async for message in self.websocket:
                await self.handle_message(message)
        except websockets.exceptions.ConnectionClosed:
            self.log("Connection closed by server", "WARNING")
            self.is_connected = False
            self.boot_notification_accepted = False
            await self.handle_connection_failure()
        except Exception as e:
            self.log(f"Message handler error: {e}", "ERROR")
            self.is_connected = False
            await self.handle_connection_failure()
    
    async def handle_message(self, raw_message: str):
        """Process incoming OCPP message"""
        try:
            message = json.loads(raw_message)
            self.log(f"Received: {message}")
            
            message_type = message[0]
            
            if message_type == MessageType.CALL.value:
                await self.handle_call(message)
            elif message_type == MessageType.CALL_RESULT.value:
                await self.handle_call_result(message)
            elif message_type == MessageType.CALL_ERROR.value:
                await self.handle_call_error(message)
                
        except Exception as e:
            self.log(f"Error handling message: {e}", "ERROR")
    
    async def handle_call(self, message: list):
        """Handle incoming request from Central System"""
        _, message_id, action, payload = message
        
        handlers = {
            "Reset": self.handle_reset,
            "RemoteStartTransaction": self.handle_remote_start_transaction,
            "RemoteStopTransaction": self.handle_remote_stop_transaction,
            "GetConfiguration": self.handle_get_configuration,
            "ChangeConfiguration": self.handle_change_configuration,
            "ClearCache": self.handle_clear_cache,
            "TriggerMessage": self.handle_trigger_message
        }
        
        handler = handlers.get(action)
        if handler:
            await handler(message_id, payload)
        else:
            await self.send_call_error(
                message_id,
                "NotImplemented",
                f"Action {action} not implemented"
            )
    
    async def handle_call_result(self, message: list):
        """Handle response from Central System"""
        _, message_id, payload = message
        
        if message_id in self.pending_requests:
            self.pending_requests[message_id].set_result(payload)
            del self.pending_requests[message_id]
    
    async def handle_call_error(self, message: list):
        """Handle error response from Central System"""
        _, message_id, error_code, error_description, error_details = message
        
        if message_id in self.pending_requests:
            self.pending_requests[message_id].set_exception(
                Exception(f"{error_code}: {error_description}")
            )
            del self.pending_requests[message_id]
    
    async def send_call(self, action: str, payload: dict) -> dict:
        """Send request to Central System and wait for response"""
        if not self.is_connected or not self.websocket:
            raise Exception("Not connected to Central System")
            
        message_id = self.get_next_message_id()
        message = [MessageType.CALL.value, message_id, action, payload]
        
        # Create future for response
        future = asyncio.get_event_loop().create_future()
        self.pending_requests[message_id] = future
        
        # Send message
        self.log(f"Sending: {message}")
        await self.websocket.send(json.dumps(message))
        
        # Wait for response
        try:
            response = await asyncio.wait_for(future, timeout=30)
            return response
        except asyncio.TimeoutError:
            if message_id in self.pending_requests:
                del self.pending_requests[message_id]
            raise Exception(f"Timeout waiting for response to {action}")
    
    async def send_call_result(self, message_id: str, payload: dict):
        """Send response to Central System"""
        if not self.is_connected or not self.websocket:
            return
            
        message = [MessageType.CALL_RESULT.value, message_id, payload]
        self.log(f"Sending response: {message}")
        await self.websocket.send(json.dumps(message))
    
    async def send_call_error(self, message_id: str, error_code: str, 
                            error_description: str, error_details: dict = None):
        """Send error response to Central System"""
        if not self.is_connected or not self.websocket:
            return
            
        message = [
            MessageType.CALL_ERROR.value,
            message_id,
            error_code,
            error_description,
            error_details or {}
        ]
        self.log(f"Sending error: {message}")
        await self.websocket.send(json.dumps(message))
    
    async def send_boot_notification(self):
        """Send BootNotification to Central System"""
        payload = {
            "chargePointVendor": self.charge_point_vendor,
            "chargePointModel": self.charge_point_model,
            "chargePointSerialNumber": self.charge_point_serial_number,
            "chargeBoxSerialNumber": self.charge_point_serial_number,
            "firmwareVersion": self.firmware_version,
            "iccid": "",
            "imsi": "",
            "meterType": self.meter_type,
            "meterSerialNumber": self.meter_serial_number
        }
        
        try:
            response = await self.send_call(OCPPAction.BOOT_NOTIFICATION.value, payload)
            
            if response.get("status") == "Accepted":
                self.log("BootNotification accepted")
                self.boot_notification_accepted = True
                asyncio.create_task(self.heartbeat_loop())
                # Send initial status for all connectors
                for connector_id in range(1, self.number_of_connectors + 1):
                    await self.send_status_notification(connector_id, ChargerStatus.AVAILABLE)
            else:
                self.log(f"BootNotification rejected: {response}", "WARNING")
                # Retry after interval
                await asyncio.sleep(response.get("interval", 60))
                await self.send_boot_notification()
                
        except Exception as e:
            self.log(f"Error sending BootNotification: {e}", "ERROR")
    
    async def heartbeat_loop(self):
        """Send periodic heartbeat messages"""
        while self.is_connected and self.boot_notification_accepted:
            try:
                await asyncio.sleep(self.heartbeat_interval)
                if self.is_connected:  # Check again after sleep
                    response = await self.send_call(OCPPAction.HEARTBEAT.value, {})
                    self.log(f"Heartbeat sent, current time: {response.get('currentTime')}")
            except Exception as e:
                self.log(f"Error sending heartbeat: {e}", "ERROR")
                break
    
    async def send_status_notification(self, connector_id: int, 
                                     status: ChargerStatus, 
                                     error_code: str = "NoError"):
        """Send StatusNotification to Central System"""
        # Validate connector ID
        if connector_id < 0 or connector_id > self.number_of_connectors:
            self.log(f"Invalid connector ID: {connector_id}. Valid range: 0-{self.number_of_connectors}", "ERROR")
            return
            
        payload = {
            "connectorId": connector_id,
            "status": status.value,
            "errorCode": error_code,
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }
        
        try:
            await self.send_call(OCPPAction.STATUS_NOTIFICATION.value, payload)
            if connector_id > 0:  # Only update status for actual connectors, not connector 0
                self.connector_status[connector_id] = status
            self.log(f"Status notification sent: Connector {connector_id} - {status.value}")
        except Exception as e:
            self.log(f"Error sending status notification: {e}", "ERROR")
    
    async def start_transaction(self, id_tag: str, connector_id: int = 1):
        """Start a charging transaction"""
        # Validate connector ID
        if connector_id < 1 or connector_id > self.number_of_connectors:
            self.log(f"Invalid connector ID: {connector_id}. Valid range: 1-{self.number_of_connectors}", "ERROR")
            return
            
        # Check if connector is available
        if self.connector_status.get(connector_id) != ChargerStatus.AVAILABLE:
            self.log(f"Connector {connector_id} is not available. Current status: {self.connector_status.get(connector_id).value}", "WARNING")
            return
            
        # Update status to Preparing
        await self.send_status_notification(connector_id, ChargerStatus.PREPARING)
        
        # Authorize the ID tag
        auth_payload = {"idTag": id_tag}
        auth_response = await self.send_call(OCPPAction.AUTHORIZE.value, auth_payload)
        
        if auth_response.get("idTagInfo", {}).get("status") != "Accepted":
            self.log(f"Authorization failed for {id_tag}", "WARNING")
            await self.send_status_notification(connector_id, ChargerStatus.AVAILABLE)
            return
        
        # Start transaction
        payload = {
            "connectorId": connector_id,
            "idTag": id_tag,
            "meterStart": 0,
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }
        
        try:
            response = await self.send_call(OCPPAction.START_TRANSACTION.value, payload)
            transaction_id = response.get("transactionId")
            self.connector_transactions[connector_id] = transaction_id
            self.log(f"Transaction started on connector {connector_id}: {transaction_id}")
            
            # Update status to Charging
            await self.send_status_notification(connector_id, ChargerStatus.CHARGING)
            
            # Start sending meter values
            asyncio.create_task(self.send_meter_values_loop(connector_id, transaction_id))
            
        except Exception as e:
            self.log(f"Error starting transaction: {e}", "ERROR")
            await self.send_status_notification(connector_id, ChargerStatus.AVAILABLE)
    
    async def stop_transaction(self, transaction_id: int = None, connector_id: int = None):
        """Stop a charging transaction"""
        # If no transaction ID provided, try to find it by connector ID
        if transaction_id is None:
            if connector_id is None:
                # Find first active transaction
                for conn_id, trans_id in self.connector_transactions.items():
                    if trans_id is not None:
                        transaction_id = trans_id
                        connector_id = conn_id
                        break
            else:
                transaction_id = self.connector_transactions.get(connector_id)
        
        if transaction_id is None:
            self.log("No active transaction to stop", "WARNING")
            return
        
        # Find connector ID if not provided
        if connector_id is None:
            for conn_id, trans_id in self.connector_transactions.items():
                if trans_id == transaction_id:
                    connector_id = conn_id
                    break
        
        payload = {
            "transactionId": transaction_id,
            "meterStop": 10000,  # Example meter value
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }
        
        try:
            response = await self.send_call(OCPPAction.STOP_TRANSACTION.value, payload)
            self.log(f"Transaction stopped on connector {connector_id}: {response}")
            
            if connector_id:
                self.connector_transactions[connector_id] = None
                # Update status to Available
                await self.send_status_notification(connector_id, ChargerStatus.AVAILABLE)
            
        except Exception as e:
            self.log(f"Error stopping transaction: {e}", "ERROR")
    
    async def send_meter_values_loop(self, connector_id: int, transaction_id: int):
        """Send periodic meter values during charging"""
        meter_value = 0
        
        while (self.connector_transactions.get(connector_id) == transaction_id and 
               self.connector_status.get(connector_id) == ChargerStatus.CHARGING):
            await asyncio.sleep(60)  # Send every minute
            
            meter_value += 100  # Increment meter value
            
            payload = {
                "connectorId": connector_id,
                "transactionId": transaction_id,
                "meterValue": [{
                    "timestamp": datetime.utcnow().isoformat() + "Z",
                    "sampledValue": [{
                        "value": str(meter_value),
                        "unit": "Wh",
                        "measurand": "Energy.Active.Import.Register"
                    }]
                }]
            }
            
            try:
                await self.send_call(OCPPAction.METER_VALUES.value, payload)
                self.log(f"Meter values sent for connector {connector_id}: {meter_value} Wh")
            except Exception as e:
                self.log(f"Error sending meter values: {e}", "ERROR")
                break
    
    # Request handlers
    async def handle_reset(self, message_id: str, payload: dict):
        """Handle Reset request"""
        self.log(f"Reset request received: {payload}")
        await self.send_call_result(message_id, {"status": "Accepted"})
        
        # Simulate reset
        await asyncio.sleep(2)
        self.log("Simulating reset...")
        self.is_connected = False
        await self.websocket.close()
    
    async def handle_remote_start_transaction(self, message_id: str, payload: dict):
        """Handle RemoteStartTransaction request"""
        self.log(f"RemoteStartTransaction received: {payload}")
        await self.send_call_result(message_id, {"status": "Accepted"})
        
        # Start transaction
        await self.start_transaction(
            payload.get("idTag"),
            payload.get("connectorId", 1)
        )
    
    async def handle_remote_stop_transaction(self, message_id: str, payload: dict):
        """Handle RemoteStopTransaction request"""
        self.log(f"RemoteStopTransaction received: {payload}")
        await self.send_call_result(message_id, {"status": "Accepted"})
        
        # Stop transaction
        await self.stop_transaction(payload.get("transactionId"))
    
    async def handle_get_configuration(self, message_id: str, payload: dict):
        """Handle GetConfiguration request"""
        self.log(f"GetConfiguration received: {payload}")
        
        requested_keys = payload.get("key", [])
        
        configuration_keys = []
        unknown_keys = []
        
        if not requested_keys:
            # Return all keys
            for config_key in self.configuration_keys.values():
                configuration_keys.append({
                    "key": config_key.key,
                    "readonly": config_key.readonly,
                    "value": config_key.value
                })
        else:
            # Return only requested keys
            for key_name in requested_keys:
                if key_name in self.configuration_keys:
                    config_key = self.configuration_keys[key_name]
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
        
        await self.send_call_result(message_id, response)
        self.log(f"Sent {len(configuration_keys)} configuration keys")
    
    async def handle_change_configuration(self, message_id: str, payload: dict):
        """Handle ChangeConfiguration request"""
        self.log(f"ChangeConfiguration received: {payload}")
        
        key = payload.get("key")
        value = payload.get("value")
        
        if not key or value is None:
            await self.send_call_result(message_id, {"status": "Rejected"})
            return
        
        status = self.update_configuration_key(key, value)
        
        await self.send_call_result(message_id, {"status": status})
        
        if status == "Accepted":
            self.log(f"Configuration key '{key}' updated to '{value}'")
        elif status == "RebootRequired":
            self.log(f"Configuration key '{key}' updated to '{value}' (reboot required)")
        elif status == "NotSupported":
            self.log(f"Configuration key '{key}' not supported", "WARNING")
        else:
            self.log(f"Failed to update configuration key '{key}'", "WARNING")
    
    async def handle_clear_cache(self, message_id: str, payload: dict):
        """Handle ClearCache request"""
        self.log(f"ClearCache received: {payload}")
        await self.send_call_result(message_id, {"status": "Accepted"})
    
    async def handle_trigger_message(self, message_id: str, payload: dict):
        """Handle TriggerMessage request"""
        self.log(f"TriggerMessage received: {payload}")
        
        requested_message = payload.get("requestedMessage")
        
        if requested_message == "BootNotification":
            await self.send_call_result(message_id, {"status": "Accepted"})
            await self.send_boot_notification()
        elif requested_message == "Heartbeat":
            await self.send_call_result(message_id, {"status": "Accepted"})
            await self.send_call(OCPPAction.HEARTBEAT.value, {})
        elif requested_message == "StatusNotification":
            await self.send_call_result(message_id, {"status": "Accepted"})
            connector_id = payload.get("connectorId", 1)
            await self.send_status_notification(
                connector_id, 
                self.connector_status.get(connector_id, ChargerStatus.AVAILABLE)
            )
        else:
            await self.send_call_result(message_id, {"status": "NotImplemented"})
    
    async def disconnect(self):
        """Disconnect from Central System"""
        self.is_connected = False
        if self.websocket:
            await self.websocket.close()
        self.log("Disconnected from Central System")
    
    def get_active_transactions(self) -> List[Dict[str, Any]]:
        """Get list of active transactions"""
        active_transactions = []
        for connector_id, transaction_id in self.connector_transactions.items():
            if transaction_id is not None:
                active_transactions.append({
                    'connector_id': connector_id,
                    'transaction_id': transaction_id,
                    'status': self.connector_status.get(connector_id, ChargerStatus.AVAILABLE).value
                })
        return active_transactions


class ConfigurationDialog(tk.Toplevel):
    """Dialog for managing configuration keys"""
    def __init__(self, parent, config_keys: List[Dict[str, Any]]):
        super().__init__(parent)
        self.parent = parent
        self.config_keys = config_keys.copy()
        self.result = None
        
        self.title("Configuration Keys Management")
        self.geometry("800x600")
        
        # Make dialog modal
        self.transient(parent)
        self.grab_set()
        
        self.setup_ui()
        
        # Center the dialog
        self.update_idletasks()
        x = (self.winfo_screenwidth() // 2) - (self.winfo_width() // 2)
        y = (self.winfo_screenheight() // 2) - (self.winfo_height() // 2)
        self.geometry(f"+{x}+{y}")

    def setup_ui(self):
        """Setup the dialog UI"""
        # Top frame with add button
        top_frame = ttk.Frame(self)
        top_frame.pack(fill=tk.X, padx=10, pady=5)
        
        ttk.Button(top_frame, text="Add Key", command=self.add_key).pack(side=tk.LEFT)
        ttk.Button(top_frame, text="Delete Selected", command=self.delete_selected).pack(side=tk.LEFT, padx=(5, 0))
        
        # Treeview for configuration keys
        tree_frame = ttk.Frame(self)
        tree_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        # Scrollbars
        vsb = ttk.Scrollbar(tree_frame, orient="vertical")
        hsb = ttk.Scrollbar(tree_frame, orient="horizontal")
        
        # Treeview
        self.tree = ttk.Treeview(tree_frame, 
                                columns=('value', 'readonly', 'reboot_required'),
                                yscrollcommand=vsb.set,
                                xscrollcommand=hsb.set)
        
        vsb.config(command=self.tree.yview)
        hsb.config(command=self.tree.xview)
        
        # Configure columns
        self.tree.heading('#0', text='Key')
        self.tree.heading('value', text='Value')
        self.tree.heading('readonly', text='Read Only')
        self.tree.heading('reboot_required', text='Reboot Required')
        
        self.tree.column('#0', width=250)
        self.tree.column('value', width=250)
        self.tree.column('readonly', width=100)
        self.tree.column('reboot_required', width=120)
        
        # Pack treeview and scrollbars
        self.tree.grid(row=0, column=0, sticky='nsew')
        vsb.grid(row=0, column=1, sticky='ns')
        hsb.grid(row=1, column=0, sticky='ew')
        
        tree_frame.grid_rowconfigure(0, weight=1)
        tree_frame.grid_columnconfigure(0, weight=1)
        
        # Populate tree
        self.populate_tree()
        
        # Bind double click for editing
        self.tree.bind('<Double-1>', self.on_double_click)
        
        # Bottom buttons
        button_frame = ttk.Frame(self)
        button_frame.pack(fill=tk.X, padx=10, pady=10)
        
        ttk.Button(button_frame, text="Save", command=self.save).pack(side=tk.RIGHT, padx=(5, 0))
        ttk.Button(button_frame, text="Cancel", command=self.destroy).pack(side=tk.RIGHT)

    def populate_tree(self):
        """Populate the tree with configuration keys"""
        # Clear tree
        for item in self.tree.get_children():
            self.tree.delete(item)
        
        # Add keys
        for key_data in sorted(self.config_keys, key=lambda x: x['key']):
            self.tree.insert('', 'end', 
                           text=key_data['key'],
                           values=(key_data['value'],
                                 'Yes' if key_data['readonly'] else 'No',
                                 'Yes' if key_data.get('reboot_required', False) else 'No'))

    def add_key(self):
        """Add a new configuration key"""
        dialog = KeyEditDialog(self, None)
        self.wait_window(dialog)
        
        if dialog.result:
            self.config_keys.append(dialog.result)
            self.populate_tree()

    def delete_selected(self):
        """Delete selected keys"""
        selected = self.tree.selection()
        if not selected:
            messagebox.showwarning("No Selection", "Please select keys to delete")
            return
        
        if messagebox.askyesno("Confirm Delete", "Delete selected configuration keys?"):
            for item in selected:
                key_name = self.tree.item(item)['text']
                self.config_keys = [k for k in self.config_keys if k['key'] != key_name]
            
            self.populate_tree()

    def on_double_click(self, event):
        """Handle double click on tree item"""
        item = self.tree.selection()
        if not item:
            return
        
        item = item[0]
        key_name = self.tree.item(item)['text']
        
        # Find the key data
        key_data = next((k for k in self.config_keys if k['key'] == key_name), None)
        if key_data:
            dialog = KeyEditDialog(self, key_data)
            self.wait_window(dialog)
            
            if dialog.result:
                # Update the key data
                for i, k in enumerate(self.config_keys):
                    if k['key'] == key_name:
                        self.config_keys[i] = dialog.result
                        break
                
                self.populate_tree()

    def save(self):
        """Save configuration keys"""
        self.result = self.config_keys
        self.destroy()


class KeyEditDialog(tk.Toplevel):
    """Dialog for editing a single configuration key"""
    def __init__(self, parent, key_data: Optional[Dict[str, Any]]):
        super().__init__(parent)
        self.parent = parent
        self.key_data = key_data
        self.result = None
        
        self.title("Edit Configuration Key" if key_data else "Add Configuration Key")
        self.geometry("400x250")
        
        # Make dialog modal
        self.transient(parent)
        self.grab_set()
        
        self.setup_ui()
        
        # Center the dialog
        self.update_idletasks()
        x = (self.winfo_screenwidth() // 2) - (self.winfo_width() // 2)
        y = (self.winfo_screenheight() // 2) - (self.winfo_height() // 2)
        self.geometry(f"+{x}+{y}")

    def setup_ui(self):
        """Setup the dialog UI"""
        frame = ttk.Frame(self, padding=20)
        frame.pack(fill=tk.BOTH, expand=True)
        
        # Key name
        ttk.Label(frame, text="Key Name:").grid(row=0, column=0, sticky=tk.W, pady=5)
        self.key_var = tk.StringVar(value=self.key_data['key'] if self.key_data else '')
        self.key_entry = ttk.Entry(frame, textvariable=self.key_var, width=40)
        self.key_entry.grid(row=0, column=1, pady=5)
        
        # Disable key editing for existing keys
        if self.key_data:
            self.key_entry.config(state='readonly')
        
        # Value
        ttk.Label(frame, text="Value:").grid(row=1, column=0, sticky=tk.W, pady=5)
        self.value_var = tk.StringVar(value=self.key_data['value'] if self.key_data else '')
        ttk.Entry(frame, textvariable=self.value_var, width=40).grid(row=1, column=1, pady=5)
        
        # Read only
        ttk.Label(frame, text="Read Only:").grid(row=2, column=0, sticky=tk.W, pady=5)
        self.readonly_var = tk.BooleanVar(value=self.key_data['readonly'] if self.key_data else False)
        ttk.Checkbutton(frame, variable=self.readonly_var).grid(row=2, column=1, sticky=tk.W, pady=5)
        
        # Reboot required
        ttk.Label(frame, text="Reboot Required:").grid(row=3, column=0, sticky=tk.W, pady=5)
        self.reboot_var = tk.BooleanVar(value=self.key_data.get('reboot_required', False) if self.key_data else False)
        ttk.Checkbutton(frame, variable=self.reboot_var).grid(row=3, column=1, sticky=tk.W, pady=5)
        
        # Buttons
        button_frame = ttk.Frame(frame)
        button_frame.grid(row=4, column=0, columnspan=2, pady=20)
        
        ttk.Button(button_frame, text="OK", command=self.ok_clicked).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Cancel", command=self.destroy).pack(side=tk.LEFT)

    def ok_clicked(self):
        """Handle OK button click"""
        key_name = self.key_var.get().strip()
        if not key_name:
            messagebox.showerror("Error", "Key name cannot be empty")
            return
        
        self.result = {
            'key': key_name,
            'value': self.value_var.get(),
            'readonly': self.readonly_var.get(),
            'reboot_required': self.reboot_var.get()
        }
        
        self.destroy()


class EVChargerSimulatorGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("EV Charger Simulator with OCPP 1.6")
        self.root.geometry("1000x700")
        
        self.simulator = None
        self.asyncio_thread = None
        self.loop = None
        self.config_keys = []
        
        self.setup_ui()
        
        # Handle window close
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

    def setup_ui(self):
        """Setup the GUI components"""
        # Create notebook for tabs
        notebook = ttk.Notebook(self.root)
        notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Configuration tab
        config_frame = ttk.Frame(notebook)
        notebook.add(config_frame, text="Configuration")
        self.setup_config_tab(config_frame)
        
        # Control tab
        control_frame = ttk.Frame(notebook)
        notebook.add(control_frame, text="Control")
        self.setup_control_tab(control_frame)
        
        # Log tab
        log_frame = ttk.Frame(notebook)
        notebook.add(log_frame, text="Logs")
        self.setup_log_tab(log_frame)

    def setup_config_tab(self, parent):
        """Setup configuration tab"""
        # Connection settings
        conn_frame = ttk.LabelFrame(parent, text="Connection Settings", padding=10)
        conn_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(conn_frame, text="Charge Point ID:").grid(row=0, column=0, sticky=tk.W, pady=2)
        self.cp_id_var = tk.StringVar(value="d15charger2")
        ttk.Entry(conn_frame, textvariable=self.cp_id_var, width=30).grid(row=0, column=1, sticky=tk.W, pady=2)
        
        ttk.Label(conn_frame, text="Central System URL:").grid(row=1, column=0, sticky=tk.W, pady=2)
        self.url_var = tk.StringVar(value="ws://server.16.ocpp.us.qa.siemens.solidstudio.io")
        ttk.Entry(conn_frame, textvariable=self.url_var, width=60).grid(row=1, column=1, sticky=tk.W, pady=2)
        
        ttk.Label(conn_frame, text="Password:").grid(row=2, column=0, sticky=tk.W, pady=2)
        self.password_var = tk.StringVar(value="Annu12345!")
        ttk.Entry(conn_frame, textvariable=self.password_var, width=30, show="*").grid(row=2, column=1, sticky=tk.W, pady=2)
        
        ttk.Label(conn_frame, text="Heartbeat Interval (s):").grid(row=3, column=0, sticky=tk.W, pady=2)
        self.heartbeat_var = tk.StringVar(value="60")
        ttk.Entry(conn_frame, textvariable=self.heartbeat_var, width=10).grid(row=3, column=1, sticky=tk.W, pady=2)
        
        # Configuration Keys button
        config_keys_btn = ttk.Button(conn_frame, text="Manage Configuration Keys", command=self.manage_config_keys)
        config_keys_btn.grid(row=4, column=1, sticky=tk.W, pady=10)
        
        # Security settings
        security_frame = ttk.LabelFrame(parent, text="Security Settings", padding=10)
        security_frame.pack(fill=tk.X, pady=5)
        
        # TLS Enable/Disable
        self.use_tls_var = tk.BooleanVar(value=False)
        tls_frame = ttk.Frame(security_frame)
        tls_frame.grid(row=0, column=0, columnspan=2, sticky=tk.W, pady=2)
        
        ttk.Checkbutton(tls_frame, text="Use TLS (WSS)", variable=self.use_tls_var, 
                       command=self.on_tls_toggle).pack(side=tk.LEFT)
        
        self.security_profile_label = ttk.Label(tls_frame, text="Security Profile: Basic Auth only", 
                                              foreground="blue")
        self.security_profile_label.pack(side=tk.LEFT, padx=(20, 0))
        
        # CA Certificate (only shown when TLS is enabled)
        self.cert_label = ttk.Label(security_frame, text="CA Certificate:")
        self.cert_label.grid(row=1, column=0, sticky=tk.W, pady=2)
        
        cert_frame = ttk.Frame(security_frame)
        cert_frame.grid(row=1, column=1, sticky=tk.W, pady=2)
        
        self.ca_cert_var = tk.StringVar()
        self.cert_entry = ttk.Entry(cert_frame, textvariable=self.ca_cert_var, width=50)
        self.cert_entry.pack(side=tk.LEFT)
        
        self.cert_browse_btn = ttk.Button(cert_frame, text="Browse", command=self.browse_certificate)
        self.cert_browse_btn.pack(side=tk.LEFT, padx=(5, 0))
        
        # Initially hide certificate options
        self.toggle_certificate_widgets()
        
        # URL helper buttons
        url_helper_frame = ttk.Frame(conn_frame)
        url_helper_frame.grid(row=5, column=1, sticky=tk.W, pady=5)
        
        ttk.Button(url_helper_frame, text="Set WS URL", 
                  command=lambda: self.set_url_protocol("ws")).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(url_helper_frame, text="Set WSS URL", 
                  command=lambda: self.set_url_protocol("wss")).pack(side=tk.LEFT)
        
        # Charger properties
        charger_frame = ttk.LabelFrame(parent, text="Charger Properties", padding=10)
        charger_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(charger_frame, text="Vendor:").grid(row=0, column=0, sticky=tk.W, pady=2)
        self.vendor_var = tk.StringVar(value="SimulatorVendor")
        ttk.Entry(charger_frame, textvariable=self.vendor_var, width=30).grid(row=0, column=1, sticky=tk.W, pady=2)
        
        ttk.Label(charger_frame, text="Model:").grid(row=1, column=0, sticky=tk.W, pady=2)
        self.model_var = tk.StringVar(value="SimulatorModel")
        ttk.Entry(charger_frame, textvariable=self.model_var, width=30).grid(row=1, column=1, sticky=tk.W, pady=2)
        
        ttk.Label(charger_frame, text="Serial Number:").grid(row=2, column=0, sticky=tk.W, pady=2)
        self.serial_var = tk.StringVar(value="SIM001")
        ttk.Entry(charger_frame, textvariable=self.serial_var, width=30).grid(row=2, column=1, sticky=tk.W, pady=2)
        
        ttk.Label(charger_frame, text="Firmware Version:").grid(row=3, column=0, sticky=tk.W, pady=2)
        self.firmware_var = tk.StringVar(value="1.0.0")
        ttk.Entry(charger_frame, textvariable=self.firmware_var, width=30).grid(row=3, column=1, sticky=tk.W, pady=2)
        
        # Number of connectors
        ttk.Label(charger_frame, text="Number of Connectors:").grid(row=4, column=0, sticky=tk.W, pady=2)
        self.num_connectors_var = tk.StringVar(value="1")
        ttk.Spinbox(charger_frame, textvariable=self.num_connectors_var, from_=1, to=10, width=10).grid(row=4, column=1, sticky=tk.W, pady=2)

    def manage_config_keys(self):
        """Open configuration keys management dialog"""
        # Get current keys from simulator if connected, otherwise use saved keys
        if self.simulator:
            self.config_keys = self.simulator.get_configuration_keys_list()
        
        dialog = ConfigurationDialog(self.root, self.config_keys)
        self.wait_window(dialog)
        
        if dialog.result:
            self.config_keys = dialog.result
            # Update simulator if connected
            if self.simulator:
                # Clear existing keys
                self.simulator.configuration_keys.clear()
                # Load new keys
                self.simulator._load_custom_config_keys(self.config_keys)

    def on_tls_toggle(self):
        """Handle TLS checkbox toggle"""
        self.toggle_certificate_widgets()
        self.update_security_profile_label()

    def toggle_certificate_widgets(self):
        """Show/hide certificate widgets based on TLS setting"""
        if self.use_tls_var.get():
            # Show certificate options
            self.cert_label.grid()
            self.cert_entry.master.grid()
        else:
            # Hide certificate options
            self.cert_label.grid_remove()
            self.cert_entry.master.grid_remove()

    def update_security_profile_label(self):
        """Update security profile label based on TLS setting"""
        if self.use_tls_var.get():
            self.security_profile_label.config(text="Security Profile: TLS with Basic Auth", foreground="green")
        else:
            self.security_profile_label.config(text="Security Profile: Basic Auth only", foreground="blue")

    def set_url_protocol(self, protocol):
        """Set URL protocol (ws or wss)"""
        current_url = self.url_var.get()
        
        # Remove existing protocol
        if current_url.startswith("ws://"):
            current_url = current_url[5:]
        elif current_url.startswith("wss://"):
            current_url = current_url[6:]
        
        # Add new protocol
        new_url = f"{protocol}://{current_url}"
        self.url_var.set(new_url)
        
        # Update TLS checkbox accordingly
        self.use_tls_var.set(protocol == "wss")
        self.on_tls_toggle()

    def setup_control_tab(self, parent):
        """Setup control tab"""
        # Connection control
        conn_control_frame = ttk.LabelFrame(parent, text="Connection Control", padding=10)
        conn_control_frame.pack(fill=tk.X, pady=5)
        
        self.connect_btn = ttk.Button(conn_control_frame, text="Connect", command=self.connect_charger)
        self.connect_btn.pack(side=tk.LEFT, padx=5)
        
        self.disconnect_btn = ttk.Button(conn_control_frame, text="Disconnect", command=self.disconnect_charger, state=tk.DISABLED)
        self.disconnect_btn.pack(side=tk.LEFT, padx=5)
        
        # Status display
        status_frame = ttk.LabelFrame(parent, text="Status", padding=10)
        status_frame.pack(fill=tk.X, pady=5)
        
        self.status_var = tk.StringVar(value="Disconnected")
        ttk.Label(status_frame, text="Connection Status:").pack(side=tk.LEFT)
        self.status_label = ttk.Label(status_frame, textvariable=self.status_var, foreground="red")
        self.status_label.pack(side=tk.LEFT, padx=(10, 0))
        
        # Connection info
        self.connection_info_var = tk.StringVar(value="")
        self.connection_info_label = ttk.Label(status_frame, textvariable=self.connection_info_var, foreground="gray")
        self.connection_info_label.pack(side=tk.LEFT, padx=(20, 0))
        
        # Manual message sending
        message_frame = ttk.LabelFrame(parent, text="Send Messages", padding=10)
        message_frame.pack(fill=tk.X, pady=5)
        
        # Row 1: Connector ID and Heartbeat
        row1_frame = ttk.Frame(message_frame)
        row1_frame.pack(fill=tk.X, pady=2)
        
        ttk.Label(row1_frame, text="Connector ID:").pack(side=tk.LEFT)
        self.connector_id_var = tk.StringVar(value="1")
        ttk.Spinbox(row1_frame, textvariable=self.connector_id_var, from_=0, to=10, width=5).pack(side=tk.LEFT, padx=(5, 20))
        
        ttk.Button(row1_frame, text="Send Heartbeat", command=self.send_heartbeat).pack(side=tk.LEFT, padx=5)
        
        # Row 2: Status buttons
        row2_frame = ttk.Frame(message_frame)
        row2_frame.pack(fill=tk.X, pady=2)
        
        ttk.Button(row2_frame, text="Send Status Available", command=lambda: self.send_status("Available")).pack(side=tk.LEFT, padx=5)
        ttk.Button(row2_frame, text="Send Status Charging", command=lambda: self.send_status("Charging")).pack(side=tk.LEFT, padx=5)
        ttk.Button(row2_frame, text="Send Status Unavailable", command=lambda: self.send_status("Unavailable")).pack(side=tk.LEFT, padx=5)
        ttk.Button(row2_frame, text="Send Status Faulted", command=lambda: self.send_status("Faulted")).pack(side=tk.LEFT, padx=5)
        
        # Transaction control
        transaction_frame = ttk.LabelFrame(parent, text="Transaction Control", padding=10)
        transaction_frame.pack(fill=tk.X, pady=5)
        
        # Transaction start row
        start_frame = ttk.Frame(transaction_frame)
        start_frame.pack(fill=tk.X, pady=2)
        
        ttk.Label(start_frame, text="ID Tag:").pack(side=tk.LEFT)
        self.id_tag_var = tk.StringVar(value="TestCard123")
        ttk.Entry(start_frame, textvariable=self.id_tag_var, width=20).pack(side=tk.LEFT, padx=5)
        
        ttk.Label(start_frame, text="Connector:").pack(side=tk.LEFT, padx=(10, 0))
        self.transaction_connector_var = tk.StringVar(value="1")
        ttk.Spinbox(start_frame, textvariable=self.transaction_connector_var, from_=1, to=10, width=5).pack(side=tk.LEFT, padx=5)
        
        ttk.Button(start_frame, text="Start Transaction", command=self.start_transaction).pack(side=tk.LEFT, padx=5)
        
        # Transaction stop row
        stop_frame = ttk.Frame(transaction_frame)
        stop_frame.pack(fill=tk.X, pady=2)
        
        ttk.Button(stop_frame, text="Stop Transaction", command=self.stop_transaction).pack(side=tk.LEFT, padx=5)
        ttk.Label(stop_frame, text="(Stops active transaction on selected connector)").pack(side=tk.LEFT, padx=5)
        
        # Active transactions display
        active_frame = ttk.LabelFrame(parent, text="Active Transactions", padding=10)
        active_frame.pack(fill=tk.X, pady=5)
        
        self.active_transactions_text = tk.Text(active_frame, height=3, width=60)
        self.active_transactions_text.pack(fill=tk.X)
        self.active_transactions_text.config(state=tk.DISABLED)

    def setup_log_tab(self, parent):
        """Setup log tab"""
        log_frame = ttk.Frame(parent)
        log_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Log text area
        self.log_text = scrolledtext.ScrolledText(log_frame, wrap=tk.WORD, width=100, height=30)
        self.log_text.pack(fill=tk.BOTH, expand=True)
        
        # Clear button
        ttk.Button(log_frame, text="Clear Logs", command=self.clear_logs).pack(pady=5)

    def browse_certificate(self):
        """Browse for CA certificate file"""
        filename = filedialog.askopenfilename(
            title="Select CA Certificate",
            filetypes=[("Certificate files", "*.pem *.crt *.cer"), ("All files", "*.*")]
        )
        if filename:
            self.ca_cert_var.set(filename)

    def update_log(self, message):
        """Update log display (thread-safe)"""
        def _update():
            self.log_text.insert(tk.END, message + "\n")
            self.log_text.see(tk.END)
        
        self.root.after(0, _update)

    def clear_logs(self):
        """Clear log display"""
        self.log_text.delete(1.0, tk.END)

    def apply_config(self):
        """Apply configuration to simulator"""
        try:
            num_connectors = int(self.num_connectors_var.get())
            if num_connectors < 1 or num_connectors > 10:
                messagebox.showerror("Error", "Number of connectors must be between 1 and 10")
                return
        except ValueError:
            messagebox.showerror("Error", "Invalid number of connectors")
            return
            
        config = {
            'charge_point_id': self.cp_id_var.get(),
            'password': self.password_var.get(),
            'central_system_url': self.url_var.get(),
            'heartbeat_interval': int(self.heartbeat_var.get()),
            'use_tls': self.use_tls_var.get(),
            'ca_cert_path': self.ca_cert_var.get() if self.ca_cert_var.get() else None,
            'charge_point_vendor': self.vendor_var.get(),
            'charge_point_model': self.model_var.get(),
            'charge_point_serial_number': self.serial_var.get(),
            'firmware_version': self.firmware_var.get(),
            'meter_serial_number': f"METER{self.cp_id_var.get()}",
            'number_of_connectors': num_connectors,
            'configuration_keys': self.config_keys
        }
        
        self.simulator = EVChargerSimulator(config, gui_callback=self.update_log)
        
        # Update connector spinbox maximum values
        self.connector_id_var.set("1")
        self.transaction_connector_var.set("1")

    def connect_charger(self):
        """Connect to the Central System"""
        if not self.cp_id_var.get() or not self.url_var.get() or not self.password_var.get():
            messagebox.showerror("Error", "Please fill in all required fields")
            return
        
        # Validate URL protocol matches TLS setting
        url = self.url_var.get()
        use_tls = self.use_tls_var.get()
        
        if use_tls and not url.startswith('wss://'):
            if messagebox.askyesno("URL Mismatch", 
                                 "TLS is enabled but URL doesn't use 'wss://'. Continue anyway?"):
                pass
            else:
                return
        elif not use_tls and not url.startswith('ws://'):
            if messagebox.askyesno("URL Mismatch", 
                                 "TLS is disabled but URL doesn't use 'ws://'. Continue anyway?"):
                pass
            else:
                return
        
        self.apply_config()
        
        # Update connection info
        connection_type = "WSS (TLS)" if use_tls else "WS (Plain)"
        self.connection_info_var.set(f"({connection_type})")
        
        # Start asyncio loop in separate thread
        self.asyncio_thread = threading.Thread(target=self.run_asyncio_loop, daemon=True)
        self.asyncio_thread.start()
        
        self.connect_btn.config(state=tk.DISABLED)
        self.disconnect_btn.config(state=tk.NORMAL)
        self.status_var.set("Connecting...")
        self.status_label.config(foreground="orange")

    def run_asyncio_loop(self):
        """Run asyncio loop in separate thread"""
        try:
            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)
            
            # Set event loop policy for Windows
            if platform.system() == 'Windows':
                asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
            
            self.loop.run_until_complete(self.simulator.connect())
            
            # Start periodic updates for active transactions
            if self.simulator and self.simulator.is_connected:
                self.root.after(0, self.update_status_connected)
                self.root.after(2000, self.periodic_transaction_update)
        except Exception as e:
            self.simulator.log(f"Connection error: {e}", "ERROR")
        finally:
            self.root.after(0, self.on_disconnected)
    
    def update_status_connected(self):
        """Update status when connected"""
        self.status_var.set("Connected")
        self.status_label.config(foreground="green")
        self.update_active_transactions()
    
    def periodic_transaction_update(self):
        """Periodically update active transactions display"""
        if self.simulator and self.simulator.is_connected:
            self.update_active_transactions()
            # Schedule next update
            self.root.after(5000, self.periodic_transaction_update)

    def disconnect_charger(self):
        """Disconnect from Central System"""
        if self.loop and self.simulator and self.simulator.is_connected:
            asyncio.run_coroutine_threadsafe(self.simulator.disconnect(), self.loop)
        
        self.on_disconnected()

    def on_disconnected(self):
        """Handle disconnection UI updates"""
        self.connect_btn.config(state=tk.NORMAL)
        self.disconnect_btn.config(state=tk.DISABLED)
        self.status_var.set("Disconnected")
        self.status_label.config(foreground="red")
        self.connection_info_var.set("")
        
        # Clear active transactions display
        self.active_transactions_text.config(state=tk.NORMAL)
        self.active_transactions_text.delete(1.0, tk.END)
        self.active_transactions_text.insert(tk.END, "Not connected")
        self.active_transactions_text.config(state=tk.DISABLED)

    def send_heartbeat(self):
        """Send heartbeat manually"""
        if self.loop and self.simulator and self.simulator.is_connected:
            asyncio.run_coroutine_threadsafe(self.simulator.send_call(OCPPAction.HEARTBEAT.value, {}), self.loop)
        else:
            messagebox.showwarning("Warning", "Not connected to Central System")

    def send_status(self, status):
        """Send status notification manually"""
        if self.loop and self.simulator and self.simulator.is_connected:
            try:
                connector_id = int(self.connector_id_var.get())
                status_enum = getattr(ChargerStatus, status.upper(), ChargerStatus.AVAILABLE)
                asyncio.run_coroutine_threadsafe(
                    self.simulator.send_status_notification(connector_id, status_enum), 
                    self.loop
                )
            except ValueError:
                messagebox.showerror("Error", "Invalid connector ID")
        else:
            messagebox.showwarning("Warning", "Not connected to Central System")

    def start_transaction(self):
        """Start a charging transaction"""
        if self.loop and self.simulator and self.simulator.is_connected:
            id_tag = self.id_tag_var.get()
            if not id_tag:
                messagebox.showerror("Error", "Please enter an ID tag")
                return
            try:
                connector_id = int(self.transaction_connector_var.get())
                asyncio.run_coroutine_threadsafe(
                    self.simulator.start_transaction(id_tag, connector_id), 
                    self.loop
                )
                # Update active transactions display
                self.root.after(1000, self.update_active_transactions)
            except ValueError:
                messagebox.showerror("Error", "Invalid connector ID")
        else:
            messagebox.showwarning("Warning", "Not connected to Central System")

    def stop_transaction(self):
        """Stop the current transaction"""
        if self.loop and self.simulator and self.simulator.is_connected:
            try:
                connector_id = int(self.transaction_connector_var.get())
                asyncio.run_coroutine_threadsafe(
                    self.simulator.stop_transaction(connector_id=connector_id), 
                    self.loop
                )
                # Update active transactions display
                self.root.after(1000, self.update_active_transactions)
            except ValueError:
                messagebox.showerror("Error", "Invalid connector ID")
        else:
            messagebox.showwarning("Warning", "Not connected to Central System")
    
    def update_active_transactions(self):
        """Update the active transactions display"""
        if self.simulator:
            active_transactions = self.simulator.get_active_transactions()
            
            self.active_transactions_text.config(state=tk.NORMAL)
            self.active_transactions_text.delete(1.0, tk.END)
            
            if active_transactions:
                for transaction in active_transactions:
                    text = f"Connector {transaction['connector_id']}: Transaction {transaction['transaction_id']} - {transaction['status']}\n"
                    self.active_transactions_text.insert(tk.END, text)
            else:
                self.active_transactions_text.insert(tk.END, "No active transactions")
            
            self.active_transactions_text.config(state=tk.DISABLED)

    def wait_window(self, window):
        """Wait for a window to be destroyed"""
        window.wait_window()

    def on_closing(self):
        """Handle window closing"""
        if self.simulator and self.simulator.is_connected:
            self.disconnect_charger()
        
        if self.loop:
            self.loop.call_soon_threadsafe(self.loop.stop)
        
        self.root.destroy()


def main():
    """Main function"""
    # Handle both GUI and CLI modes
    if len(sys.argv) > 1 and sys.argv[1] == "--cli":
        # CLI mode
        print("Running in CLI mode...")
        # Original CLI implementation would go here
        pass
    else:
        # GUI mode
        root = tk.Tk()
        app = EVChargerSimulatorGUI(root)
        root.mainloop()


if __name__ == "__main__":
    main()
        ttk.Entry(conn_frame, textvariable=self.url_var, width=60).grid(row=1, column=1, sticky=tk.W, pady=2)
        
        ttk.Label(conn_frame, text="Password:").grid(row=2, column=0, sticky=tk.W, pady=2)
        self.password_var = tk.StringVar(value="")
        ttk.Entry(conn_frame, textvariable=self.password_var, width=30, show="*").grid(row=2, column=1, sticky=tk.W, pady=2)
        
        ttk.Label(conn_frame, text="Heartbeat Interval (s):").grid(row=3, column=0, sticky=tk.W, pady=2)
        self.heartbeat_var = tk.StringVar(value="60")
        ttk.Entry(conn_frame, textvariable=self.heartbeat_var, width=10).grid(row=3, column=1, sticky=tk.W, pady=2)
        
        # Configuration Keys button
        config_keys_btn = ttk.Button(conn_frame, text="Manage Configuration Keys", command=self.manage_config_keys)
        config_keys_btn.grid(row=4, column=1, sticky=tk.W, pady=10)
        
        # Security settings
        security_frame = ttk.LabelFrame(parent, text="Security Settings", padding=10)
        security_frame.pack(fill=tk.X, pady=5)
        
        # TLS Enable/Disable
        self.use_tls_var = tk.BooleanVar(value=False)
        tls_frame = ttk.Frame(security_frame)
        tls_frame.grid(row=0, column=0, columnspan=2, sticky=tk.W, pady=2)
        
        ttk.Checkbutton(tls_frame, text="Use TLS (WSS)", variable=self.use_tls_var, 
                       command=self.on_tls_toggle).pack(side=tk.LEFT)
        
        self.security_profile_label = ttk.Label(tls_frame, text="Security Profile: Basic Auth only", 
                                              foreground="blue")
        self.security_profile_label.pack(side=tk.LEFT, padx=(20, 0))
        
        # CA Certificate (only shown when TLS is enabled)
        self.cert_label = ttk.Label(security_frame, text="CA Certificate:")
        self.cert_label.grid(row=1, column=0, sticky=tk.W, pady=2)
        
        cert_frame = ttk.Frame(security_frame)
        cert_frame.grid(row=1, column=1, sticky=tk.W, pady=2)
        
        self.ca_cert_var = tk.StringVar()
        self.cert_entry = ttk.Entry(cert_frame, textvariable=self.ca_cert_var, width=50)
        self.cert_entry.pack(side=tk.LEFT)
        
        self.cert_browse_btn = ttk.Button(cert_frame, text="Browse", command=self.browse_certificate)
        self.cert_browse_btn.pack(side=tk.LEFT, padx=(5, 0))
        
        # Initially hide certificate options
        self.toggle_certificate_widgets()
        
        # URL helper buttons
        url_helper_frame = ttk.Frame(conn_frame)
        url_helper_frame.grid(row=5, column=1, sticky=tk.W, pady=5)
        
        ttk.Button(url_helper_frame, text="Set WS URL", 
                  command=lambda: self.set_url_protocol("ws")).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(url_helper_frame, text="Set WSS URL", 
                  command=lambda: self.set_url_protocol("wss")).pack(side=tk.LEFT)
        
        # Charger properties
        charger_frame = ttk.LabelFrame(parent, text="Charger Properties", padding=10)
        charger_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(charger_frame, text="Vendor:").grid(row=0, column=0, sticky=tk.W, pady=2)
        self.vendor_var = tk.StringVar(value="SimulatorVendor")
        ttk.Entry(charger_frame, textvariable=self.vendor_var, width=30).grid(row=0, column=1, sticky=tk.W, pady=2)
        
        ttk.Label(charger_frame, text="Model:").grid(row=1, column=0, sticky=tk.W, pady=2)
        self.model_var = tk.StringVar(value="SimulatorModel")
        ttk.Entry(charger_frame, textvariable=self.model_var, width=30).grid(row=1, column=1, sticky=tk.W, pady=2)
        
        ttk.Label(charger_frame, text="Serial Number:").grid(row=2, column=0, sticky=tk.W, pady=2)
        self.serial_var = tk.StringVar(value="SIM001")
        ttk.Entry(charger_frame, textvariable=self.serial_var, width=30).grid(row=2, column=1, sticky=tk.W, pady=2)
        
        ttk.Label(charger_frame, text="Firmware Version:").grid(row=3, column=0, sticky=tk.W, pady=2)
        self.firmware_var = tk.StringVar(value="1.0.0")
        ttk.Entry(charger_frame, textvariable=self.firmware_var, width=30).grid(row=3, column=1, sticky=tk.W, pady=2)
        
        # Number of connectors
        ttk.Label(charger_frame, text="Number of Connectors:").grid(row=4, column=0, sticky=tk.W, pady=2)
        self.num_connectors_var = tk.StringVar(value="1")
        ttk.Spinbox(charger_frame, textvariable=self.num_connectors_var, from_=1, to=10, width=10).grid(row=4, column=1, sticky=tk.W, pady=2)

    def manage_config_keys(self):
        """Open configuration keys management dialog"""
        # Get current keys from simulator if connected, otherwise use saved keys
        if self.simulator:
            self.config_keys = self.simulator.get_configuration_keys_list()
        
        dialog = ConfigurationDialog(self.root, self.config_keys)
        self.wait_window(dialog)
        
        if dialog.result:
            self.config_keys = dialog.result
            # Update simulator if connected
            if self.simulator:
                # Clear existing keys
                self.simulator.configuration_keys.clear()
                # Load new keys
                self.simulator._load_custom_config_keys(self.config_keys)

    def on_tls_toggle(self):
        """Handle TLS checkbox toggle"""
        self.toggle_certificate_widgets()
        self.update_security_profile_label()

    def toggle_certificate_widgets(self):
        """Show/hide certificate widgets based on TLS setting"""
        if self.use_tls_var.get():
            # Show certificate options
            self.cert_label.grid()
            self.cert_entry.master.grid()
        else:
            # Hide certificate options
            self.cert_label.grid_remove()
            self.cert_entry.master.grid_remove()

    def update_security_profile_label(self):
        """Update security profile label based on TLS setting"""
        if self.use_tls_var.get():
            self.security_profile_label.config(text="Security Profile: TLS with Basic Auth", foreground="green")
        else:
            self.security_profile_label.config(text="Security Profile: Basic Auth only", foreground="blue")

    def set_url_protocol(self, protocol):
        """Set URL protocol (ws or wss)"""
        current_url = self.url_var.get()
        
        # Remove existing protocol
        if current_url.startswith("ws://"):
            current_url = current_url[5:]
        elif current_url.startswith("wss://"):
            current_url = current_url[6:]
        
        # Add new protocol
        new_url = f"{protocol}://{current_url}"
        self.url_var.set(new_url)
        
        # Update TLS checkbox accordingly
        self.use_tls_var.set(protocol == "wss")
        self.on_tls_toggle()

    def setup_control_tab(self, parent):
        """Setup control tab"""
        # Connection control
        conn_control_frame = ttk.LabelFrame(parent, text="Connection Control", padding=10)
        conn_control_frame.pack(fill=tk.X, pady=5)
        
        self.connect_btn = ttk.Button(conn_control_frame, text="Connect", command=self.connect_charger)
        self.connect_btn.pack(side=tk.LEFT, padx=5)
        
        self.disconnect_btn = ttk.Button(conn_control_frame, text="Disconnect", command=self.disconnect_charger, state=tk.DISABLED)
        self.disconnect_btn.pack(side=tk.LEFT, padx=5)
        
        # Status display
        status_frame = ttk.LabelFrame(parent, text="Status", padding=10)
        status_frame.pack(fill=tk.X, pady=5)
        
        self.status_var = tk.StringVar(value="Disconnected")
        ttk.Label(status_frame, text="Connection Status:").pack(side=tk.LEFT)
        self.status_label = ttk.Label(status_frame, textvariable=self.status_var, foreground="red")
        self.status_label.pack(side=tk.LEFT, padx=(10, 0))
        
        # Connection info
        self.connection_info_var = tk.StringVar(value="")
        self.connection_info_label = ttk.Label(status_frame, textvariable=self.connection_info_var, foreground="gray")
        self.connection_info_label.pack(side=tk.LEFT, padx=(20, 0))
        
        # Manual message sending
        message_frame = ttk.LabelFrame(parent, text="Send Messages", padding=10)
        message_frame.pack(fill=tk.X, pady=5)
        
        # Row 1: Connector ID and Heartbeat
        row1_frame = ttk.Frame(message_frame)
        row1_frame.pack(fill=tk.X, pady=2)
        
        ttk.Label(row1_frame, text="Connector ID:").pack(side=tk.LEFT)
        self.connector_id_var = tk.StringVar(value="1")
        ttk.Spinbox(row1_frame, textvariable=self.connector_id_var, from_=0, to=10, width=5).pack(side=tk.LEFT, padx=(5, 20))
        
        ttk.Button(row1_frame, text="Send Heartbeat", command=self.send_heartbeat).pack(side=tk.LEFT, padx=5)
        
        # Row 2: Status buttons
        row2_frame = ttk.Frame(message_frame)
        row2_frame.pack(fill=tk.X, pady=2)
        
        ttk.Button(row2_frame, text="Send Status Available", command=lambda: self.send_status("Available")).pack(side=tk.LEFT, padx=5)
        ttk.Button(row2_frame, text="Send Status Charging", command=lambda: self.send_status("Charging")).pack(side=tk.LEFT, padx=5)
        ttk.Button(row2_frame, text="Send Status Unavailable", command=lambda: self.send_status("Unavailable")).pack(side=tk.LEFT, padx=5)
        ttk.Button(row2_frame, text="Send Status Faulted", command=lambda: self.send_status("Faulted")).pack(side=tk.LEFT, padx=5)
        
        # Transaction control
        transaction_frame = ttk.LabelFrame(parent, text="Transaction Control", padding=10)
        transaction_frame.pack(fill=tk.X, pady=5)
        
        # Transaction start row
        start_frame = ttk.Frame(transaction_frame)
        start_frame.pack(fill=tk.X, pady=2)
        
        ttk.Label(start_frame, text="ID Tag:").pack(side=tk.LEFT)
        self.id_tag_var = tk.StringVar(value="TestCard123")
        ttk.Entry(start_frame, textvariable=self.id_tag_var, width=20).pack(side=tk.LEFT, padx=5)
        
        ttk.Label(start_frame, text="Connector:").pack(side=tk.LEFT, padx=(10, 0))
        self.transaction_connector_var = tk.StringVar(value="1")
        ttk.Spinbox(start_frame, textvariable=self.transaction_connector_var, from_=1, to=10, width=5).pack(side=tk.LEFT, padx=5)
        
        ttk.Button(start_frame, text="Start Transaction", command=self.start_transaction).pack(side=tk.LEFT, padx=5)
        
        # Transaction stop row
        stop_frame = ttk.Frame(transaction_frame)
        stop_frame.pack(fill=tk.X, pady=2)
        
        ttk.Button(stop_frame, text="Stop Transaction", command=self.stop_transaction).pack(side=tk.LEFT, padx=5)
        ttk.Label(stop_frame, text="(Stops active transaction on selected connector)").pack(side=tk.LEFT, padx=5)
        
        # Active transactions display
        active_frame = ttk.LabelFrame(parent, text="Active Transactions", padding=10)
        active_frame.pack(fill=tk.X, pady=5)
        
        self.active_transactions_text = tk.Text(active_frame, height=3, width=60)
        self.active_transactions_text.pack(fill=tk.X)
        self.active_transactions_text.config(state=tk.DISABLED)

    def setup_log_tab(self, parent):
        """Setup log tab"""
        log_frame = ttk.Frame(parent)
        log_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Log text area
        self.log_text = scrolledtext.ScrolledText(log_frame, wrap=tk.WORD, width=100, height=30)
        self.log_text.pack(fill=tk.BOTH, expand=True)
        
        # Clear button
        ttk.Button(log_frame, text="Clear Logs", command=self.clear_logs).pack(pady=5)

    def browse_certificate(self):
        """Browse for CA certificate file"""
        filename = filedialog.askopenfilename(
            title="Select CA Certificate",
            filetypes=[("Certificate files", "*.pem *.crt *.cer"), ("All files", "*.*")]
        )
        if filename:
            self.ca_cert_var.set(filename)

    def update_log(self, message):
        """Update log display (thread-safe)"""
        def _update():
            self.log_text.insert(tk.END, message + "\n")
            self.log_text.see(tk.END)
        
        self.root.after(0, _update)

    def clear_logs(self):
        """Clear log display"""
        self.log_text.delete(1.0, tk.END)

    def apply_config(self):
        """Apply configuration to simulator"""
        try:
            num_connectors = int(self.num_connectors_var.get())
            if num_connectors < 1 or num_connectors > 10:
                messagebox.showerror("Error", "Number of connectors must be between 1 and 10")
                return
        except ValueError:
            messagebox.showerror("Error", "Invalid number of connectors")
            return
            
        config = {
            'charge_point_id': self.cp_id_var.get(),
            'password': self.password_var.get(),
            'central_system_url': self.url_var.get(),
            'heartbeat_interval': int(self.heartbeat_var.get()),
            'use_tls': self.use_tls_var.get(),
            'ca_cert_path': self.ca_cert_var.get() if self.ca_cert_var.get() else None,
            'charge_point_vendor': self.vendor_var.get(),
            'charge_point_model': self.model_var.get(),
            'charge_point_serial_number': self.serial_var.get(),
            'firmware_version': self.firmware_var.get(),
            'meter_serial_number': f"METER{self.cp_id_var.get()}",
            'number_of_connectors': num_connectors,
            'configuration_keys': self.config_keys
        }
        
        self.simulator = EVChargerSimulator(config, gui_callback=self.update_log)
        
        # Update connector spinbox maximum values
        self.connector_id_var.set("1")
        self.transaction_connector_var.set("1")

    def connect_charger(self):
        """Connect to the Central System"""
        if not self.cp_id_var.get() or not self.url_var.get() or not self.password_var.get():
            messagebox.showerror("Error", "Please fill in all required fields")
            return
        
        # Validate URL protocol matches TLS setting
        url = self.url_var.get()
        use_tls = self.use_tls_var.get()
        
        if use_tls and not url.startswith('wss://'):
            if messagebox.askyesno("URL Mismatch", 
                                 "TLS is enabled but URL doesn't use 'wss://'. Continue anyway?"):
                pass
            else:
                return
        elif not use_tls and not url.startswith('ws://'):
            if messagebox.askyesno("URL Mismatch", 
                                 "TLS is disabled but URL doesn't use 'ws://'. Continue anyway?"):
                pass
            else:
                return
        
        self.apply_config()
        
        # Update connection info
        connection_type = "WSS (TLS)" if use_tls else "WS (Plain)"
        self.connection_info_var.set(f"({connection_type})")
        
        # Start asyncio loop in separate thread
        self.asyncio_thread = threading.Thread(target=self.run_asyncio_loop, daemon=True)
        self.asyncio_thread.start()
        
        self.connect_btn.config(state=tk.DISABLED)
        self.disconnect_btn.config(state=tk.NORMAL)
        self.status_var.set("Connecting...")
        self.status_label.config(foreground="orange")

    def run_asyncio_loop(self):
        """Run asyncio loop in separate thread"""
        try:
            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)
            
            # Set event loop policy for Windows
            if platform.system() == 'Windows':
                asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
            
            self.loop.run_until_complete(self.simulator.connect())
            
            # Start periodic updates for active transactions
            if self.simulator and self.simulator.is_connected:
                self.root.after(0, self.update_status_connected)
                self.root.after(2000, self.periodic_transaction_update)
        except Exception as e:
            self.simulator.log(f"Connection error: {e}", "ERROR")
        finally:
            self.root.after(0, self.on_disconnected)
    
    def update_status_connected(self):
        """Update status when connected"""
        self.status_var.set("Connected")
        self.status_label.config(foreground="green")
        self.update_active_transactions()
    
    def periodic_transaction_update(self):
        """Periodically update active transactions display"""
        if self.simulator and self.simulator.is_connected:
            self.update_active_transactions()
            # Schedule next update
            self.root.after(5000, self.periodic_transaction_update)

    def disconnect_charger(self):
        """Disconnect from Central System"""
        if self.loop and self.simulator and self.simulator.is_connected:
            asyncio.run_coroutine_threadsafe(self.simulator.disconnect(), self.loop)
        
        self.on_disconnected()

    def on_disconnected(self):
        """Handle disconnection UI updates"""
        self.connect_btn.config(state=tk.NORMAL)
        self.disconnect_btn.config(state=tk.DISABLED)
        self.status_var.set("Disconnected")
        self.status_label.config(foreground="red")
        self.connection_info_var.set("")
        
        # Clear active transactions display
        self.active_transactions_text.config(state=tk.NORMAL)
        self.active_transactions_text.delete(1.0, tk.END)
        self.active_transactions_text.insert(tk.END, "Not connected")
        self.active_transactions_text.config(state=tk.DISABLED)

    def send_heartbeat(self):
        """Send heartbeat manually"""
        if self.loop and self.simulator and self.simulator.is_connected:
            asyncio.run_coroutine_threadsafe(self.simulator.send_call(OCPPAction.HEARTBEAT.value, {}), self.loop)
        else:
            messagebox.showwarning("Warning", "Not connected to Central System")

    def send_status(self, status):
        """Send status notification manually"""
        if self.loop and self.simulator and self.simulator.is_connected:
            try:
                connector_id = int(self.connector_id_var.get())
                status_enum = getattr(ChargerStatus, status.upper(), ChargerStatus.AVAILABLE)
                asyncio.run_coroutine_threadsafe(
                    self.simulator.send_status_notification(connector_id, status_enum), 
                    self.loop
                )
            except ValueError:
                messagebox.showerror("Error", "Invalid connector ID")
        else:
            messagebox.showwarning("Warning", "Not connected to Central System")

    def start_transaction(self):
        """Start a charging transaction"""
        if self.loop and self.simulator and self.simulator.is_connected:
            id_tag = self.id_tag_var.get()
            if not id_tag:
                messagebox.showerror("Error", "Please enter an ID tag")
                return
            try:
                connector_id = int(self.transaction_connector_var.get())
                asyncio.run_coroutine_threadsafe(
                    self.simulator.start_transaction(id_tag, connector_id), 
                    self.loop
                )
                # Update active transactions display
                self.root.after(1000, self.update_active_transactions)
            except ValueError:
                messagebox.showerror("Error", "Invalid connector ID")
        else:
            messagebox.showwarning("Warning", "Not connected to Central System")

    def stop_transaction(self):
        """Stop the current transaction"""
        if self.loop and self.simulator and self.simulator.is_connected:
            try:
                connector_id = int(self.transaction_connector_var.get())
                asyncio.run_coroutine_threadsafe(
                    self.simulator.stop_transaction(connector_id=connector_id), 
                    self.loop
                )
                # Update active transactions display
                self.root.after(1000, self.update_active_transactions)
            except ValueError:
                messagebox.showerror("Error", "Invalid connector ID")
        else:
            messagebox.showwarning("Warning", "Not connected to Central System")
    
    def update_active_transactions(self):
        """Update the active transactions display"""
        if self.simulator:
            active_transactions = self.simulator.get_active_transactions()
            
            self.active_transactions_text.config(state=tk.NORMAL)
            self.active_transactions_text.delete(1.0, tk.END)
            
            if active_transactions:
                for transaction in active_transactions:
                    text = f"Connector {transaction['connector_id']}: Transaction {transaction['transaction_id']} - {transaction['status']}\n"
                    self.active_transactions_text.insert(tk.END, text)
            else:
                self.active_transactions_text.insert(tk.END, "No active transactions")
            
            self.active_transactions_text.config(state=tk.DISABLED)

    def wait_window(self, window):
        """Wait for a window to be destroyed"""
        window.wait_window()

    def on_closing(self):
        """Handle window closing"""
        if self.simulator and self.simulator.is_connected:
            self.disconnect_charger()
        
        if self.loop:
            self.loop.call_soon_threadsafe(self.loop.stop)
        
        self.root.destroy()


def main():
    """Main function"""
    # Handle both GUI and CLI modes
    if len(sys.argv) > 1 and sys.argv[1] == "--cli":
        # CLI mode
        print("Running in CLI mode...")
        # Original CLI implementation would go here
        pass
    else:
        # GUI mode
        root = tk.Tk()
        app = EVChargerSimulatorGUI(root)
        root.mainloop()


if __name__ == "__main__":
    main()