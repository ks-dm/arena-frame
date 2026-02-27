"""Dithering algorithms for e-ink display.

Currently uses PIL's built-in dithering via Image.quantize().
Designed as a plugin point for future algorithms (Atkinson, Floyd-Steinberg, etc.).
"""

from PIL import Image


def default_dither(image: Image.Image, palette: list[tuple] | None = None) -> Image.Image:
    """Apply default dithering (PIL built-in).

    The Inky library handles palette conversion internally,
    so this is a pass-through for now.
    """
    return image


DITHER_ALGORITHMS = {
    "default": default_dither,
}


def get_ditherer(name="default"):
    return DITHER_ALGORITHMS.get(name, default_dither)
