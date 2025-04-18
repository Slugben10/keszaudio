#!/usr/bin/env python3
import os
import sys
import subprocess

def main():
    # Set environment variables to bypass macOS GUI restrictions
    os.environ['WXMAC_NO_NATIVE_MENUBAR'] = '1'
    os.environ['PYOBJC_DISABLE_CONFIRMATION'] = '1'
    os.environ['QT_MAC_WANTS_LAYER'] = '1'
    os.environ['PYTHONHASHSEED'] = '1'
    
    # Force wxPython to use basic capabilities
    os.environ['WX_NO_NATIVE'] = '1'
    
    # Suppress PyAudio warnings
    os.environ['PYTHONWARNINGS'] = 'ignore::DeprecationWarning'
    
    # Get the path to the main.py script
    main_script = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'main.py')
    
    # Ask if user wants GUI or CLI mode
    try:
        mode = input("Run in GUI mode (y/n)? ").strip().lower()
        if mode == 'y' or mode == 'yes':
            # Try running with pythonw for macOS GUI
            if sys.platform == 'darwin':
                try:
                    # Check if pythonw exists
                    pythonw_path = os.path.join(os.path.dirname(sys.executable), 'pythonw')
                    if os.path.exists(pythonw_path):
                        print("Starting GUI with pythonw...")
                        subprocess.run([pythonw_path, main_script])
                        return 0
                except Exception:
                    pass
            
            # Fall back to standard python with GUI
            print("Starting GUI mode...")
            subprocess.run([sys.executable, main_script])
        else:
            # Run in CLI mode
            print("Starting CLI mode...")
            subprocess.run([sys.executable, main_script, "--cli"])
    except KeyboardInterrupt:
        print("\nApplication startup canceled by user.")
    except Exception as e:
        print(f"Error running application: {e}")
        return 1
    
    return 0

if __name__ == "__main__":
    sys.exit(main()) 