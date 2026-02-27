"""Image compositing, overlays, and display output.

Handles layout of content (image or text), title, channel info overlay,
and error messages on the e-ink canvas.
"""

import sys
import argparse
from pathlib import Path
from PIL import Image, ImageDraw

from config import CONTENT_DIR, load_config
from sources.arena import get_channel_info
from display.eink import EinkDisplay
from display.text import (
    load_font_regular, load_font_bold,
    text_width, text_height, ellipsize_to_fit,
    wrap_text_to_width, calculate_text_height, render_text_in_box,
    FILL_GAP_PX,
)

# Base layout values (designed for 7.3" display: 480px canvas width)
# All get scaled proportionally to actual display size at runtime.
_REF_WIDTH = 480

_BASE_TITLE_GAP = 16
_BASE_TITLE_SIDE_PADDING = 24
_BASE_TXT_PADDING = 10
_BASE_CHANNEL_INFO_PADDING = 5
_BASE_CHANNEL_INFO_BOTTOM_PADDING = 16
_BASE_CHANNEL_INFO_LINE_SPACING = 4
_BASE_ERROR_MARGIN = 40

_BASE_CAPTION_SIZE = 20
_BASE_CHANNEL_INFO_SIZE = 24
_BASE_TEXT_SIZE = 18
_BASE_ERROR_SIZE = 18

# Min content box expressed as fraction of canvas height
_MIN_BOX_HEIGHT_RATIO = 0.6

SUPPORTED_IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif")
SUPPORTED_TEXT_EXTS = (".txt",)


def _compute_layout(canvas_w, canvas_h):
    """Compute all layout values scaled to the actual display size."""
    scale = canvas_w / _REF_WIDTH

    return {
        "title_gap": round(_BASE_TITLE_GAP * scale),
        "title_side_padding": round(_BASE_TITLE_SIDE_PADDING * scale),
        "txt_padding": round(_BASE_TXT_PADDING * scale),
        "min_box_height": round(canvas_h * _MIN_BOX_HEIGHT_RATIO),
        "channel_info_padding": round(_BASE_CHANNEL_INFO_PADDING * scale),
        "channel_info_bottom_padding": round(_BASE_CHANNEL_INFO_BOTTOM_PADDING * scale),
        "channel_info_line_spacing": round(_BASE_CHANNEL_INFO_LINE_SPACING * scale),
        "error_margin": round(_BASE_ERROR_MARGIN * scale),
        "caption_size": round(_BASE_CAPTION_SIZE * scale),
        "channel_info_size": round(_BASE_CHANNEL_INFO_SIZE * scale),
        "text_size": round(_BASE_TEXT_SIZE * scale),
        "error_size": round(_BASE_ERROR_SIZE * scale),
    }


# ---------------------------------------------------------------------------
# Theme
# ---------------------------------------------------------------------------

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
    return {
        "bg_color": "white",
        "text_color": "#333333",
        "caption_color": "#696969",
        "border_color": "#EDEDED",
        "channel_info_color": "#333333",
        "error_color": "#CC0000",
    }


# ---------------------------------------------------------------------------
# Image helpers
# ---------------------------------------------------------------------------

def fit_center(image: Image.Image, box_w: int, box_h: int) -> Image.Image:
    img = image.copy()
    img.thumbnail((box_w, box_h), Image.LANCZOS)
    return img


def calculate_image_box_height(img_width, img_height, box_width, min_height, max_height):
    if img_width == 0:
        return min_height
    aspect_ratio = img_height / img_width
    if aspect_ratio <= 1.0:
        return min_height
    needed_height = int(box_width * aspect_ratio)
    return max(min_height, min(needed_height, max_height))


# ---------------------------------------------------------------------------
# Channel info overlay (mixed bold/regular with wrapping)
# ---------------------------------------------------------------------------

def build_channel_info_segments(user_name, channel_name, font_bold, font_regular):
    segments = [("Are.na", font_bold), (" / ", font_regular)]
    if user_name:
        segments += [(user_name, font_bold), (" / ", font_regular)]
    segments.append((channel_name, font_bold))
    return segments


def get_segments_width(draw, segments):
    return sum(text_width(draw, text, font) for text, font in segments)


def draw_segments(draw, segments, x, y, fill):
    for text, font in segments:
        draw.text((x, y), text, font=font, fill=fill)
        x += text_width(draw, text, font)
    return x


def ellipsize_segments(draw, segments, max_w):
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
    for i, (text, _font) in enumerate(segments):
        if text == " / ":
            line1 = segments[: i + 1]
            line1_w = get_segments_width(draw, line1)
            if line1_w <= max_w and line1_w > best_break_width:
                best_break = i + 1
                best_break_width = line1_w

    if best_break is not None:
        line1 = segments[:best_break]
        line2 = segments[best_break:]
        if get_segments_width(draw, line2) > max_w:
            line2 = ellipsize_segments(draw, line2, max_w)
        return [line1, line2]

    return [ellipsize_segments(draw, segments, max_w)]


def calculate_channel_info_height(draw, segments, max_w, font_bold, font_regular, line_height, line_spacing):
    lines = wrap_channel_info_segments(draw, segments, max_w, font_bold, font_regular)
    num_lines = len(lines)
    return num_lines * line_height + (num_lines - 1) * line_spacing


def draw_channel_info(draw, segments, max_w, x_start, y_start, fill, font_bold, font_regular, line_height, line_spacing):
    lines = wrap_channel_info_segments(draw, segments, max_w, font_bold, font_regular)
    y = y_start
    for line_segments in lines:
        draw_segments(draw, line_segments, x_start, y, fill)
        y += line_height + line_spacing
    return len(lines) * line_height + (len(lines) - 1) * line_spacing


# ---------------------------------------------------------------------------
# Display functions
# ---------------------------------------------------------------------------

def get_last_displayed_content():
    if CONTENT_DIR.exists():
        files = list(CONTENT_DIR.glob("*"))
        if files:
            return files[0]
    return None


def display_error_only(error_message):
    """Display just an error message centered on screen."""
    config = load_config()
    theme = get_theme_colors(config.get("dark_mode", False))

    eink = EinkDisplay()
    canvas_w, canvas_h = eink.canvas_size
    layout = _compute_layout(canvas_w, canvas_h)

    canvas = Image.new("RGB", (canvas_w, canvas_h), theme["bg_color"])
    draw = ImageDraw.Draw(canvas)

    error_font = load_font_bold(layout["error_size"])
    max_text_w = canvas_w - layout["error_margin"] * 2
    error_lines = wrap_text_to_width(draw, error_message, error_font, max_text_w, fill_gap_px=FILL_GAP_PX)
    line_h = text_height(draw, "Ag", error_font) + 4
    total_h = len(error_lines) * line_h

    y = (canvas_h - total_h) // 2
    for line in error_lines:
        line_w = text_width(draw, line, error_font)
        x = (canvas_w - line_w) // 2
        draw.text((x, y), line, font=error_font, fill=theme["error_color"])
        y += line_h

    eink.show(canvas)
    print(f"Displayed error: {error_message}")
    return True


def display_content(content_path=None, error_message=None):
    """Render content (image or text) with overlays and push to e-ink.

    Returns True on success, False on failure.
    """
    if not content_path and error_message:
        last_content = get_last_displayed_content()
        if last_content:
            content_path = str(last_content)
        else:
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

    if error_message:
        user_name, channel_name = None, channel_slug
    else:
        user_name, channel_name = get_channel_info(channel_slug, arena_token)

    eink = EinkDisplay()
    CANVAS_W, CANVAS_H = eink.canvas_size
    L = _compute_layout(CANVAS_W, CANVAS_H)

    title_font = load_font_regular(L["caption_size"])
    text_font = load_font_regular(L["text_size"])
    error_font = load_font_bold(L["error_size"])
    channel_info_font_bold = load_font_bold(L["channel_info_size"])
    channel_info_font_regular = load_font_regular(L["channel_info_size"])

    temp_img = Image.new("RGB", (1, 1))
    temp_draw = ImageDraw.Draw(temp_img)
    title_h = text_height(temp_draw, "Ag", title_font)
    error_h = text_height(temp_draw, "Ag", error_font) if error_message else 0
    channel_info_line_h = text_height(temp_draw, "Ag", channel_info_font_bold)

    channel_segments = build_channel_info_segments(
        user_name, channel_name, channel_info_font_bold, channel_info_font_regular
    )
    max_channel_info_w = CANVAS_W - (L["channel_info_padding"] * 2)
    channel_info_total_h = calculate_channel_info_height(
        temp_draw, channel_segments, max_channel_info_w,
        channel_info_font_bold, channel_info_font_regular,
        channel_info_line_h, L["channel_info_line_spacing"],
    )

    bottom_reserved = L["channel_info_bottom_padding"] + channel_info_total_h + L["channel_info_padding"]
    if error_message:
        bottom_reserved += error_h + round(8 * CANVAS_W / _REF_WIDTH)

    max_box_height = CANVAS_H - L["title_gap"] - title_h - bottom_reserved
    top_box_w = CANVAS_W

    # Determine content box height
    if low.endswith(SUPPORTED_IMAGE_EXTS):
        src = Image.open(path).convert("RGB")
        top_box_h = calculate_image_box_height(
            src.width, src.height, top_box_w, L["min_box_height"], max_box_height
        )
    elif low.endswith(SUPPORTED_TEXT_EXTS):
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
        needed_height = calculate_text_height(temp_draw, content, text_font, top_box_w, L["txt_padding"])
        top_box_h = max(L["min_box_height"], min(needed_height, max_box_height))
    else:
        top_box_h = L["min_box_height"]

    title_y = top_box_h + L["title_gap"]

    canvas = Image.new("RGB", (CANVAS_W, CANVAS_H), BG_COLOR)
    draw = ImageDraw.Draw(canvas)

    # --- Content area ---
    if low.endswith(SUPPORTED_IMAGE_EXTS):
        fitted = fit_center(src, top_box_w, top_box_h)
        img_x = (top_box_w - fitted.width) // 2
        img_y = (top_box_h - fitted.height) // 2
        canvas.paste(fitted, (img_x, img_y))
    elif low.endswith(SUPPORTED_TEXT_EXTS):
        draw.rectangle([0, 0, top_box_w - 1, top_box_h - 1], outline=BORDER_COLOR, width=1)
        render_text_in_box(draw, (0, 0), (top_box_w, top_box_h), content, text_font, L["txt_padding"], TEXT_COLOR)

    # --- Title (centered) ---
    max_title_w = CANVAS_W - (L["title_side_padding"] * 2)
    title = ellipsize_to_fit(draw, stem, title_font, max_title_w)
    bbox = draw.textbbox((0, 0), title, font=title_font)
    title_w = bbox[2] - bbox[0]
    x = (CANVAS_W - title_w) // 2
    draw.text((x, title_y), title, font=title_font, fill=CAPTION_COLOR)

    # --- Error message (below title) ---
    if error_message:
        error_gap = round(8 * CANVAS_W / _REF_WIDTH)
        error_y = title_y + title_h + error_gap
        error_text = ellipsize_to_fit(draw, f"⚠ {error_message}", error_font, max_title_w)
        error_w = text_width(draw, error_text, error_font)
        error_x = (CANVAS_W - error_w) // 2
        draw.text((error_x, error_y), error_text, font=error_font, fill=ERROR_COLOR)

    # --- Channel info (bottom left) ---
    if config.get("show_info", True):
        channel_info_y = CANVAS_H - L["channel_info_bottom_padding"] - channel_info_total_h
        draw_channel_info(
            draw, channel_segments, max_channel_info_w,
            L["channel_info_padding"], channel_info_y,
            CHANNEL_INFO_COLOR,
            channel_info_font_bold, channel_info_font_regular,
            channel_info_line_h, L["channel_info_line_spacing"],
        )

    eink.show(canvas)

    if error_message:
        print(f"Displayed with error: {error_message}")
    else:
        print(f"Displayed: {content_path}")
    return True


# ---------------------------------------------------------------------------
# CLI entry point (for manual testing)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Display content on Inky Impression")
    parser.add_argument("content_path", nargs="?", help="Path to content file")
    parser.add_argument("--error", "-e", help="Error message to display")

    args = parser.parse_args()

    if not args.content_path and not args.error:
        print("Usage: python -m display.renderer <content_path> [--error 'message']")
        print("       python -m display.renderer --error 'message'")
        sys.exit(1)

    success = display_content(args.content_path, args.error)
    sys.exit(0 if success else 1)
