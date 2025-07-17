# ev_charger_simulator.py
"""OCPP 1.6 EV Charger Simulator Core"""

import asyncio
import json
import base64
import logging
from datetime import datetime
from typing import Dict, Any, Optional, List
import websockets
import urllib.parse
import ssl
import platform

from ocpp_enums import MessageType, OCPPAction, ChargerStatus
from configuration_keys import ConfigurationManager
from meter_values import MeterValuesHandler
from message_handlers import MessageHandlers
from charging_profiles import ChargingProfilesManager

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


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
        
        # Initialize components
        self.config_manager = ConfigurationManager(self.heartbeat_interval, self.number_of_connectors)
        self.meter_handler = MeterValuesHandler(self)
        self.message_handlers = MessageHandlers(self)
        self.charging_profiles_manager = ChargingProfilesManager(self)
        
        # Load custom configuration keys from config if provided
        if 'configuration_keys' in config:
            self.config_manager.load_custom_config_keys(config['configuration_keys'])
    
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
        parsed = urllib.parse.urlparse(self.central_system_url)
        auth_string = f"{self.charge_point_id}:{self.password}"
        
        if parsed.scheme == "ws":
            scheme = "ws"
        elif parsed.scheme == "wss":
            scheme = "wss"
        else:
            scheme = "ws"
            
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
        
        self.log("All connection methods failed", "ERROR")
        await self.handle_connection_failure()
    
    async def _connect_with_headers(self):
        """Try connection with headers (newer websockets versions)"""
        uri = f"{self.central_system_url}/{self.charge_point_id}"
        headers = {"Authorization": self.create_auth_header()}
        ssl_context = self._create_ssl_context()
        
        self.log(f"Connecting with headers to: {uri}")
        
        try:
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
                self.websocket = await websockets.connect(
                    uri,
                    ssl=ssl_context,
                    subprotocols=['ocpp1.6'],
                    extra_headers=headers
                )
            except TypeError:
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
        
        handlers = self.message_handlers.get_handlers()
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
        
        future = asyncio.get_event_loop().create_future()
        self.pending_requests[message_id] = future
        
        self.log(f"Sending: {message}")
        await self.websocket.send(json.dumps(message))
        
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
                asyncio.create_task(self.meter_handler.send_grid_meter_values_loop())
                
                for connector_id in range(1, self.number_of_connectors + 1):
                    await self.send_status_notification(connector_id, ChargerStatus.AVAILABLE)
            else:
                self.log(f"BootNotification rejected: {response}", "WARNING")
                await asyncio.sleep(response.get("interval", 60))
                await self.send_boot_notification()
                
        except Exception as e:
            self.log(f"Error sending BootNotification: {e}", "ERROR")
    
    async def heartbeat_loop(self):
        """Send periodic heartbeat messages"""
        while self.is_connected and self.boot_notification_accepted:
            try:
                await asyncio.sleep(self.heartbeat_interval)
                if self.is_connected:
                    response = await self.send_call(OCPPAction.HEARTBEAT.value, {})
                    self.log(f"Heartbeat sent, current time: {response.get('currentTime')}")
            except Exception as e:
                self.log(f"Error sending heartbeat: {e}", "ERROR")
                break
    
    async def send_status_notification(self, connector_id: int, 
                                     status: ChargerStatus, 
                                     error_code: str = "NoError"):
        """Send StatusNotification to Central System"""
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
            if connector_id > 0:
                self.connector_status[connector_id] = status
            self.log(f"Status notification sent: Connector {connector_id} - {status.value}")
        except Exception as e:
            self.log(f"Error sending status notification: {e}", "ERROR")
    
    async def start_transaction(self, id_tag: str, connector_id: int = 1):
        """Start a charging transaction"""
        if connector_id < 1 or connector_id > self.number_of_connectors:
            self.log(f"Invalid connector ID: {connector_id}. Valid range: 1-{self.number_of_connectors}", "ERROR")
            return
            
        if self.connector_status.get(connector_id) != ChargerStatus.AVAILABLE:
            self.log(f"Connector {connector_id} is not available. Current status: {self.connector_status.get(connector_id).value}", "WARNING")
            return
            
        await self.send_status_notification(connector_id, ChargerStatus.PREPARING)
        
        auth_payload = {"idTag": id_tag}
        auth_response = await self.send_call(OCPPAction.AUTHORIZE.value, auth_payload)
        
        if auth_response.get("idTagInfo", {}).get("status") != "Accepted":
            self.log(f"Authorization failed for {id_tag}", "WARNING")
            await self.send_status_notification(connector_id, ChargerStatus.AVAILABLE)
            return
        
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
            
            await self.send_status_notification(connector_id, ChargerStatus.CHARGING)
            
            asyncio.create_task(self.meter_handler.send_meter_values_loop(connector_id, transaction_id))
            
        except Exception as e:
            self.log(f"Error starting transaction: {e}", "ERROR")
            await self.send_status_notification(connector_id, ChargerStatus.AVAILABLE)
    
    async def stop_transaction(self, transaction_id: int = None, connector_id: int = None):
        """Stop a charging transaction"""
        if transaction_id is None:
            if connector_id is None:
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
        
        if connector_id is None:
            for conn_id, trans_id in self.connector_transactions.items():
                if trans_id == transaction_id:
                    connector_id = conn_id
                    break
        
        sampled_values = self.meter_handler.get_stop_transaction_values(connector_id)
        
        payload = {
            "transactionId": transaction_id,
            "meterStop": 10000,
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }
        
        if sampled_values:
            payload["transactionData"] = [{
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "sampledValue": sampled_values
            }]
        
        try:
            response = await self.send_call(OCPPAction.STOP_TRANSACTION.value, payload)
            self.log(f"Transaction stopped on connector {connector_id}: {response}")
            
            if connector_id:
                self.connector_transactions[connector_id] = None
                await self.send_status_notification(connector_id, ChargerStatus.AVAILABLE)
            
        except Exception as e:
            self.log(f"Error stopping transaction: {e}", "ERROR")
    
    async def disconnect(self):
        """Disconnect from Central System"""
        self.is_connected = False
        if self.websocket:
            await self.websocket.close()
        self.log("Disconnected from Central System")
    
    def get_active_transactions(self) -> List[Dict[str, Any]]:
        """Get list of active transactions"""
        active_transactions = []
        for conn_id, trans_id in self.connector_transactions.items():
            if trans_id is not None:
                active_transactions.append({
                    'connector_id': conn_id,
                    'transaction_id': trans_id,
                    'status': self.connector_status.get(conn_id, ChargerStatus.AVAILABLE).value
                })
        return active_transactions
    
    def get_configuration_keys_list(self) -> List[Dict[str, Any]]:
        """Get list of configuration keys for GUI display"""
        return self.config_manager.get_configuration_keys_list()
    
    def update_configuration_key(self, key: str, value: str) -> str:
        """Update a configuration key value"""
        return self.config_manager.update_configuration_key(key, value)
