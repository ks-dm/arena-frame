"""E-ink display hardware abstraction.

Wraps Pimoroni's Inky library with lazy loading so modules can be
imported on machines without the hardware present.
"""

from PIL import Image


class EinkDisplay:
    """Thin wrapper around Inky Impression for e-ink output."""

    def __init__(self):
        from inky.auto import auto
        self._display = auto()
        self._final_w, self._final_h = self._display.resolution

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
