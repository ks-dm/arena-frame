#!/usr/bin/env python3
"""LED blinker for Inky — indicates AP setup mode is active."""

import time
import signal
import sys

LED_PIN = 13
running = True


def signal_handler(sig, frame):
    global running
    running = False


def main():
    try:
        import gpiod
        import gpiodevice
        from gpiod.line import Bias, Direction, Value
    except ImportError:
        print("gpiod/gpiodevice not available")
        sys.exit(1)

    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    try:
        chip = gpiodevice.find_chip_by_platform()
        led = chip.line_offset_from_id(LED_PIN)
        gpio = chip.request_lines(
            consumer="inky-led",
            config={led: gpiod.LineSettings(direction=Direction.OUTPUT, bias=Bias.DISABLED)},
        )

        print("LED blinker started")

        while running:
            gpio.set_value(led, Value.ACTIVE)
            time.sleep(0.5)
            if not running:
                break
            gpio.set_value(led, Value.INACTIVE)
            time.sleep(0.5)

        gpio.set_value(led, Value.INACTIVE)
        print("LED blinker stopped")

    except Exception as e:
        print(f"LED error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
