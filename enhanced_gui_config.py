# Enhanced gui_main.py - Configuration section with Max Power setting

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
    
    # Charger properties with enhanced Max Power setting
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
    
    # Enhanced Maximum power configuration
    max_power_frame = ttk.Frame(charger_frame)
    max_power_frame.grid(row=5, column=0, columnspan=3, sticky=tk.W, pady=10)
    
    ttk.Label(max_power_frame, text="Maximum Charger Power:", font=('TkDefaultFont', 9, 'bold')).grid(row=0, column=0, sticky=tk.W, pady=2)
    
    # Power input with validation
    power_input_frame = ttk.Frame(max_power_frame)
    power_input_frame.grid(row=1, column=0, columnspan=3, sticky=tk.W, pady=2)
    
    self.max_power_var = tk.StringVar(value="22000")
    power_entry = ttk.Entry(power_input_frame, textvariable=self.max_power_var, width=15)
    power_entry.grid(row=0, column=0, padx=(0, 5))
    
    ttk.Label(power_input_frame, text="Watts").grid(row=0, column=1, padx=(0, 10))
    
    # Power presets
    presets_frame = ttk.Frame(power_input_frame)
    presets_frame.grid(row=0, column=2, padx=(10, 0))
    
    ttk.Button(presets_frame, text="3.7kW", width=6, 
              command=lambda: self.max_power_var.set("3700")).grid(row=0, column=0, padx=2)
    ttk.Button(presets_frame, text="7.4kW", width=6, 
              command=lambda: self.max_power_var.set("7400")).grid(row=0, column=1, padx=2)
    ttk.Button(presets_frame, text="11kW", width=6, 
              command=lambda: self.max_power_var.set("11000")).grid(row=0, column=2, padx=2)
    ttk.Button(presets_frame, text="22kW", width=6, 
              command=lambda: self.max_power_var.set("22000")).grid(row=0, column=3, padx=2)
    ttk.Button(presets_frame, text="50kW", width=6, 
              command=lambda: self.max_power_var.set("50000")).grid(row=0, column=4, padx=2)
    
    # Power information
    info_frame = ttk.Frame(max_power_frame)
    info_frame.grid(row=2, column=0, columnspan=3, sticky=tk.W, pady=(5, 0))
    
    ttk.Label(info_frame, text="ℹ️ This is the maximum power your charger can deliver.", 
             foreground="blue", font=('TkDefaultFont', 8)).grid(row=0, column=0, sticky=tk.W)
    ttk.Label(info_frame, text="  SetChargingProfile requests exceeding this limit will be rejected.", 
             foreground="blue", font=('TkDefaultFont', 8)).grid(row=1, column=0, sticky=tk.W)
    
    # Current/Power relationship display
    self.power_info_var = tk.StringVar()
    self.update_power_info()
    ttk.Label(info_frame, textvariable=self.power_info_var, 
             foreground="gray", font=('TkDefaultFont', 8)).grid(row=2, column=0, sticky=tk.W, pady=(5, 0))
    
    # Bind power entry to update info
    power_entry.bind('<KeyRelease>', lambda e: self.update_power_info())
    
    # Security settings (keeping existing TLS configuration)
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

def update_power_info(self):
    """Update power information display"""
    try:
        power_watts = int(self.max_power_var.get())
        power_kw = power_watts / 1000
        
        # Calculate approximate current (assuming 230V single phase for AC, 400V for DC)
        current_single_phase = power_watts / 230  # A
        current_three_phase = power_watts / (400 * 1.732)  # A for 3-phase
        
        if power_watts >= 50000:  # DC Fast charging
            info_text = f"≈ {power_kw:.1f}kW DC Fast Charging ({current_single_phase/3:.0f}A per connector)"
        elif power_watts >= 11000:  # 3-phase AC
            info_text = f"≈ {power_kw:.1f}kW (3-phase AC: {current_three_phase:.1f}A per phase)"
        else:  # Single phase AC
            info_text = f"≈ {power_kw:.1f}kW (single-phase AC: {current_single_phase:.1f}A)"
        
        self.power_info_var.set(f"💡 {info_text}")
        
    except ValueError:
        self.power_info_var.set("💡 Enter a valid power value")

def apply_config(self):
    """Apply configuration to simulator with enhanced validation"""
    try:
        num_connectors = int(self.num_connectors_var.get())
        if num_connectors < 1 or num_connectors > 10:
            messagebox.showerror("Error", "Number of connectors must be between 1 and 10")
            return
            
        max_power = int(self.max_power_var.get())
        if max_power < 1000:  # Minimum 1kW
            messagebox.showerror("Error", "Maximum power must be at least 1000W (1kW)")
            return
        elif max_power > 1000000:  # Maximum 1MW
            messagebox.showerror("Error", "Maximum power cannot exceed 1,000,000W (1MW)")
            return
            
        # Validate power makes sense for connector type
        if max_power > 50000 and num_connectors > 4:
            if not messagebox.askyesno("High Power Warning", 
                                     f"You've configured {max_power/1000:.1f}kW with {num_connectors} connectors.\n"
                                     f"This is typically used for DC fast charging with fewer connectors.\n"
                                     f"Continue anyway?"):
                return
                
    except ValueError:
        messagebox.showerror("Error", "Invalid number values in configuration")
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
        'max_power': max_power,  # This will be used by charging profile handler
        'configuration_keys': self.config_keys
    }
    
    self.simulator = EVChargerSimulator(config, gui_callback=self.update_log)
    
    # Update connector spinbox maximum values
    self.connector_id_var.set("1")
    self.transaction_connector_var.set("1")
    
    # Show configuration summary
    self.show_config_summary(max_power, num_connectors)