# meter_values.py
"""OCPP 1.6 Meter Values Handling"""

from datetime import datetime
from typing import Dict, List, Any, Optional
import asyncio
from ocpp_enums import OCPPAction, ChargerStatus
import logging

logger = logging.getLogger(__name__)


class MeterValuesHandler:
    """Handles meter values generation and transmission"""
    
    def __init__(self, simulator):
        self.simulator = simulator
        self.meter_values: Dict[int, Dict[str, float]] = {}
        
    def initialize_connector(self, connector_id: int):
        """Initialize meter values for a connector"""
        self.meter_values[connector_id] = {
            "Energy.Active.Import.Register": 0,
            "Power.Active.Import": 7400,  # Default 7.4 kW
            "Current.Import": 32.0,  # Default 32A
            "Voltage": 230.0,  # Default 230V
            "Temperature": 25.0,  # Default 25°C
            "SoC": 50,  # Default 50% State of Charge
            "Power.Offered": 7400,  # Maximum power offered
            "Current.Offered": 32.0,  # Maximum current offered
            "Energy.Reactive.Import.Register": 0,
            "Energy.Active.Export.Register": 0,
            "Energy.Reactive.Export.Register": 0,
            "Power.Reactive.Import": 0,
            "Power.Reactive.Export": 0,
            "Power.Active.Export": 0,
            "Power.Factor": 0.95,
            "Frequency": 50.0,  # Default 50Hz
            "RPM": 0
        }
    
    async def send_meter_values_loop(self, connector_id: int, transaction_id: int):
        """Send periodic meter values during charging"""
        # Get the meter value sample interval from configuration
        sample_interval = self.simulator.config_manager.get_int_value("MeterValueSampleInterval", 60)
        
        # If interval is 0, don't send any meter values
        if sample_interval == 0:
            self.simulator.log(f"MeterValueSampleInterval is 0, not sending meter values for connector {connector_id}")
            return
        
        # Get the measurands to sample from configuration
        sampled_data_config = self.simulator.config_manager.get_value("MeterValuesSampledData", "Energy.Active.Import.Register")
        measurands = [m.strip() for m in sampled_data_config.split(",") if m.strip()]
        
        self.simulator.log(f"Starting meter values loop for connector {connector_id} with interval {sample_interval}s, measurands: {measurands}")
        
        # Initialize meter values for connector if not exists
        if connector_id not in self.meter_values:
            self.initialize_connector(connector_id)
        
        while (self.simulator.connector_transactions.get(connector_id) == transaction_id and 
               self.simulator.connector_status.get(connector_id) == ChargerStatus.CHARGING):
            await asyncio.sleep(sample_interval)
            
            # Check if still charging after sleep
            if (self.simulator.connector_transactions.get(connector_id) != transaction_id or
                self.simulator.connector_status.get(connector_id) != ChargerStatus.CHARGING):
                break
            
            # Check if interval changed
            new_interval = self.simulator.config_manager.get_int_value("MeterValueSampleInterval", 60)
            if new_interval != sample_interval:
                self.simulator.log(f"MeterValueSampleInterval changed from {sample_interval} to {new_interval}")
                sample_interval = new_interval
                if sample_interval == 0:
                    self.simulator.log(f"MeterValueSampleInterval is 0, stopping meter values for connector {connector_id}")
                    return
            
            # Get current measurands (may have changed)
            sampled_data_config = self.simulator.config_manager.get_value("MeterValuesSampledData", "Energy.Active.Import.Register")
            measurands = [m.strip() for m in sampled_data_config.split(",") if m.strip()]
            
            # Prepare sampled values
            sampled_values = self._generate_sampled_values(connector_id, measurands, "Sample.Periodic")
            
            # Only send if we have values to send
            if sampled_values:
                payload = {
                    "connectorId": connector_id,
                    "transactionId": transaction_id,
                    "meterValue": [{
                        "timestamp": datetime.utcnow().isoformat() + "Z",
                        "sampledValue": sampled_values
                    }]
                }
                
                try:
                    await self.simulator.send_call(OCPPAction.METER_VALUES.value, payload)
                    self.simulator.log(f"Meter values sent for connector {connector_id}: {len(sampled_values)} measurands")
                except Exception as e:
                    self.simulator.log(f"Error sending meter values: {e}", "ERROR")
                    break
    
    async def send_grid_meter_values_loop(self):
        """Send periodic meter values for connector 0 (grid connection) if configured"""
        # Get the meter value sample interval from configuration
        sample_interval = self.simulator.config_manager.get_int_value("MeterValueSampleInterval", 60)
        
        # If interval is 0, don't send any meter values
        if sample_interval == 0:
            return
        
        # Get the measurands to sample from configuration
        sampled_data_config = self.simulator.config_manager.get_value("MeterValuesSampledData", "")
        if not sampled_data_config:
            return
            
        measurands = [m.strip() for m in sampled_data_config.split(",") if m.strip()]
        
        # Check if any measurands should be reported on the Inlet (grid connection)
        inlet_measurands = []
        for measurand in measurands:
            # These measurands typically can be measured at the grid connection
            if measurand in ["Power.Active.Import", "Current.Import", "Voltage", "Power.Factor", "Frequency", 
                             "Power.Reactive.Import", "Energy.Active.Import.Register", "Energy.Reactive.Import.Register"]:
                inlet_measurands.append(measurand)
        
        if not inlet_measurands:
            return  # No inlet measurands to report
        
        self.simulator.log(f"Starting grid meter values loop (connector 0) with interval {sample_interval}s, measurands: {inlet_measurands}")
        
        while self.simulator.is_connected and self.simulator.boot_notification_accepted:
            await asyncio.sleep(sample_interval)
            
            if not self.simulator.is_connected:
                break
            
            # Check if interval changed
            new_interval = self.simulator.config_manager.get_int_value("MeterValueSampleInterval", 60)
            if new_interval != sample_interval:
                sample_interval = new_interval
                if sample_interval == 0:
                    return
            
            # Re-check measurands in case configuration changed
            sampled_data_config = self.simulator.config_manager.get_value("MeterValuesSampledData", "")
            if sampled_data_config:
                measurands = [m.strip() for m in sampled_data_config.split(",") if m.strip()]
                inlet_measurands = [m for m in measurands if m in ["Power.Active.Import", "Current.Import", "Voltage", 
                                                                   "Power.Factor", "Frequency", "Power.Reactive.Import", 
                                                                   "Energy.Active.Import.Register", "Energy.Reactive.Import.Register"]]
            
            # Prepare sampled values for grid connection
            sampled_values = self._generate_grid_sampled_values(inlet_measurands)
            
            # Only send if we have values to send
            if sampled_values:
                payload = {
                    "connectorId": 0,  # Connector 0 represents the grid connection
                    "meterValue": [{
                        "timestamp": datetime.utcnow().isoformat() + "Z",
                        "sampledValue": sampled_values
                    }]
                }
                
                try:
                    await self.simulator.send_call(OCPPAction.METER_VALUES.value, payload)
                    self.simulator.log(f"Grid meter values sent (connector 0): {len(sampled_values)} measurands")
                except Exception as e:
                    self.simulator.log(f"Error sending grid meter values: {e}", "ERROR")
    
    def _generate_sampled_values(self, connector_id: int, measurands: List[str], context: str) -> List[Dict[str, Any]]:
        """Generate sampled values for given measurands"""
        sampled_values = []
        meter_vals = self.meter_values.get(connector_id, {})
        
        # Get current limits from charging profiles if available
        current_limits = {"power": None, "current": None}
        if hasattr(self.simulator, 'charging_profiles_manager'):
            current_limits = self.simulator.charging_profiles_manager.get_current_limit(connector_id)
        
        for measurand in measurands:
            if measurand == "Energy.Active.Import.Register":
                # Calculate energy based on actual power consumption
                actual_power = meter_vals.get("Power.Active.Import", 7400)
                if current_limits["power"] is not None:
                    actual_power = min(actual_power, current_limits["power"])
                
                # Energy increment based on actual power and sample interval
                sample_interval = self.simulator.config_manager.get_int_value("MeterValueSampleInterval", 60)
                energy_increment = (actual_power * sample_interval) / 3600  # Convert to Wh
                
                meter_vals[measurand] = meter_vals.get(measurand, 0) + energy_increment
                sampled_values.append({
                    "value": str(int(meter_vals[measurand])),
                    "context": context,
                    "format": "Raw",
                    "measurand": measurand,
                    "location": "Outlet",
                    "unit": "Wh"
                })
            elif measurand == "Power.Active.Import":
                # Apply power limit from charging profile
                base_power = meter_vals.get("Power.Active.Import", 7400)
                
                if current_limits["power"] is not None:
                    # Apply the charging profile limit
                    actual_power = min(base_power, current_limits["power"])
                    meter_vals["Power.Active.Import"] = actual_power
                else:
                    # No limit, use base power with some variation
                    actual_power = base_power + (int(meter_vals.get("Energy.Active.Import.Register", 0)) % 100)
                
                sampled_values.append({
                    "value": str(int(actual_power)),
                    "context": context,
                    "format": "Raw",
                    "measurand": measurand,
                    "location": "Outlet",
                    "unit": "W"
                })
            elif measurand == "SoC":
                # Simulate State of Charge increasing during charging
                current_soc = meter_vals.get("SoC", 50)
                # Increase SoC gradually (0.1% per minute at 60s interval)
                if sample_interval := self.simulator.config_manager.get_int_value("MeterValueSampleInterval", 60):
                    soc_increment = 0.1 * (sample_interval / 60)
                    new_soc = min(100, current_soc + soc_increment)
                    meter_vals["SoC"] = new_soc
                else:
                    new_soc = current_soc
                
                sampled_values.append({
                    "value": str(int(new_soc)),
                    "context": context,
                    "format": "Raw",
                    "measurand": measurand,
                    "location": "EV",
                    "unit": "Percent"
                })
            elif measurand == "Current.Import":
                # Apply current limit from charging profile
                base_current = meter_vals.get("Current.Import", 32.0)
                
                if current_limits["current"] is not None:
                    # Apply the charging profile limit
                    actual_current = min(base_current, current_limits["current"])
                    meter_vals["Current.Import"] = actual_current
                else:
                    # No limit, use base current with some variation
                    actual_current = base_current + (meter_vals.get("Energy.Active.Import.Register", 0) % 10) / 10.0
                
                sampled_values.append({
                    "value": f"{actual_current:.1f}",
                    "context": context,
                    "format": "Raw",
                    "measurand": measurand,
                    "phase": "L1",
                    "location": "Outlet",
                    "unit": "A"
                })
            elif measurand == "Voltage":
                # Simulate voltage with small variation
                voltage = meter_vals.get("Voltage", 230.0) + (meter_vals.get("Energy.Active.Import.Register", 0) % 5) - 2.5
                sampled_values.append({
                    "value": f"{voltage:.1f}",
                    "context": context,
                    "format": "Raw",
                    "measurand": measurand,
                    "phase": "L1",
                    "location": "Outlet",
                    "unit": "V"
                })
            elif measurand == "Temperature":
                # Simulate temperature rising during charging
                temp = meter_vals.get("Temperature", 25.0) + (meter_vals.get("Energy.Active.Import.Register", 0) % 10) / 5.0
                sampled_values.append({
                    "value": f"{temp:.1f}",
                    "context": context,
                    "format": "Raw",
                    "measurand": measurand,
                    "location": "Outlet",
                    "unit": "Celsius"
                })
            elif measurand == "Power.Offered":
                # Maximum power that can be offered
                sampled_values.append({
                    "value": str(int(meter_vals.get("Power.Offered", 7400))),
                    "context": context,
                    "format": "Raw",
                    "measurand": measurand,
                    "location": "Outlet",
                    "unit": "W"
                })
            elif measurand == "Current.Offered":
                # Maximum current that can be offered
                sampled_values.append({
                    "value": f"{meter_vals.get('Current.Offered', 32.0):.1f}",
                    "context": context,
                    "format": "Raw",
                    "measurand": measurand,
                    "phase": "L1",
                    "location": "Outlet",
                    "unit": "A"
                })
            elif measurand == "Power.Factor":
                # Power factor
                sampled_values.append({
                    "value": f"{meter_vals.get('Power.Factor', 0.95):.2f}",
                    "context": context,
                    "format": "Raw",
                    "measurand": measurand,
                    "location": "Outlet"
                })
            elif measurand == "Frequency":
                # Grid frequency
                sampled_values.append({
                    "value": f"{meter_vals.get('Frequency', 50.0):.1f}",
                    "context": context,
                    "format": "Raw",
                    "measurand": measurand,
                    "location": "Outlet",
                    "unit": "Hz"
                })
            elif measurand == "Energy.Reactive.Import.Register":
                # Reactive energy
                meter_vals[measurand] = meter_vals.get(measurand, 0) + 20  # Increment by 20 VArh
                sampled_values.append({
                    "value": str(int(meter_vals[measurand])),
                    "context": context,
                    "format": "Raw",
                    "measurand": measurand,
                    "location": "Outlet",
                    "unit": "varh"
                })
            elif measurand == "Power.Reactive.Import":
                # Reactive power
                reactive_power = meter_vals.get("Power.Active.Import", 7400) * 0.33  # Approx tan(φ) for PF=0.95
                sampled_values.append({
                    "value": str(int(reactive_power)),
                    "context": context,
                    "format": "Raw",
                    "measurand": measurand,
                    "location": "Outlet",
                    "unit": "var"
                })
        
        return sampled_values
    
    def _generate_grid_sampled_values(self, measurands: List[str]) -> List[Dict[str, Any]]:
        """Generate sampled values for grid connection"""
        sampled_values = []
        
        # Calculate total power/current from all active transactions
        total_power = 0
        total_current = 0
        active_connectors = 0
        
        for conn_id, trans_id in self.simulator.connector_transactions.items():
            if trans_id is not None:
                active_connectors += 1
                total_power += self.meter_values.get(conn_id, {}).get("Power.Active.Import", 7400)
                total_current += self.meter_values.get(conn_id, {}).get("Current.Import", 32)
        
        for measurand in measurands:
            if measurand == "Power.Active.Import":
                if total_power > 0:
                    sampled_values.append({
                        "value": str(int(total_power)),
                        "context": "Sample.Periodic",
                        "format": "Raw",
                        "measurand": measurand,
                        "location": "Inlet",
                        "unit": "W"
                    })
            elif measurand == "Current.Import":
                if total_current > 0:
                    # Report for each phase
                    for phase in ["L1", "L2", "L3"]:
                        phase_current = total_current / 3  # Distribute evenly across phases
                        sampled_values.append({
                            "value": f"{phase_current:.1f}",
                            "context": "Sample.Periodic",
                            "format": "Raw",
                            "measurand": measurand,
                            "phase": phase,
                            "location": "Inlet",
                            "unit": "A"
                        })
            elif measurand == "Voltage":
                # Grid voltage (3-phase)
                for phase in ["L1", "L2", "L3"]:
                    voltage = 230.0  # Standard voltage
                    sampled_values.append({
                        "value": f"{voltage:.1f}",
                        "context": "Sample.Periodic",
                        "format": "Raw",
                        "measurand": measurand,
                        "phase": phase,
                        "location": "Inlet",
                        "unit": "V"
                    })
            elif measurand == "Power.Factor":
                sampled_values.append({
                    "value": "0.95",
                    "context": "Sample.Periodic",
                    "format": "Raw",
                    "measurand": measurand,
                    "location": "Inlet"
                })
            elif measurand == "Frequency":
                sampled_values.append({
                    "value": "50.0",
                    "context": "Sample.Periodic",
                    "format": "Raw",
                    "measurand": measurand,
                    "location": "Inlet",
                    "unit": "Hz"
                })
            elif measurand == "Energy.Active.Import.Register":
                # Total energy from grid (sum of all connectors)
                total_energy = sum(self.meter_values.get(conn_id, {}).get("Energy.Active.Import.Register", 0) 
                                 for conn_id in range(1, self.simulator.number_of_connectors + 1))
                if total_energy > 0:
                    sampled_values.append({
                        "value": str(int(total_energy)),
                        "context": "Sample.Periodic",
                        "format": "Raw",
                        "measurand": measurand,
                        "location": "Inlet",
                        "unit": "Wh"
                    })
        
        return sampled_values
    
    def get_stop_transaction_values(self, connector_id: int) -> List[Dict[str, Any]]:
        """Get meter values for stop transaction"""
        # Get the measurands to include in stop transaction
        stop_txn_data_config = self.simulator.config_manager.get_value("StopTxnSampledData", "Energy.Active.Import.Register")
        measurands = [m.strip() for m in stop_txn_data_config.split(",") if m.strip()]
        
        # Generate sampled values with Transaction.End context
        return self._generate_sampled_values(connector_id, measurands, "Transaction.End")
