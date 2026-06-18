import sys
import os
import time
import subprocess
import argparse

def main():
    parser = argparse.ArgumentParser(description='MCL Updater Helper')
    parser.add_argument('--current', required=True, help='Path to the current executable')
    parser.add_argument('--update', required=True, help='Path to the downloaded update file')
    args = parser.parse_args()

    current_exe = os.path.abspath(args.current)
    update_exe = os.path.abspath(args.update)

    # Wait for the main process to exit
    name = os.path.basename(current_exe)
    while True:
        # Check if process is still running
        result = subprocess.run(
            ['tasklist', '/FI', f'IMAGENAME eq {name}'],
            capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW
        )
        if name not in result.stdout:
            break
        time.sleep(0.5)

    # Small extra delay to ensure file handles are released
    time.sleep(1)

    # Replace the old executable
    try:
        os.replace(update_exe, current_exe)   # atomic replace (Python 3.3+)
    except Exception as e:
        # Fallback: copy + delete
        import shutil
        shutil.copy2(update_exe, current_exe)
        os.remove(update_exe)

    # Launch the new launcher
    subprocess.Popen([current_exe], creationflags=subprocess.CREATE_NO_WINDOW)

if __name__ == '__main__':
    main()
