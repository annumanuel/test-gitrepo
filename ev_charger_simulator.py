# ev_charger_simulator.py
"""OCPP 1.6 EV Charger Simulator Core"""

import asyncio
import json
import base64
import logging
from datetime import datetime, timedelta, timezone
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