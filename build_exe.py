"""Build PopNotification executable with PyInstaller.

Usage:
    pip install pyinstaller
    python build_exe.py

The compiled exe will be placed in dist/PopNotification/
"""
import subprocess
import sys
import os

if __name__ == "__main__":
    if not os.path.exists("PopNotification.spec"):
        sys.exit("Error: PopNotification.spec not found. Run this script from the project root.")

    print("Building PopNotification executable...")
    result = subprocess.run(
        [sys.executable, "-m", "PyInstaller", "--clean", "PopNotification.spec"],
        capture_output=False,
    )
    if result.returncode == 0:
        print("\nBuild successful! Executable is in dist/PopNotification/PopNotification.exe")
    else:
        sys.exit(result.returncode)
