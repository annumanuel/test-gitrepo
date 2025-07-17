# debug_imports.py
"""Debug script to check imports"""

import sys
import os

print(f"Python version: {sys.version}")
print(f"Current directory: {os.getcwd()}")
print(f"Files in directory: {os.listdir('.')}")
print("\nChecking imports...")

try:
    import tkinter
    print("✓ tkinter imported successfully")
except ImportError as e:
    print(f"✗ tkinter import failed: {e}")

try:
    import websockets
    print("✓ websockets imported successfully")
except ImportError as e:
    print(f"✗ websockets import failed: {e}")

try:
    import asyncio
    print("✓ asyncio imported successfully")
except ImportError as e:
    print(f"✗ asyncio import failed: {e}")

print("\nChecking local modules...")

try:
    import ocpp_enums
    print("✓ ocpp_enums imported successfully")
except ImportError as e:
    print(f"✗ ocpp_enums import failed: {e}")

try:
    import configuration_keys
    print("✓ configuration_keys imported successfully")
except ImportError as e:
    print(f"✗ configuration_keys import failed: {e}")

try:
    import meter_values
    print("✓ meter_values imported successfully")
except ImportError as e:
    print(f"✗ meter_values import failed: {e}")

try:
    import message_handlers
    print("✓ message_handlers imported successfully")
except ImportError as e:
    print(f"✗ message_handlers import failed: {e}")

try:
    import ev_charger_simulator
    print("✓ ev_charger_simulator imported successfully")
except ImportError as e:
    print(f"✗ ev_charger_simulator import failed: {e}")

try:
    import gui_dialogs
    print("✓ gui_dialogs imported successfully")
except ImportError as e:
    print(f"✗ gui_dialogs import failed: {e}")

try:
    import gui_main
    print("✓ gui_main imported successfully")
except ImportError as e:
    print(f"✗ gui_main import failed: {e}")

print("\nImport chain complete!")
