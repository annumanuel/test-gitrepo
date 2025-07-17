# gui_dialogs.py
"""GUI Dialogs for Configuration Management"""

import tkinter as tk
from tkinter import ttk, messagebox
from typing import List, Dict, Any, Optional


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
