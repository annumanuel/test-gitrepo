# main.py
"""Main entry point for EV Charger Simulator"""

import sys
import tkinter as tk
from gui_main import EVChargerSimulatorGUI


def main():
    """Main function"""
    # Handle both GUI and CLI modes
    if len(sys.argv) > 1 and sys.argv[1] == "--cli":
        # CLI mode
        print("CLI mode not implemented yet. Please run without arguments for GUI mode.")
        sys.exit(1)
    else:
        # GUI mode (default)
        root = tk.Tk()
        app = EVChargerSimulatorGUI(root)
        root.mainloop()


if __name__ == "__main__":
    main()
