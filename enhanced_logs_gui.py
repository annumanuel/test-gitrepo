# Enhanced logs tab for gui_main.py

import re
from datetime import datetime

# Add these to the EVChargerSimulatorGUI class __init__ method:
def __init__(self, root):
    # ... existing code ...
    self.log_entries = []  # Store all log entries
    self.filtered_log_entries = []  # Store filtered entries
    
# Replace the setup_log_tab method with this enhanced version:
def setup_log_tab(self, parent):
    """Setup enhanced log tab with search and table"""
    log_frame = ttk.Frame(parent)
    log_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
    
    # Search and filter frame
    search_frame = ttk.Frame(log_frame)
    search_frame.pack(fill=tk.X, pady=(0, 10))
    
    # Search bar
    ttk.Label(search_frame, text="Search:").pack(side=tk.LEFT, padx=(0, 5))
    self.search_var = tk.StringVar()
    self.search_var.trace('w', self.filter_logs)
    search_entry = ttk.Entry(search_frame, textvariable=self.search_var, width=30)
    search_entry.pack(side=tk.LEFT, padx=(0, 10))
    
    # Level filter
    ttk.Label(search_frame, text="Level:").pack(side=tk.LEFT, padx=(0, 5))
    self.level_filter_var = tk.StringVar(value="ALL")
    level_combo = ttk.Combobox(search_frame, textvariable=self.level_filter_var, 
                              values=["ALL", "INFO", "WARNING", "ERROR"], width=10)
    level_combo.pack(side=tk.LEFT, padx=(0, 10))
    level_combo.bind('<<ComboboxSelected>>', lambda e: self.filter_logs())
    
    # Component filter
    ttk.Label(search_frame, text="Component:").pack(side=tk.LEFT, padx=(0, 5))
    self.component_filter_var = tk.StringVar(value="ALL")
    self.component_combo = ttk.Combobox(search_frame, textvariable=self.component_filter_var, 
                                       values=["ALL"], width=15)
    self.component_combo.pack(side=tk.LEFT, padx=(0, 10))
    self.component_combo.bind('<<ComboboxSelected>>', lambda e: self.filter_logs())
    
    # Clear and export buttons
    ttk.Button(search_frame, text="Clear Logs", command=self.clear_logs).pack(side=tk.RIGHT, padx=(5, 0))
    ttk.Button(search_frame, text="Export Logs", command=self.export_logs).pack(side=tk.RIGHT, padx=(5, 0))
    ttk.Button(search_frame, text="Auto-scroll", command=self.toggle_autoscroll).pack(side=tk.RIGHT, padx=(5, 0))
    
    # Status bar
    status_frame = ttk.Frame(log_frame)
    status_frame.pack(fill=tk.X, pady=(0, 5))
    
    self.log_status_var = tk.StringVar(value="0 log entries")
    ttk.Label(status_frame, textvariable=self.log_status_var).pack(side=tk.LEFT)
    
    self.autoscroll_var = tk.BooleanVar(value=True)
    self.autoscroll_status = ttk.Label(status_frame, text="Auto-scroll: ON", foreground="green")
    self.autoscroll_status.pack(side=tk.RIGHT)
    
    # Create treeview for log table
    tree_frame = ttk.Frame(log_frame)
    tree_frame.pack(fill=tk.BOTH, expand=True)
    
    # Scrollbars
    v_scrollbar = ttk.Scrollbar(tree_frame, orient="vertical")
    h_scrollbar = ttk.Scrollbar(tree_frame, orient="horizontal")
    
    # Treeview
    self.log_tree = ttk.Treeview(tree_frame,
                                columns=('time', 'level', 'component', 'message'),
                                show='headings',
                                yscrollcommand=v_scrollbar.set,
                                xscrollcommand=h_scrollbar.set)
    
    # Configure scrollbars
    v_scrollbar.config(command=self.log_tree.yview)
    h_scrollbar.config(command=self.log_tree.xview)
    
    # Configure columns
    self.log_tree.heading('time', text='Timestamp')
    self.log_tree.heading('level', text='Level')
    self.log_tree.heading('component', text='Component')
    self.log_tree.heading('message', text='Message')
    
    # Set column widths
    self.log_tree.column('time', width=120, minwidth=100)
    self.log_tree.column('level', width=80, minwidth=60)
    self.log_tree.column('component', width=150, minwidth=100)
    self.log_tree.column('message', width=500, minwidth=200)
    
    # Configure row colors based on log level
    self.log_tree.tag_configure('INFO', background='white')
    self.log_tree.tag_configure('WARNING', background='#fff3cd', foreground='#856404')
    self.log_tree.tag_configure('ERROR', background='#f8d7da', foreground='#721c24')
    
    # Pack treeview and scrollbars
    self.log_tree.grid(row=0, column=0, sticky='nsew')
    v_scrollbar.grid(row=0, column=1, sticky='ns')
    h_scrollbar.grid(row=1, column=0, sticky='ew')
    
    tree_frame.grid_rowconfigure(0, weight=1)
    tree_frame.grid_columnconfigure(0, weight=1)
    
    # Bind double-click to show full message
    self.log_tree.bind('<Double-1>', self.show_full_log_message)

# Replace the update_log method:
def update_log(self, message):
    """Update log display (thread-safe)"""
    def _update():
        # Parse log message
        log_entry = self.parse_log_message(message)
        self.log_entries.append(log_entry)
        
        # Update component filter dropdown
        self.update_component_filter()
        
        # Apply current filters
        self.filter_logs()
        
        # Auto-scroll if enabled
        if self.autoscroll_var.get():
            self.log_tree.see(self.log_tree.get_children()[-1] if self.log_tree.get_children() else '')
    
    self.root.after(0, _update)

def parse_log_message(self, message):
    """Parse log message into components"""
    # Expected format: [HH:MM:SS] LEVEL: message
    pattern = r'\[(\d{2}:\d{2}:\d{2})\]\s+(\w+):\s+(.*)'
    match = re.match(pattern, message)
    
    if match:
        time_str, level, msg = match.groups()
        
        # Extract component from message if possible
        component = "Simulator"
        if "ChargingProfiles" in msg:
            component = "ChargingProfiles"
        elif "MeterValues" in msg:
            component = "MeterValues"
        elif "Configuration" in msg:
            component = "Configuration"
        elif "Connection" in msg:
            component = "Connection"
        elif "Transaction" in msg:
            component = "Transaction"
        elif "Heartbeat" in msg:
            component = "Heartbeat"
        elif "BootNotification" in msg:
            component = "BootNotification"
        elif "Status" in msg:
            component = "StatusNotification"
        elif "Reset" in msg:
            component = "Reset"
        
        return {
            'timestamp': time_str,
            'level': level,
            'component': component,
            'message': msg,
            'full_message': message
        }
    else:
        # Fallback for unparsed messages
        return {
            'timestamp': datetime.now().strftime("%H:%M:%S"),
            'level': 'INFO',
            'component': 'Simulator',
            'message': message,
            'full_message': message
        }

def filter_logs(self, *args):
    """Filter logs based on search criteria"""
    search_text = self.search_var.get().lower()
    level_filter = self.level_filter_var.get()
    component_filter = self.component_filter_var.get()
    
    # Clear current tree
    for item in self.log_tree.get_children():
        self.log_tree.delete(item)
    
    # Filter entries
    self.filtered_log_entries = []
    for entry in self.log_entries:
        # Apply filters
        if level_filter != "ALL" and entry['level'] != level_filter:
            continue
        if component_filter != "ALL" and entry['component'] != component_filter:
            continue
        if search_text and search_text not in entry['message'].lower():
            continue
        
        self.filtered_log_entries.append(entry)
        
        # Add to tree
        self.log_tree.insert('', 'end',
                           values=(entry['timestamp'], entry['level'], 
                                 entry['component'], entry['message']),
                           tags=(entry['level'],))
    
    # Update status
    total_entries = len(self.log_entries)
    filtered_entries = len(self.filtered_log_entries)
    self.log_status_var.set(f"{filtered_entries} of {total_entries} log entries")

def update_component_filter(self):
    """Update component filter dropdown with available components"""
    components = set(['ALL'])
    for entry in self.log_entries:
        components.add(entry['component'])
    
    self.component_combo['values'] = sorted(list(components))

def clear_logs(self):
    """Clear all log entries"""
    self.log_entries.clear()
    self.filtered_log_entries.clear()
    for item in self.log_tree.get_children():
        self.log_tree.delete(item)
    self.log_status_var.set("0 log entries")

def toggle_autoscroll(self):
    """Toggle auto-scroll functionality"""
    self.autoscroll_var.set(not self.autoscroll_var.get())
    if self.autoscroll_var.get():
        self.autoscroll_status.config(text="Auto-scroll: ON", foreground="green")
    else:
        self.autoscroll_status.config(text="Auto-scroll: OFF", foreground="red")

def show_full_log_message(self, event):
    """Show full log message in a dialog"""
    selection = self.log_tree.selection()
    if not selection:
        return
    
    item = self.log_tree.item(selection[0])
    values = item['values']
    
    # Find the full entry
    full_entry = None
    for entry in self.filtered_log_entries:
        if (entry['timestamp'] == values[0] and 
            entry['level'] == values[1] and 
            entry['component'] == values[2]):
            full_entry = entry
            break
    
    if full_entry:
        # Create dialog
        dialog = tk.Toplevel(self.root)
        dialog.title("Full Log Message")
        dialog.geometry("600x300")
        dialog.transient(self.root)
        dialog.grab_set()
        
        # Message text
        text_frame = ttk.Frame(dialog, padding=10)
        text_frame.pack(fill=tk.BOTH, expand=True)
        
        text_widget = tk.Text(text_frame, wrap=tk.WORD, width=70, height=15)
        scrollbar = ttk.Scrollbar(text_frame, orient="vertical", command=text_widget.yview)
        text_widget.config(yscrollcommand=scrollbar.set)
        
        text_widget.insert(tk.END, full_entry['full_message'])
        text_widget.config(state=tk.DISABLED)
        
        text_widget.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Close button
        ttk.Button(dialog, text="Close", command=dialog.destroy).pack(pady=10)

def export_logs(self):
    """Export logs to a file"""
    from tkinter import filedialog
    
    filename = filedialog.asksaveasfilename(
        title="Export Logs",
        defaultextension=".txt",
        filetypes=[("Text files", "*.txt"), ("CSV files", "*.csv"), ("All files", "*.*")]
    )
    
    if filename:
        try:
            with open(filename, 'w', encoding='utf-8') as f:
                if filename.endswith('.csv'):
                    f.write("Timestamp,Level,Component,Message\n")
                    for entry in self.filtered_log_entries:
                        f.write(f'"{entry["timestamp"]}","{entry["level"]}","{entry["component"]}","{entry["message"]}"\n')
                else:
                    for entry in self.filtered_log_entries:
                        f.write(f"{entry['full_message']}\n")
            
            messagebox.showinfo("Export Complete", f"Logs exported to {filename}")
        except Exception as e:
            messagebox.showerror("Export Error", f"Failed to export logs: {e}")