"""Font loading, text measurement, wrapping, and rendering utilities."""

from PIL import ImageDraw, ImageFont
from config import FONT_DIR

FILL_GAP_PX = 50


# ---------------------------------------------------------------------------
# Font loading
# ---------------------------------------------------------------------------

def load_font_regular(size: int) -> ImageFont.ImageFont:
    font_path = FONT_DIR / "Areal-Regular.ttf"
    try:
        return ImageFont.truetype(str(font_path), size)
    except OSError:
        try:
            return ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", size)
        except OSError:
            return ImageFont.load_default()


def load_font_bold(size: int) -> ImageFont.ImageFont:
    font_path = FONT_DIR / "Areal-Bold.ttf"
    try:
        return ImageFont.truetype(str(font_path), size)
    except OSError:
        try:
            return ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", size)
        except OSError:
            return ImageFont.load_default()


# ---------------------------------------------------------------------------
# Text measurement
# ---------------------------------------------------------------------------

def text_width(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont) -> int:
    bbox = draw.textbbox((0, 0), text, font=font)
    return bbox[2] - bbox[0]


def text_height(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont) -> int:
    bbox = draw.textbbox((0, 0), text, font=font)
    return bbox[3] - bbox[1]


def ellipsize_to_fit(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, max_w: int) -> str:
    text = (text or "").strip()
    if not text:
        return ""
    if text_width(draw, text, font) <= max_w:
        return text
    ell = "…"
    lo, hi = 0, len(text)
    best = ell
    while lo <= hi:
        mid = (lo + hi) // 2
        candidate = text[:mid].rstrip() + ell
        if text_width(draw, candidate, font) <= max_w:
            best = candidate
            lo = mid + 1
        else:
            hi = mid - 1
    return best


# ---------------------------------------------------------------------------
# Word wrapping with hyphenation
# ---------------------------------------------------------------------------

def wrap_text_to_width(draw, text, font, max_w, fill_gap_px=FILL_GAP_PX):
    """Wrap text to fit within max_w pixels, with hyphenation for fill."""
    lines = []

    def w(s: str) -> int:
        return text_width(draw, s, font)

    def fits(s: str) -> bool:
        return w(s) <= max_w

    def remaining_space(prefix: str) -> int:
        return max_w - w(prefix) if prefix else max_w

    def split_to_fill(prefix: str, word: str):
        base = (prefix + " ") if prefix else ""
        lo, hi = 1, len(word) - 1
        best = None
        while lo <= hi:
            mid = (lo + hi) // 2
            cand = base + word[:mid] + "-"
            if fits(cand):
                best = mid
                lo = mid + 1
            else:
                hi = mid - 1
        if best is None:
            return None, word
        return (base + word[:best] + "-").strip(), word[best:]

    def split_long_word(word: str):
        parts = []
        while word and not fits(word):
            lo, hi = 1, len(word) - 1
            best = None
            while lo <= hi:
                mid = (lo + hi) // 2
                chunk = word[:mid] + "-"
                if fits(chunk):
                    best = mid
                    lo = mid + 1
                else:
                    hi = mid - 1
            if best is None:
                best = 1
            parts.append(word[:best] + "-")
            word = word[best:]
        if word:
            parts.append(word)
        return parts

    for para in (text or "").splitlines() or [""]:
        words = para.split()
        if not words:
            lines.append("")
            continue
        current = ""
        for word in words:
            candidate = word if not current else current + " " + word
            if fits(candidate):
                current = candidate
                continue
            if not current and not fits(word):
                parts = split_long_word(word)
                lines.extend(parts[:-1])
                current = parts[-1]
                continue
            gap = remaining_space(current)
            if gap > fill_gap_px:
                hy_line, rem = split_to_fill(current, word)
                if hy_line:
                    lines.append(hy_line)
                    if fits(rem):
                        current = rem
                    else:
                        parts = split_long_word(rem)
                        lines.extend(parts[:-1])
                        current = parts[-1]
                    continue
            if current:
                lines.append(current)
            current = ""
            if fits(word):
                current = word
            else:
                parts = split_long_word(word)
                lines.extend(parts[:-1])
                current = parts[-1]
        if current:
            lines.append(current)
    return lines


# ---------------------------------------------------------------------------
# Text rendering into boxes
# ---------------------------------------------------------------------------

def calculate_text_height(draw, text, font, box_width, padding):
    """Calculate the pixel height needed to render wrapped text."""
    max_w = box_width - 2 * padding
    lines = wrap_text_to_width(draw, text.strip(), font, max_w, fill_gap_px=FILL_GAP_PX)
    ascent, descent = font.getmetrics()
    line_h = ascent + descent + 4
    return len(lines) * line_h + 2 * padding


def render_text_in_box(draw, box_xy, box_wh, text, font, padding, text_color):
    """Render wrapped text inside a bounding box."""
    x0, y0 = box_xy
    box_w, box_h = box_wh
    max_w = box_w - 2 * padding
    max_h = box_h - 2 * padding
    lines = wrap_text_to_width(draw, text.strip(), font, max_w, fill_gap_px=FILL_GAP_PX)
    ascent, descent = font.getmetrics()
    line_h = ascent + descent + 4
    max_lines = max(1, max_h // line_h)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = ellipsize_to_fit(draw, lines[-1].rstrip(), font, max_w)
    y = y0 + padding
    for line in lines:
        draw.text((x0 + padding, y), line, font=font, fill=text_color)
        y += line_h
