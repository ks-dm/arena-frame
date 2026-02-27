#!/usr/bin/env python3
"""
Display image or text on Inky Impression
Run with pimoroni venv: ~/.virtualenvs/pimoroni/bin/python display_image.py <content_path> [--error "message"]
"""

import sys
import os
import json
import argparse
import requests
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from inky.auto import auto

CONFIG_FILE = Path("/etc/photoframe/config.json")
ARENA_API = "https://api.are.na/v2"

# Layout settings
TITLE_GAP_PX = 16
TITLE_SIDE_PADDING = 24
TXT_PADDING = 10
FILL_GAP_PX = 50
MIN_BOX_HEIGHT = 480
CHANNEL_INFO_PADDING = 5
CHANNEL_INFO_BOTTOM_PADDING = 16
CHANNEL_INFO_LINE_SPACING = 4

# Font sizes
CAPTION_SIZE = 20
CHANNEL_INFO_SIZE = 24
TEXT_SIZE = 18
ERROR_SIZE = 18

SUPPORTED_IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif")
SUPPORTED_TEXT_EXTS = (".txt",)


def load_config():
    try:
        with open(CONFIG_FILE, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def get_theme_colors(dark_mode):
    if dark_mode:
        return {
            "bg_color": "black",
            "text_color": "#E5E5E5",
            "caption_color": "#B2B2B2",
            "border_color": "#333333",
            "channel_info_color": "#E5E5E5",
            "error_color": "#FF6B6B",
        }
    else:
        return {
            "bg_color": "white",
            "text_color": "#333333",
            "caption_color": "#696969",
            "border_color": "#EDEDED",
            "channel_info_color": "#333333",
            "error_color": "#CC0000",
        }


def get_channel_info(slug, token=None):
    """Fetch channel info from Are.na API to get user and channel display names"""
    try:
        headers = {"User-Agent": "ArenaFrame/1.0"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        
        url = f"{ARENA_API}/channels/{slug}"
        response = requests.get(url, headers=headers, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            user_name = data.get("user", {}).get("full_name") or data.get("user", {}).get("username", "")
            channel_name = data.get("title", slug)
            return user_name, channel_name
    except Exception as e:
        print(f"Error fetching channel info: {e}")
    
    return None, slug


def load_font_regular(size: int):
    """Load regular weight font"""
    font_path = "/home/pi/Areal-Regular.ttf"
    try:
        return ImageFont.truetype(font_path, size)
    except OSError:
        try:
            return ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", size)
        except OSError:
            return ImageFont.load_default()


def load_font_bold(size: int):
    """Load bold weight font"""
    font_path = "/home/pi/Areal-Bold.ttf"
    try:
        return ImageFont.truetype(font_path, size)
    except OSError:
        try:
            return ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", size)
        except OSError:
            return ImageFont.load_default()


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


def fit_center(image: Image.Image, box_w: int, box_h: int) -> Image.Image:
    img = image.copy()
    img.thumbnail((box_w, box_h), Image.LANCZOS)
    return img


def wrap_text_to_width(draw, text, font, max_w, fill_gap_px=50):
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


def calculate_text_height(draw, text, font, box_width, padding):
    """Calculate the height needed to render text"""
    max_w = box_width - 2 * padding
    lines = wrap_text_to_width(draw, text.strip(), font, max_w, fill_gap_px=FILL_GAP_PX)
    ascent, descent = font.getmetrics()
    line_h = ascent + descent + 4
    return len(lines) * line_h + 2 * padding


def render_text_in_box(draw: ImageDraw.ImageDraw, box_xy, box_wh, text: str, font: ImageFont.ImageFont, padding: int, text_color: str):
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


def calculate_image_box_height(img_width, img_height, box_width, min_height, max_height):
    """Calculate optimal box height for an image."""
    if img_width == 0:
        return min_height
    
    aspect_ratio = img_height / img_width
    
    if aspect_ratio <= 1.0:
        return min_height
    
    needed_height = int(box_width * aspect_ratio)
    
    return max(min_height, min(needed_height, max_height))


def build_channel_info_segments(user_name, channel_name, font_bold, font_regular):
    """Build channel info as list of (text, font) tuples"""
    segments = []
    segments.append(("Are.na", font_bold))
    segments.append((" / ", font_regular))
    if user_name:
        segments.append((user_name, font_bold))
        segments.append((" / ", font_regular))
    segments.append((channel_name, font_bold))
    return segments


def get_segments_width(draw, segments):
    """Calculate total width of segments"""
    return sum(text_width(draw, text, font) for text, font in segments)


def draw_segments(draw, segments, x, y, fill):
    """Draw segments at position, returns final x position"""
    for text, font in segments:
        draw.text((x, y), text, font=font, fill=fill)
        x += text_width(draw, text, font)
    return x


def ellipsize_segments(draw, segments, max_w):
    """Ellipsize the last segment if total width exceeds max_w"""
    total_w = get_segments_width(draw, segments)
    if total_w <= max_w:
        return segments
    
    prefix_segments = segments[:-1]
    prefix_w = get_segments_width(draw, prefix_segments)
    
    last_text, last_font = segments[-1]
    available_w = max_w - prefix_w
    
    if available_w <= 0:
        available_w = max_w // 4
    
    ellipsized = ellipsize_to_fit(draw, last_text, last_font, available_w)
    return prefix_segments + [(ellipsized, last_font)]


def wrap_channel_info_segments(draw, segments, max_w, font_bold, font_regular):
    """Wrap channel info to max 2 lines, breaking at ' / ' separators."""
    total_w = get_segments_width(draw, segments)
    
    if total_w <= max_w:
        return [segments]
    
    best_break = None
    best_break_width = 0
    
    for i, (text, font) in enumerate(segments):
        if text == " / ":
            line1 = segments[:i+1]
            line1_w = get_segments_width(draw, line1)
            if line1_w <= max_w and line1_w > best_break_width:
                best_break = i + 1
                best_break_width = line1_w
    
    if best_break is not None:
        line1 = segments[:best_break]
        line2 = segments[best_break:]
        
        line2_w = get_segments_width(draw, line2)
        if line2_w > max_w:
            line2 = ellipsize_segments(draw, line2, max_w)
        
        return [line1, line2]
    
    return [ellipsize_segments(draw, segments, max_w)]


def calculate_channel_info_height(draw, segments, max_w, font_bold, font_regular, line_height, line_spacing):
    """Calculate total height needed for channel info"""
    lines = wrap_channel_info_segments(draw, segments, max_w, font_bold, font_regular)
    num_lines = len(lines)
    return num_lines * line_height + (num_lines - 1) * line_spacing


def draw_channel_info(draw, segments, max_w, x_start, y_start, fill, font_bold, font_regular, line_height, line_spacing):
    """Draw channel info with wrapping and mixed fonts"""
    lines = wrap_channel_info_segments(draw, segments, max_w, font_bold, font_regular)
    
    y = y_start
    for line_segments in lines:
        draw_segments(draw, line_segments, x_start, y, fill)
        y += line_height + line_spacing
    
    return len(lines) * line_height + (len(lines) - 1) * line_spacing


def get_last_displayed_content():
    """Get the path of the last displayed content"""
    content_dir = Path("/home/pi/arena-frame/content")
    if content_dir.exists():
        files = list(content_dir.glob("*"))
        if files:
            return files[0]
    return None


def display_error_only(error_message):
    """Display just an error message on screen with minimal layout"""
    config = load_config()
    dark_mode = config.get("dark_mode", False)
    theme = get_theme_colors(dark_mode)
    
    display = auto()
    final_w, final_h = display.resolution
    
    CANVAS_W = final_h
    CANVAS_H = final_w
    
    canvas = Image.new("RGB", (CANVAS_W, CANVAS_H), theme["bg_color"])
    draw = ImageDraw.Draw(canvas)
    
    error_font = load_font_bold(ERROR_SIZE)
    
    # Center error message
    error_lines = wrap_text_to_width(draw, error_message, error_font, CANVAS_W - 40, fill_gap_px=FILL_GAP_PX)
    line_h = text_height(draw, "Ag", error_font) + 4
    total_h = len(error_lines) * line_h
    
    y = (CANVAS_H - total_h) // 2
    for line in error_lines:
        line_w = text_width(draw, line, error_font)
        x = (CANVAS_W - line_w) // 2
        draw.text((x, y), line, font=error_font, fill=theme["error_color"])
        y += line_h
    
    final_img = canvas.rotate(90, expand=True)
    display.set_image(final_img)
    display.show()
    
    print(f"Displayed error: {error_message}")
    return True


def main(content_path: str = None, error_message: str = None):
    """Load content and display on Inky"""
    
    # If no content but error, try to use last displayed content
    if not content_path and error_message:
        last_content = get_last_displayed_content()
        if last_content:
            content_path = str(last_content)
        else:
            # No previous content, just show error
            return display_error_only(error_message)
    
    if not content_path:
        print("No content to display")
        return False
    
    path = Path(content_path)
    if not path.exists():
        if error_message:
            return display_error_only(error_message)
        print(f"Content not found: {content_path}")
        return False
    
    filename = path.name
    stem = path.stem
    low = filename.lower()

    # Load config and get theme
    config = load_config()
    dark_mode = config.get("dark_mode", False)
    theme = get_theme_colors(dark_mode)
    
    channel_slug = config.get("channel_slug", "")
    arena_token = config.get("arena_token")

    BG_COLOR = theme["bg_color"]
    TEXT_COLOR = theme["text_color"]
    CAPTION_COLOR = theme["caption_color"]
    BORDER_COLOR = theme["border_color"]
    CHANNEL_INFO_COLOR = theme["channel_info_color"]
    ERROR_COLOR = theme["error_color"]

    # Get channel info from API (skip if showing error to avoid more failures)
    if error_message:
        user_name, channel_name = None, channel_slug
    else:
        user_name, channel_name = get_channel_info(channel_slug, arena_token)

    # Create display
    display = auto()
    final_w, final_h = display.resolution

    CANVAS_W = final_h
    CANVAS_H = final_w

    # Load fonts
    title_font = load_font_regular(CAPTION_SIZE)
    text_font = load_font_regular(TEXT_SIZE)
    error_font = load_font_bold(ERROR_SIZE)
    channel_info_font_bold = load_font_bold(CHANNEL_INFO_SIZE)
    channel_info_font_regular = load_font_regular(CHANNEL_INFO_SIZE)
    
    temp_img = Image.new("RGB", (1, 1))
    temp_draw = ImageDraw.Draw(temp_img)
    title_h = text_height(temp_draw, "Ag", title_font)
    error_h = text_height(temp_draw, "Ag", error_font) if error_message else 0
    channel_info_line_h = text_height(temp_draw, "Ag", channel_info_font_bold)
    
    # Build channel info segments
    channel_segments = build_channel_info_segments(user_name, channel_name, channel_info_font_bold, channel_info_font_regular)
    
    max_channel_info_w = CANVAS_W - (CHANNEL_INFO_PADDING * 2)
    channel_info_total_h = calculate_channel_info_height(
        temp_draw, channel_segments, max_channel_info_w,
        channel_info_font_bold, channel_info_font_regular,
        channel_info_line_h, CHANNEL_INFO_LINE_SPACING
    )
    
    # Reserve space for bottom elements
    BOTTOM_RESERVED = CHANNEL_INFO_BOTTOM_PADDING + channel_info_total_h + CHANNEL_INFO_PADDING
    if error_message:
        BOTTOM_RESERVED += error_h + 8  # Extra space for error
    
    MAX_BOX_HEIGHT = CANVAS_H - TITLE_GAP_PX - title_h - BOTTOM_RESERVED

    TOP_BOX_W = CANVAS_W

    # Determine content box height
    if low.endswith(SUPPORTED_IMAGE_EXTS):
        src = Image.open(path).convert("RGB")
        TOP_BOX_H = calculate_image_box_height(
            src.width, src.height,
            TOP_BOX_W, MIN_BOX_HEIGHT, MAX_BOX_HEIGHT
        )
    elif low.endswith(SUPPORTED_TEXT_EXTS):
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
        needed_height = calculate_text_height(temp_draw, content, text_font, TOP_BOX_W, TXT_PADDING)
        TOP_BOX_H = max(MIN_BOX_HEIGHT, min(needed_height, MAX_BOX_HEIGHT))
    else:
        TOP_BOX_H = MIN_BOX_HEIGHT

    TITLE_Y = TOP_BOX_H + TITLE_GAP_PX

    canvas = Image.new("RGB", (CANVAS_W, CANVAS_H), BG_COLOR)
    draw = ImageDraw.Draw(canvas)

    # --- CONTENT AREA ---
    if low.endswith(SUPPORTED_IMAGE_EXTS):
        fitted = fit_center(src, TOP_BOX_W, TOP_BOX_H)
        img_x = (TOP_BOX_W - fitted.width) // 2
        img_y = (TOP_BOX_H - fitted.height) // 2
        canvas.paste(fitted, (img_x, img_y))

    elif low.endswith(SUPPORTED_TEXT_EXTS):
        draw.rectangle([0, 0, TOP_BOX_W - 1, TOP_BOX_H - 1], outline=BORDER_COLOR, width=1)
        render_text_in_box(draw, (0, 0), (TOP_BOX_W, TOP_BOX_H), content, text_font, TXT_PADDING, TEXT_COLOR)

    # --- TITLE (centered) ---
    max_title_w = CANVAS_W - (TITLE_SIDE_PADDING * 2)
    title = ellipsize_to_fit(draw, stem, title_font, max_title_w)
    bbox = draw.textbbox((0, 0), title, font=title_font)
    title_w = bbox[2] - bbox[0]
    x = (CANVAS_W - title_w) // 2
    draw.text((x, TITLE_Y), title, font=title_font, fill=CAPTION_COLOR)

    # --- ERROR MESSAGE (below title, if present) ---
    if error_message:
        error_y = TITLE_Y + title_h + 8
        error_text = ellipsize_to_fit(draw, f"⚠ {error_message}", error_font, max_title_w)
        error_w = text_width(draw, error_text, error_font)
        error_x = (CANVAS_W - error_w) // 2
        draw.text((error_x, error_y), error_text, font=error_font, fill=ERROR_COLOR)

    # --- CHANNEL INFO (bottom left) ---
    if config.get("show_info", True):
        channel_info_y = CANVAS_H - CHANNEL_INFO_BOTTOM_PADDING - channel_info_total_h
        draw_channel_info(
            draw, channel_segments, max_channel_info_w,
            CHANNEL_INFO_PADDING, channel_info_y,
            CHANNEL_INFO_COLOR,
            channel_info_font_bold, channel_info_font_regular,
            channel_info_line_h, CHANNEL_INFO_LINE_SPACING
        )
    # Rotate 90° CCW
    final_img = canvas.rotate(90, expand=True)

    display.set_image(final_img)
    display.show()

    if error_message:
        print(f"Displayed with error: {error_message}")
    else:
        print(f"Displayed: {content_path}")
    return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Display content on Inky Impression")
    parser.add_argument("content_path", nargs="?", help="Path to content file")
    parser.add_argument("--error", "-e", help="Error message to display")
    
    args = parser.parse_args()
    
    if not args.content_path and not args.error:
        print("Usage: display_image.py <content_path> [--error 'message']")
        print("       display_image.py --error 'message'")
        sys.exit(1)
    
    success = main(args.content_path, args.error)
    sys.exit(0 if success else 1)
