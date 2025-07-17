# gui_main.py
"""Main GUI Application for EV Charger Simulator"""

import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox, filedialog
import asyncio
import threading
import platform
import sys

# Import from other modules
from ev_charger_simulator import EVChargerSimulator
from gui_dialogs import ConfigurationDialog
from ocpp_enums import OCPPAction, ChargerStatus


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
        
        # Charging Profiles tab
        profiles_frame = ttk.Frame(notebook)
        notebook.add(profiles_frame, text="Charging Profiles")
        self.setup_charging_profiles_tab(profiles_frame)
        
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
                self.simulator.config_manager.configuration_keys.clear()
                # Load new keys
                self.simulator.config_manager.load_custom_config_keys(self.config_keys)

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

    def setup_charging_profiles_tab(self, parent):
        """Setup charging profiles tab"""
        # Create main frame with padding
        main_frame = ttk.Frame(parent, padding=10)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Profile Settings Frame
        profile_frame = ttk.LabelFrame(main_frame, text="Charging Profile Settings", padding=10)
        profile_frame.pack(fill=tk.X, pady=(0, 10))
        
        # Row 1: Profile ID and Connector
        row1 = ttk.Frame(profile_frame)
        row1.pack(fill=tk.X, pady=2)
        
        ttk.Label(row1, text="Profile ID:").pack(side=tk.LEFT, padx=(0, 5))
        self.profile_id_var = tk.StringVar(value="1")
        ttk.Entry(row1, textvariable=self.profile_id_var, width=10).pack(side=tk.LEFT, padx=(0, 20))
        
        ttk.Label(row1, text="Connector ID:").pack(side=tk.LEFT, padx=(0, 5))
        self.profile_connector_var = tk.StringVar(value="1")
        ttk.Spinbox(row1, textvariable=self.profile_connector_var, from_=0, to=10, width=5).pack(side=tk.LEFT, padx=(0, 20))
        
        ttk.Label(row1, text="Stack Level:").pack(side=tk.LEFT, padx=(0, 5))
        self.stack_level_var = tk.StringVar(value="0")
        ttk.Spinbox(row1, textvariable=self.stack_level_var, from_=0, to=10, width=5).pack(side=tk.LEFT)
        
        # Row 2: Purpose and Kind
        row2 = ttk.Frame(profile_frame)
        row2.pack(fill=tk.X, pady=2)
        
        ttk.Label(row2, text="Purpose:").pack(side=tk.LEFT, padx=(0, 5))
        self.purpose_var = tk.StringVar(value="TxDefaultProfile")
        purpose_combo = ttk.Combobox(row2, textvariable=self.purpose_var, width=20)
        purpose_combo['values'] = ("ChargePointMaxProfile", "TxDefaultProfile", "TxProfile")
        purpose_combo.pack(side=tk.LEFT, padx=(0, 20))
        
        ttk.Label(row2, text="Kind:").pack(side=tk.LEFT, padx=(0, 5))
        self.kind_var = tk.StringVar(value="Absolute")
        kind_combo = ttk.Combobox(row2, textvariable=self.kind_var, width=15)
        kind_combo['values'] = ("Absolute", "Recurring", "Relative")
        kind_combo.pack(side=tk.LEFT)
        
        # Row 3: Transaction ID (optional)
        row3 = ttk.Frame(profile_frame)
        row3.pack(fill=tk.X, pady=2)
        
        ttk.Label(row3, text="Transaction ID (optional):").pack(side=tk.LEFT, padx=(0, 5))
        self.profile_transaction_var = tk.StringVar(value="")
        ttk.Entry(row3, textvariable=self.profile_transaction_var, width=15).pack(side=tk.LEFT)
        
        # Charging Schedule Frame
        schedule_frame = ttk.LabelFrame(main_frame, text="Charging Schedule", padding=10)
        schedule_frame.pack(fill=tk.X, pady=(0, 10))
        
        # Row 1: Charging Rate Unit and Duration
        sched_row1 = ttk.Frame(schedule_frame)
        sched_row1.pack(fill=tk.X, pady=2)
        
        ttk.Label(sched_row1, text="Charging Rate Unit:").pack(side=tk.LEFT, padx=(0, 5))
        self.rate_unit_var = tk.StringVar(value="W")
        unit_combo = ttk.Combobox(sched_row1, textvariable=self.rate_unit_var, width=5)
        unit_combo['values'] = ("W", "A")
        unit_combo.pack(side=tk.LEFT, padx=(0, 20))
        
        ttk.Label(sched_row1, text="Duration (seconds):").pack(side=tk.LEFT, padx=(0, 5))
        self.duration_var = tk.StringVar(value="3600")
        ttk.Entry(sched_row1, textvariable=self.duration_var, width=10).pack(side=tk.LEFT)
        
        # Schedule Periods Frame
        periods_frame = ttk.LabelFrame(main_frame, text="Schedule Periods", padding=10)
        periods_frame.pack(fill=tk.X, pady=(0, 10))
        
        # Period 1
        period1_frame = ttk.Frame(periods_frame)
        period1_frame.pack(fill=tk.X, pady=2)
        
        ttk.Label(period1_frame, text="Period 1 - Start (s):").pack(side=tk.LEFT, padx=(0, 5))
        self.period1_start_var = tk.StringVar(value="0")
        ttk.Entry(period1_frame, textvariable=self.period1_start_var, width=10).pack(side=tk.LEFT, padx=(0, 10))
        
        ttk.Label(period1_frame, text="Limit:").pack(side=tk.LEFT, padx=(0, 5))
        self.period1_limit_var = tk.StringVar(value="7400")
        ttk.Entry(period1_frame, textvariable=self.period1_limit_var, width=10).pack(side=tk.LEFT, padx=(0, 5))
        
        ttk.Label(period1_frame, text="(W or A)").pack(side=tk.LEFT)
        
        # Period 2 (optional)
        period2_frame = ttk.Frame(periods_frame)
        period2_frame.pack(fill=tk.X, pady=2)
        
        self.use_period2_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(period2_frame, text="Use Period 2", variable=self.use_period2_var).pack(side=tk.LEFT, padx=(0, 10))
        
        ttk.Label(period2_frame, text="Start (s):").pack(side=tk.LEFT, padx=(0, 5))
        self.period2_start_var = tk.StringVar(value="1800")
        ttk.Entry(period2_frame, textvariable=self.period2_start_var, width=10).pack(side=tk.LEFT, padx=(0, 10))
        
        ttk.Label(period2_frame, text="Limit:").pack(side=tk.LEFT, padx=(0, 5))
        self.period2_limit_var = tk.StringVar(value="3700")
        ttk.Entry(period2_frame, textvariable=self.period2_limit_var, width=10).pack(side=tk.LEFT, padx=(0, 5))
        
        # Period 3 (optional)
        period3_frame = ttk.Frame(periods_frame)
        period3_frame.pack(fill=tk.X, pady=2)
        
        self.use_period3_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(period3_frame, text="Use Period 3", variable=self.use_period3_var).pack(side=tk.LEFT, padx=(0, 10))
        
        ttk.Label(period3_frame, text="Start (s):").pack(side=tk.LEFT, padx=(0, 5))
        self.period3_start_var = tk.StringVar(value="3600")
        ttk.Entry(period3_frame, textvariable=self.period3_start_var, width=10).pack(side=tk.LEFT, padx=(0, 10))
        
        ttk.Label(period3_frame, text="Limit:").pack(side=tk.LEFT, padx=(0, 5))
        self.period3_limit_var = tk.StringVar(value="11000")
        ttk.Entry(period3_frame, textvariable=self.period3_limit_var, width=10).pack(side=tk.LEFT, padx=(0, 5))
        
        # Control Buttons Frame
        control_frame = ttk.Frame(main_frame)
        control_frame.pack(fill=tk.X, pady=10)
        
        ttk.Button(control_frame, text="Send SetChargingProfile", 
                  command=self.send_charging_profile).pack(side=tk.LEFT, padx=5)
        
        ttk.Button(control_frame, text="Clear Charging Profile", 
                  command=self.clear_charging_profile).pack(side=tk.LEFT, padx=5)
        
        ttk.Button(control_frame, text="Get Composite Schedule", 
                  command=self.get_composite_schedule).pack(side=tk.LEFT, padx=5)
        
        # Status Display
        status_frame = ttk.LabelFrame(main_frame, text="Active Charging Profiles", padding=10)
        status_frame.pack(fill=tk.BOTH, expand=True)
        
        self.profiles_text = tk.Text(status_frame, height=10, width=80)
        self.profiles_text.pack(fill=tk.BOTH, expand=True)
        self.profiles_text.config(state=tk.DISABLED)

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
            self.update_profiles_display()  # Also update charging profiles
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
    
    def send_charging_profile(self):
        """Send SetChargingProfile message"""
        if not self.loop or not self.simulator or not self.simulator.is_connected:
            messagebox.showwarning("Warning", "Not connected to Central System")
            return
        
        try:
            # Build charging schedule periods
            periods = []
            
            # Period 1 (always included)
            periods.append({
                "startPeriod": int(self.period1_start_var.get()),
                "limit": float(self.period1_limit_var.get())
            })
            
            # Period 2 (optional)
            if self.use_period2_var.get():
                periods.append({
                    "startPeriod": int(self.period2_start_var.get()),
                    "limit": float(self.period2_limit_var.get())
                })
            
            # Period 3 (optional)
            if self.use_period3_var.get():
                periods.append({
                    "startPeriod": int(self.period3_start_var.get()),
                    "limit": float(self.period3_limit_var.get())
                })
            
            # Build charging profile
            charging_profile = {
                "chargingProfileId": int(self.profile_id_var.get()),
                "stackLevel": int(self.stack_level_var.get()),
                "chargingProfilePurpose": self.purpose_var.get(),
                "chargingProfileKind": self.kind_var.get(),
                "chargingSchedule": {
                    "chargingRateUnit": self.rate_unit_var.get(),
                    "chargingSchedulePeriod": periods
                }
            }
            
            # Add optional fields
            if self.duration_var.get():
                charging_profile["chargingSchedule"]["duration"] = int(self.duration_var.get())
            
            if self.profile_transaction_var.get():
                charging_profile["transactionId"] = int(self.profile_transaction_var.get())
            
            # Build SetChargingProfile message
            message = {
                "connectorId": int(self.profile_connector_var.get()),
                "csChargingProfiles": charging_profile
            }
            
            # Send through simulator
            from ocpp_enums import OCPPAction
            asyncio.run_coroutine_threadsafe(
                self.simulator.send_call("SetChargingProfile", message),
                self.loop
            )
            
            # Update display
            self.update_profiles_display()
            
        except ValueError as e:
            messagebox.showerror("Error", f"Invalid input values: {e}")
        except Exception as e:
            messagebox.showerror("Error", f"Error sending charging profile: {e}")
    
    def clear_charging_profile(self):
        """Send ClearChargingProfile message"""
        if not self.loop or not self.simulator or not self.simulator.is_connected:
            messagebox.showwarning("Warning", "Not connected to Central System")
            return
        
        try:
            # Build ClearChargingProfile message
            message = {}
            
            # Add optional fields based on what user wants to clear
            if self.profile_id_var.get():
                message["id"] = int(self.profile_id_var.get())
            
            if self.profile_connector_var.get():
                message["connectorId"] = int(self.profile_connector_var.get())
            
            if self.purpose_var.get() and not self.profile_id_var.get():
                message["chargingProfilePurpose"] = self.purpose_var.get()
            
            if self.stack_level_var.get() and not self.profile_id_var.get():
                message["stackLevel"] = int(self.stack_level_var.get())
            
            # Send through simulator
            asyncio.run_coroutine_threadsafe(
                self.simulator.send_call("ClearChargingProfile", message),
                self.loop
            )
            
            # Update display
            self.update_profiles_display()
            
        except Exception as e:
            messagebox.showerror("Error", f"Error clearing charging profile: {e}")
    
    def get_composite_schedule(self):
        """Send GetCompositeSchedule message"""
        if not self.loop or not self.simulator or not self.simulator.is_connected:
            messagebox.showwarning("Warning", "Not connected to Central System")
            return
        
        try:
            # Build GetCompositeSchedule message
            message = {
                "connectorId": int(self.profile_connector_var.get()),
                "duration": int(self.duration_var.get()) if self.duration_var.get() else 86400
            }
            
            if self.rate_unit_var.get():
                message["chargingRateUnit"] = self.rate_unit_var.get()
            
            # Send through simulator
            asyncio.run_coroutine_threadsafe(
                self.simulator.send_call("GetCompositeSchedule", message),
                self.loop
            )
            
        except Exception as e:
            messagebox.showerror("Error", f"Error getting composite schedule: {e}")
    
    def update_profiles_display(self):
        """Update the active charging profiles display"""
        if not self.simulator or not hasattr(self.simulator, 'charging_profiles_manager'):
            return
        
        self.profiles_text.config(state=tk.NORMAL)
        self.profiles_text.delete(1.0, tk.END)
        
        # Display active profiles for each connector
        for connector_id in range(self.simulator.number_of_connectors + 1):
            profiles = self.simulator.charging_profiles_manager.charging_profiles.get(connector_id, [])
            if profiles:
                self.profiles_text.insert(tk.END, f"Connector {connector_id}:\n")
                for profile in profiles:
                    self.profiles_text.insert(tk.END, f"  Profile ID: {profile.charging_profile_id}, "
                                                    f"Stack Level: {profile.stack_level}, "
                                                    f"Purpose: {profile.charging_profile_purpose}\n")
                    
                    # Show current limits
                    limits = self.simulator.charging_profiles_manager.get_current_limit(connector_id)
                    if limits['power'] is not None or limits['current'] is not None:
                        self.profiles_text.insert(tk.END, f"    Current Limits: ")
                        if limits['power'] is not None:
                            self.profiles_text.insert(tk.END, f"Power={limits['power']}W ")
                        if limits['current'] is not None:
                            self.profiles_text.insert(tk.END, f"Current={limits['current']}A")
                        self.profiles_text.insert(tk.END, "\n")
                    
                    # Show schedule periods
                    for i, period in enumerate(profile.charging_schedule_periods):
                        self.profiles_text.insert(tk.END, 
                            f"    Period {i+1}: Start={period.get('startPeriod')}s, "
                            f"Limit={period.get('limit')}{profile.charging_rate_unit}\n")
                
                self.profiles_text.insert(tk.END, "\n")
        
        if self.profiles_text.get(1.0, tk.END).strip() == "":
            self.profiles_text.insert(tk.END, "No active charging profiles")
        
        self.profiles_text.config(state=tk.DISABLED)
