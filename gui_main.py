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
        ttk.Entry(conn_frame, textvariable=self.url_var, width=50).grid(row=1, column=1, sticky=tk.W, pady=2)
        
        # URL Helper buttons
        url_helper_frame = ttk.Frame(conn_frame)
        url_helper_frame.grid(row=1, column=2, sticky=tk.W, padx=(10, 0), pady=5)
        
        ttk.Button(url_helper_frame, text="Set WS URL", 
                  command=lambda: self.set_url_protocol("ws")).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(url_helper_frame, text="Set WSS URL", 
                  command=lambda: self.set_url_protocol("wss")).pack(side=tk.LEFT)
        
        ttk.Label(conn_frame, text="Password:").grid(row=2, column=0, sticky=tk.W, pady=2)
        self.password_var = tk.StringVar(value="")
        ttk.Entry(conn_frame, textvariable=self.password_var, show="*", width=30).grid(row=2, column=1, sticky=tk.W, pady=2)
        
        ttk.Label(conn_frame, text="Heartbeat Interval (s):").grid(row=3, column=0, sticky=tk.W, pady=2)
        self.heartbeat_var = tk.StringVar(value="60")
        ttk.Entry(conn_frame, textvariable=self.heartbeat_var, width=10).grid(row=3, column=1, sticky=tk.W, pady=2)
        
        # TLS settings
        tls_frame = ttk.LabelFrame(parent, text="TLS Settings", padding=10)
        tls_frame.pack(fill=tk.X, pady=5)
        
        self.use_tls_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(tls_frame, text="Use TLS/SSL", variable=self.use_tls_var).grid(row=0, column=0, sticky=tk.W, pady=2)
        
        ttk.Label(tls_frame, text="CA Certificate:").grid(row=1, column=0, sticky=tk.W, pady=2)
        self.ca_cert_var = tk.StringVar(value="")
        ttk.Entry(tls_frame, textvariable=self.ca_cert_var, width=40).grid(row=1, column=1, sticky=tk.W, pady=2)
        ttk.Button(tls_frame, text="Browse", command=self.browse_certificate).grid(row=1, column=2, sticky=tk.W, padx=5, pady=2)
        
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
        
        ttk.Label(charger_frame, text="Max Power (W):").grid(row=5, column=0, sticky=tk.W, pady=2)
        self.max_power_var = tk.StringVar(value="11000")
        ttk.Entry(charger_frame, textvariable=self.max_power_var, width=30).grid(row=5, column=1, sticky=tk.W, pady=2)
        
        ttk.Label(charger_frame, text="Max Current (A):").grid(row=6, column=0, sticky=tk.W, pady=2)
        self.max_current_var = tk.StringVar(value="48")
        ttk.Entry(charger_frame, textvariable=self.max_current_var, width=30).grid(row=6, column=1, sticky=tk.W, pady=2)
        
        # Configuration management
        config_mgmt_frame = ttk.LabelFrame(parent, text="Configuration Management", padding=10)
        config_mgmt_frame.pack(fill=tk.X, pady=5)
        
        ttk.Button(config_mgmt_frame, text="Manage Configuration Keys", 
                  command=self.manage_config_keys).pack(side=tk.LEFT, padx=5)
        
        # Connection controls
        conn_controls_frame = ttk.Frame(parent)
        conn_controls_frame.pack(fill=tk.X, pady=10)
        
        self.connect_btn = ttk.Button(conn_controls_frame, text="Connect", command=self.connect_charger)
        self.connect_btn.pack(side=tk.LEFT, padx=5)
        
        self.disconnect_btn = ttk.Button(conn_controls_frame, text="Disconnect", command=self.disconnect_charger, state=tk.DISABLED)
        self.disconnect_btn.pack(side=tk.LEFT, padx=5)
        
        # Status display
        status_frame = ttk.Frame(parent)
        status_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(status_frame, text="Status:").pack(side=tk.LEFT)
        self.status_var = tk.StringVar(value="Disconnected")
        self.status_label = ttk.Label(status_frame, textvariable=self.status_var, foreground="red")
        self.status_label.pack(side=tk.LEFT, padx=5)
        
        self.connection_info_var = tk.StringVar(value="")
        ttk.Label(status_frame, textvariable=self.connection_info_var).pack(side=tk.LEFT, padx=5)

    def set_url_protocol(self, protocol):
        """Set URL protocol (ws or wss)"""
        current_url = self.url_var.get()
        
        # Remove existing protocol
        if current_url.startswith("ws://"):
            base_url = current_url[5:]
        elif current_url.startswith("wss://"):
            base_url = current_url[6:]
        else:
            base_url = current_url
        
        # Set new protocol
        new_url = f"{protocol}://{base_url}"
        self.url_var.set(new_url)
        
        # Update TLS setting accordingly
        self.use_tls_var.set(protocol == "wss")

    def manage_config_keys(self):
        """Open configuration keys management dialog"""
        # Get current keys from simulator if connected, otherwise use saved keys
        if self.simulator:
            self.config_keys = self.simulator.get_configuration_keys_list()
        
        dialog = ConfigurationDialog(self.root, self.config_keys)
        self.root.wait_window(dialog)
        
        if hasattr(dialog, 'result') and dialog.result:
            self.config_keys = dialog.result

    def setup_control_tab(self, parent):
        """Setup control tab"""
        # Manual message sending
        manual_frame = ttk.LabelFrame(parent, text="Manual Messages", padding=10)
        manual_frame.pack(fill=tk.X, pady=5)
        
        # Heartbeat
        ttk.Button(manual_frame, text="Send Heartbeat", command=self.send_heartbeat).pack(side=tk.LEFT, padx=5)
        
        # Status notifications
        status_frame = ttk.Frame(manual_frame)
        status_frame.pack(side=tk.LEFT, padx=10)
        
        ttk.Label(status_frame, text="Connector:").pack(side=tk.LEFT)
        self.connector_id_var = tk.StringVar(value="1")
        ttk.Spinbox(status_frame, textvariable=self.connector_id_var, from_=0, to=10, width=5).pack(side=tk.LEFT, padx=5)
        
        ttk.Button(status_frame, text="Set Available", command=lambda: self.send_status("Available")).pack(side=tk.LEFT, padx=5)
        ttk.Button(status_frame, text="Set Preparing", command=lambda: self.send_status("Preparing")).pack(side=tk.LEFT, padx=5)
        ttk.Button(status_frame, text="Set Charging", command=lambda: self.send_status("Charging")).pack(side=tk.LEFT, padx=5)
        ttk.Button(status_frame, text="Set Finishing", command=lambda: self.send_status("Finishing")).pack(side=tk.LEFT, padx=5)
        ttk.Button(status_frame, text="Set Unavailable", command=lambda: self.send_status("Unavailable")).pack(side=tk.LEFT, padx=5)
        ttk.Button(status_frame, text="Set Faulted", command=lambda: self.send_status("Faulted")).pack(side=tk.LEFT, padx=5)
        
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

    def setup_charging_profiles_tab(self, parent):
        """Setup charging profiles tab - Display only, no sending functionality"""
        main_frame = ttk.Frame(parent)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Information Label
        info_frame = ttk.LabelFrame(main_frame, text="Information", padding=10)
        info_frame.pack(fill=tk.X, pady=5)
        
        info_text = ("This simulator responds to SetChargingProfile requests from the server.\n"
                    "When charging profiles are received, meter values are automatically adjusted.\n"
                    "Active profiles and their effects on power/current limits are shown below.")
        
        ttk.Label(info_frame, text=info_text, wraplength=600, justify=tk.LEFT).pack()
        
        # Control Buttons Frame (only for clearing and getting schedules)
        control_frame = ttk.Frame(main_frame)
        control_frame.pack(fill=tk.X, pady=10)
        
        ttk.Button(control_frame, text="Clear All Charging Profiles", 
                  command=self.clear_all_charging_profiles).pack(side=tk.LEFT, padx=5)
        
        ttk.Button(control_frame, text="Get Composite Schedule", 
                  command=self.get_composite_schedule).pack(side=tk.LEFT, padx=5)
        
        ttk.Button(control_frame, text="Refresh Display", 
                  command=self.update_profiles_display).pack(side=tk.LEFT, padx=5)
        
        # Status Display
        status_frame = ttk.LabelFrame(main_frame, text="Active Charging Profiles & Current Limits", padding=10)
        status_frame.pack(fill=tk.BOTH, expand=True)
        
        self.profiles_text = tk.Text(status_frame, height=15, width=80)
        profiles_scrollbar = ttk.Scrollbar(status_frame, orient=tk.VERTICAL, command=self.profiles_text.yview)
        self.profiles_text.configure(yscrollcommand=profiles_scrollbar.set)
        
        self.profiles_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        profiles_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.profiles_text.config(state=tk.DISABLED)
        
        # Auto-refresh timer
        self.schedule_profiles_update()

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
                
            max_power = float(self.max_power_var.get())
            if max_power <= 0:
                messagebox.showerror("Error", "Max power must be greater than 0")
                return
                
            max_current = float(self.max_current_var.get())
            if max_current <= 0:
                messagebox.showerror("Error", "Max current must be greater than 0")
                return
        except ValueError:
            messagebox.showerror("Error", "Invalid numeric values")
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
            'max_power': max_power,
            'max_current': max_current,
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
            
            # Debug: Check if simulator has connect method
            if not hasattr(self.simulator, 'connect'):
                error_msg = f"Simulator object does not have 'connect' method. Available methods: {[m for m in dir(self.simulator) if not m.startswith('_')]}"
                self.update_log(f"[ERROR] {error_msg}")
                return
            
            self.loop.run_until_complete(self.simulator.connect())
            
            # Start periodic updates for active transactions
            if self.simulator and self.simulator.is_connected:
                self.root.after(0, self.update_status_connected)
                self.root.after(2000, self.periodic_transaction_update)
        except Exception as e:
            # Use safer logging that doesn't depend on simulator state
            error_msg = f"Connection error: {e}"
            if self.simulator and hasattr(self.simulator, 'log'):
                self.simulator.log(error_msg, "ERROR")
            else:
                # Fallback to GUI update if simulator logging is not available
                self.update_log(f"[ERROR] {error_msg}")
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

    def clear_all_charging_profiles(self):
        """Clear all charging profiles from all connectors"""
        try:
            if not self.simulator:
                messagebox.showerror("Error", "Simulator not connected")
                return
            
            # Clear all profiles by sending ClearChargingProfile with no specific criteria
            message = {}  # Empty message clears all profiles
            
            from ocpp_enums import OCPPAction
            asyncio.run_coroutine_threadsafe(
                self.simulator.send_call("ClearChargingProfile", message),
                self.loop
            )
            
            self.update_profiles_display()
            messagebox.showinfo("Success", "Request to clear all charging profiles sent")
            
        except Exception as e:
            messagebox.showerror("Error", f"Error clearing charging profiles: {e}")

    def get_composite_schedule(self):
        """Get composite schedule for a connector"""
        try:
            if not self.simulator:
                messagebox.showerror("Error", "Simulator not connected")
                return
            
            # Simple dialog to get connector ID and duration
            connector_dialog = tk.Toplevel(self.root)
            connector_dialog.title("Get Composite Schedule")
            connector_dialog.geometry("300x200")
            connector_dialog.transient(self.root)
            connector_dialog.grab_set()
            
            ttk.Label(connector_dialog, text="Connector ID:").pack(pady=5)
            connector_var = tk.StringVar(value="1")
            ttk.Entry(connector_dialog, textvariable=connector_var, width=10).pack(pady=5)
            
            ttk.Label(connector_dialog, text="Duration (seconds):").pack(pady=5)
            duration_var = tk.StringVar(value="3600")
            ttk.Entry(connector_dialog, textvariable=duration_var, width=10).pack(pady=5)
            
            def send_request():
                try:
                    message = {
                        "connectorId": int(connector_var.get()),
                        "duration": int(duration_var.get())
                    }
                    
                    from ocpp_enums import OCPPAction
                    asyncio.run_coroutine_threadsafe(
                        self.simulator.send_call("GetCompositeSchedule", message),
                        self.loop
                    )
                    
                    connector_dialog.destroy()
                    messagebox.showinfo("Success", "GetCompositeSchedule request sent")
                    
                except ValueError:
                    messagebox.showerror("Error", "Please enter valid numeric values")
                except Exception as e:
                    messagebox.showerror("Error", f"Error sending request: {e}")
            
            ttk.Button(connector_dialog, text="Send Request", command=send_request).pack(pady=10)
            ttk.Button(connector_dialog, text="Cancel", command=connector_dialog.destroy).pack(pady=5)
            
        except Exception as e:
            messagebox.showerror("Error", f"Error getting composite schedule: {e}")

    def schedule_profiles_update(self):
        """Schedule periodic updates of the profiles display"""
        self.update_profiles_display()
        # Schedule next update in 5 seconds
        self.root.after(5000, self.schedule_profiles_update)

    def update_profiles_display(self):
        """Update the active charging profiles display with enhanced information"""
        if not self.simulator or not hasattr(self.simulator, 'charging_profiles_manager'):
            self.profiles_text.config(state=tk.NORMAL)
            self.profiles_text.delete(1.0, tk.END)
            self.profiles_text.insert(tk.END, "Simulator not connected or charging profiles not initialized")
            self.profiles_text.config(state=tk.DISABLED)
            return
        
        self.profiles_text.config(state=tk.NORMAL)
        self.profiles_text.delete(1.0, tk.END)
        
        profiles_manager = self.simulator.charging_profiles_manager
        any_profiles = False
        
        # Display active profiles for each connector
        for connector_id in range(self.simulator.number_of_connectors + 1):
            profiles = profiles_manager.charging_profiles.get(connector_id, [])
            if profiles:
                any_profiles = True
                self.profiles_text.insert(tk.END, f"═══ Connector {connector_id} ═══\n")
                
                for i, profile in enumerate(profiles):
                    self.profiles_text.insert(tk.END, f"Profile {i+1}:\n")
                    self.profiles_text.insert(tk.END, f"  • ID: {profile.charging_profile_id}\n")
                    self.profiles_text.insert(tk.END, f"  • Stack Level: {profile.stack_level}\n")
                    self.profiles_text.insert(tk.END, f"  • Purpose: {profile.charging_profile_purpose}\n")
                    self.profiles_text.insert(tk.END, f"  • Kind: {profile.charging_profile_kind}\n")
                    self.profiles_text.insert(tk.END, f"  • Rate Unit: {profile.charging_rate_unit}\n")
                    
                    if hasattr(profile, 'start_schedule') and profile.start_schedule:
                        self.profiles_text.insert(tk.END, f"  • Start Schedule: {profile.start_schedule}\n")
                    
                    if hasattr(profile, 'duration') and profile.duration:
                        self.profiles_text.insert(tk.END, f"  • Duration: {profile.duration}s\n")
                    
                    # Show schedule periods
                    self.profiles_text.insert(tk.END, f"  • Schedule Periods:\n")
                    for j, period in enumerate(profile.charging_schedule_periods):
                        start = period.get('startPeriod', 0)
                        limit = period.get('limit', 0)
                        self.profiles_text.insert(tk.END, 
                            f"    {j+1}. Start: {start}s, Limit: {limit} {profile.charging_rate_unit}\n")
                
                # Show current effective limits
                limits = profiles_manager.get_current_limit(connector_id)
                if limits['power'] is not None or limits['current'] is not None:
                    self.profiles_text.insert(tk.END, f"\n🔧 CURRENT EFFECTIVE LIMITS:\n")
                    if limits['power'] is not None:
                        self.profiles_text.insert(tk.END, f"  • Power Limit: {limits['power']:.1f} W\n")
                    if limits['current'] is not None:
                        self.profiles_text.insert(tk.END, f"  • Current Limit: {limits['current']:.1f} A\n")
                    
                    # Show meter value adjustments
                    if (hasattr(self.simulator, 'meter_handler') and 
                        connector_id in self.simulator.meter_handler.meter_values):
                        meter_vals = self.simulator.meter_handler.meter_values[connector_id]
                        self.profiles_text.insert(tk.END, f"\n📊 ADJUSTED METER VALUES:\n")
                        if "Power.Active.Import" in meter_vals:
                            self.profiles_text.insert(tk.END, f"  • Power.Active.Import: {meter_vals['Power.Active.Import']:.1f} W\n")
                        if "Current.Import" in meter_vals:
                            self.profiles_text.insert(tk.END, f"  • Current.Import: {meter_vals['Current.Import']:.1f} A\n")
                
                self.profiles_text.insert(tk.END, "\n" + "─" * 60 + "\n\n")
        
        if not any_profiles:
            self.profiles_text.insert(tk.END, "📋 No active charging profiles\n\n")
            self.profiles_text.insert(tk.END, "The simulator is ready to receive SetChargingProfile requests from the server.\n")
            self.profiles_text.insert(tk.END, "When profiles are received, they will be displayed here and meter values will be adjusted automatically.")
        
        # Add timestamp
        from datetime import datetime
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.profiles_text.insert(tk.END, f"\n\n⏰ Last updated: {timestamp}")
        
        self.profiles_text.config(state=tk.DISABLED)

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