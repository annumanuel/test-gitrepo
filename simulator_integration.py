# ev_charger_simulator.py - Updated __init__ method to include charging profile handler

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
        
        # Charger physical properties
        self.number_of_connectors = config.get('number_of_connectors', 1)
        self.max_power = config.get('max_power', 22000)  # Maximum power in Watts
        
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
        
        # Time synchronization
        self.server_time_offset = timedelta(0)
        self.last_server_time = None
        self.last_local_time = None
        
        # Initialize components
        self.config_manager = ConfigurationManager(self.heartbeat_interval, self.number_of_connectors)
        self.meter_handler = MeterValuesHandler(self)
        
        # Initialize charging profile handler (NEW)
        from charging_profile_handler import ChargingProfileHandler
        self.charging_profile_handler = ChargingProfileHandler(self)
        
        self.message_handlers = MessageHandlers(self)
        
        # Load custom configuration keys from config if provided
        if 'configuration_keys' in config:
            self.config_manager.load_custom_config_keys(config['configuration_keys'])
        
        self.log(f"EV Charger Simulator initialized: {self.number_of_connectors} connectors, max power: {self.max_power}W")

    def get_server_time(self) -> datetime:
        """Get current time synchronized with server"""
        local_time = datetime.utcnow().replace(tzinfo=timezone.utc)
        return local_time + self.server_time_offset

    # Enhanced heartbeat_loop method with time synchronization
    async def heartbeat_loop(self):
        """Send periodic heartbeat messages with time synchronization"""
        while self.is_connected and self.boot_notification_accepted:
            try:
                await asyncio.sleep(self.heartbeat_interval)
                if self.is_connected:
                    local_time_before = datetime.utcnow()
                    response = await self.send_call(OCPPAction.HEARTBEAT.value, {})
                    
                    # Capture server time for synchronization
                    if 'currentTime' in response:
                        try:
                            server_time_str = response['currentTime']
                            if server_time_str.endswith('Z'):
                                server_time = datetime.fromisoformat(server_time_str.replace('Z', '+00:00'))
                            else:
                                server_time = datetime.fromisoformat(server_time_str)
                                if server_time.tzinfo is None:
                                    server_time = server_time.replace(tzinfo=timezone.utc)
                            
                            # Calculate offset (accounting for network delay)
                            local_time_after = datetime.utcnow().replace(tzinfo=timezone.utc)
                            network_delay = (local_time_after - local_time_before.replace(tzinfo=timezone.utc)) / 2
                            adjusted_local_time = local_time_before.replace(tzinfo=timezone.utc) + network_delay
                            
                            self.server_time_offset = server_time - adjusted_local_time
                            self.last_server_time = server_time
                            self.last_local_time = adjusted_local_time
                            
                            self.log(f"Heartbeat sent, server time: {server_time_str}, offset: {self.server_time_offset.total_seconds():.2f}s")
                        except Exception as e:
                            self.log(f"Error parsing server time: {e}", "WARNING")
                            self.log(f"Heartbeat sent, current time: {response.get('currentTime')}")
                    else:
                        self.log(f"Heartbeat sent, current time: {response.get('currentTime')}")
            except Exception as e:
                self.log(f"Error sending heartbeat: {e}", "ERROR")
                break

    # Updated start_transaction method to consider charging profile limits
    async def start_transaction(self, id_tag: str, connector_id: int = 1):
        """Start a charging transaction with charging profile consideration"""
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
            "timestamp": self.get_server_time().isoformat() + "Z"
        }
        
        try:
            response = await self.send_call(OCPPAction.START_TRANSACTION.value, payload)
            transaction_id = response.get("transactionId")
            self.connector_transactions[connector_id] = transaction_id
            self.log(f"Transaction {transaction_id} started on connector {connector_id}")
            
            # Update status to Charging
            await self.send_status_notification(connector_id, ChargerStatus.CHARGING)
            
            # Apply any existing charging profile limits to meter values
            if hasattr(self, 'charging_profile_handler'):
                limits = self.charging_profile_handler.get_current_charging_limit(connector_id)
                if limits["power_limit"] or limits["current_limit"]:
                    self.log(f"Applying charging profile limits to transaction {transaction_id}", "INFO")
            
            # Start sending meter values with profile limits applied
            asyncio.create_task(self.meter_handler.send_meter_values_loop(connector_id, transaction_id))
            
        except Exception as e:
            self.log(f"Error starting transaction: {e}", "ERROR")
            await self.send_status_notification(connector_id, ChargerStatus.AVAILABLE)

# Add these imports at the top of the file
from datetime import datetime, timedelta, timezone