"""E-ink display hardware abstraction.

Wraps Pimoroni's Inky library with lazy loading so modules can be
imported on machines without the hardware present.
"""

import time
from PIL import Image

AUTO_RETRIES = 3
AUTO_RETRY_DELAY = 2


class EinkDisplay:
    """Thin wrapper around Inky Impression for e-ink output."""

    def __init__(self):
        self._display = self._detect_display()
        self._final_w, self._final_h = self._display.resolution

    @staticmethod
    def _detect_display():
        """Try auto-detection with retries, fall back to Inky e673 (13.3")."""
        from inky.auto import auto

        for attempt in range(AUTO_RETRIES):
            try:
                return auto()
            except RuntimeError:
                if attempt < AUTO_RETRIES - 1:
                    print(f"EEPROM not detected (attempt {attempt + 1}/{AUTO_RETRIES}), retrying...")
                    time.sleep(AUTO_RETRY_DELAY)

        print("Auto-detection failed, falling back to Inky e673")
        from inky.inky_e673 import Inky
        return Inky()

    @property
    def canvas_size(self):
        """Working canvas dimensions (landscape, before 90° rotation)."""
        return (self._final_h, self._final_w)

    def create_canvas(self, bg_color="white"):
        """Create a new PIL Image at the working canvas size."""
        return Image.new("RGB", self.canvas_size, bg_color)

    def show(self, canvas):
        """Rotate 90° CCW and push to the e-ink display."""
        final_img = canvas.rotate(90, expand=True)
        self._display.set_image(final_img)
        self._display.show()
