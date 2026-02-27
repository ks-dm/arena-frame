#!/usr/bin/env python3
"""
Button handler for Arena Frame
Button A: Hold to enter AP mode for configuration
"""
import signal
import subprocess
from gpiozero import Button

# GPIO pin for Button A (top button)
BUTTON_A_PIN = 5
AP_MODE_FLAG = "/tmp/force_ap_mode"
HOLD_TIME = 3  # Seconds to hold for AP mode

# Track button state
button_held = False


def create_ap_flag():
    """Create flag file to trigger AP mode"""
    with open(AP_MODE_FLAG, 'w') as f:
        f.write('1')
    print("AP mode flag created")


def trigger_ap_mode():
    """Force wifi-manager to enter AP mode"""
    print("Triggering AP mode...")
    create_ap_flag()
    subprocess.run(['sudo', 'systemctl', 'restart', 'wifi-manager'])
    print("AP mode triggered - connect to ArenaFrame-Setup to configure")


def handle_button_a_held():
    """Button A held - enter AP mode"""
    global button_held
    button_held = True
    print(f"Button A held for {HOLD_TIME}s - entering AP mode...")
    trigger_ap_mode()


def handle_button_a_released():
    """Button A released"""
    global button_held
    if not button_held:
        print(f"Button A pressed (hold for {HOLD_TIME}s to enter setup mode)")
    button_held = False


def main():
    print("Arena Frame Button Handler")
    print("==========================")
    print(f"Button A (hold {HOLD_TIME}s): Enter AP setup mode")
    print("")
    print("Press Ctrl+C to exit")
    print("")
    
    # Set up Button A only (GPIO 5)
    btn_a = Button(BUTTON_A_PIN, hold_time=HOLD_TIME)
    
    # Assign handlers
    btn_a.when_held = handle_button_a_held
    btn_a.when_released = handle_button_a_released
    
    # Keep running
    signal.pause()


if __name__ == "__main__":
    main()
