#!/usr/bin/env python3
"""GPIO button handler for Arena Frame.

Button A (GPIO5): Hold 3 seconds to enter AP mode for configuration.
"""

import signal
from gpiozero import Button
from utils import log, trigger_ap_mode

BUTTON_A_PIN = 5
HOLD_TIME = 3

button_held = False


def handle_button_a_held():
    global button_held
    button_held = True
    log(f"Button A held for {HOLD_TIME}s - entering AP mode...")
    trigger_ap_mode()


def handle_button_a_released():
    global button_held
    if not button_held:
        log(f"Button A pressed (hold for {HOLD_TIME}s to enter setup mode)")
    button_held = False


def main():
    log("Arena Frame Button Handler")
    log(f"Button A (hold {HOLD_TIME}s): Enter AP setup mode")

    btn_a = Button(BUTTON_A_PIN, hold_time=HOLD_TIME)
    btn_a.when_held = handle_button_a_held
    btn_a.when_released = handle_button_a_released

    signal.pause()


if __name__ == "__main__":
    main()
