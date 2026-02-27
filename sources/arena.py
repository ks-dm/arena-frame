"""
Are.na content source — fetches blocks from channels and downloads content.

Are.na API returns blocks in "position" order:
- position 1 (index 0) = OLDEST (first added to channel)
- higher positions = NEWER (more recently added)

Modes:
- Live: Shows newest block on init, then watches for new additions
- Cycle: Cycles through all blocks in specified order (newest/oldest/random)
"""

import os
import re
import random
import time
import requests
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urlparse

from config import (
    ARENA_API, CONTENT_DIR, STATE_FILE,
    load_config, save_json, load_state,
    get_fresh_state, write_error, clear_error,
    ERROR_NONE, ERROR_NETWORK, ERROR_CHANNEL_NOT_FOUND,
    ERROR_UNAUTHORIZED, ERROR_SERVER,
)
from sources import ContentSource

SUPPORTED_TYPES = {"Image", "Text", "Link", "Attachment", "Media", "File"}
MAX_RETRIES = 5
RETRY_DELAY = 10
CACHE_REFRESH_HOURS = 1


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

def get_headers(token=None):
    headers = {"User-Agent": "ArenaFrame/1.0"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def request_with_retry(method, url, **kwargs):
    for attempt in range(MAX_RETRIES):
        try:
            response = requests.request(method, url, timeout=120, **kwargs)
            if response.status_code >= 500:
                print(f"Server error {response.status_code} (attempt {attempt + 1}/{MAX_RETRIES})")
                if attempt < MAX_RETRIES - 1:
                    print(f"Retrying in {RETRY_DELAY}s...")
                    time.sleep(RETRY_DELAY)
                    continue
            return response
        except (
            requests.exceptions.ConnectionError,
            requests.exceptions.Timeout,
            requests.exceptions.RequestException,
        ) as e:
            print(f"Request failed (attempt {attempt + 1}/{MAX_RETRIES}): {e}")
            if attempt < MAX_RETRIES - 1:
                print(f"Retrying in {RETRY_DELAY}s...")
                time.sleep(RETRY_DELAY)
            else:
                print("Max retries exceeded")
                return None
    return None


# ---------------------------------------------------------------------------
# Block parsing helpers
# ---------------------------------------------------------------------------

def sanitize_name(name: str) -> str:
    name = (name or "").strip()
    name = re.sub(r"\s+", " ", name)
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name)
    name = name.strip(" ._")
    return name[:120] if name else ""


def ext_from_url(url: str, default=".jpg") -> str:
    path = urlparse(url).path
    base = os.path.basename(path)
    _, ext = os.path.splitext(base)
    ext = ext.lower()
    if ext in {".jpg", ".jpeg", ".png", ".gif", ".webp"}:
        return ext
    return default


def block_display_name(block: dict) -> str:
    name = block.get("title") or block.get("generated_title")
    name = sanitize_name(name)
    if not name:
        name = f"block_{block.get('id', 'unknown')}"
    return name


def best_image_url(block: dict) -> str | None:
    bclass = block.get("class")
    img_obj = block.get("image") or {}

    if bclass == "Image" and isinstance(img_obj, dict):
        original = img_obj.get("original")
        if isinstance(original, dict) and original.get("url"):
            return original["url"]

    if isinstance(img_obj, dict):
        for key in ("display", "thumb", "large", "original"):
            v = img_obj.get(key)
            if isinstance(v, dict) and v.get("url"):
                return v["url"]

    for subkey in ("attachment", "file"):
        sub = block.get(subkey) or {}
        if isinstance(sub, dict):
            img = sub.get("image") or {}
            if isinstance(img, dict):
                for key in ("display", "thumb", "large", "original"):
                    v = img.get(key)
                    if isinstance(v, dict) and v.get("url"):
                        return v["url"]

    return None


def parse_block(block: dict) -> dict | None:
    """Parse API block response into our block format."""
    bclass = block.get("class")
    if bclass not in SUPPORTED_TYPES:
        return None

    block_info = {
        "id": block["id"],
        "class": bclass,
        "name": block_display_name(block),
        "position": block.get("position", 0),
    }

    if bclass == "Text":
        block_info["content"] = block.get("content", "")
    else:
        block_info["image_url"] = best_image_url(block)

    return block_info


# ---------------------------------------------------------------------------
# API calls
# ---------------------------------------------------------------------------

def fetch_channel_blocks(slug, token=None):
    """Fetch all blocks from channel (paginated).

    Returns blocks in position order (index 0 = oldest, last = newest).
    Returns (blocks, error_code).
    """
    blocks = []
    page = 1
    per_page = 20
    headers = get_headers(token)

    while True:
        url = f"{ARENA_API}/channels/{slug}/contents"
        params = {"page": page, "per": per_page}
        response = request_with_retry("GET", url, params=params, headers=headers)

        if response is None:
            print("Failed to connect to Are.na")
            return None, ERROR_NETWORK

        if response.status_code == 401:
            print("Error: Unauthorized - check your access token")
            return None, ERROR_UNAUTHORIZED
        if response.status_code == 404:
            print(f"Error: Channel '{slug}' not found - check spelling")
            return None, ERROR_CHANNEL_NOT_FOUND
        if response.status_code in (502, 503, 504):
            print(f"Are.na servers temporarily unavailable ({response.status_code})")
            return None, ERROR_SERVER
        if response.status_code != 200:
            print(f"Error fetching channel: {response.status_code}")
            return None, ERROR_NETWORK

        data = response.json()
        contents = data.get("contents", [])
        for block in contents:
            parsed = parse_block(block)
            if parsed:
                blocks.append(parsed)

        if len(contents) < per_page:
            break
        time.sleep(1)
        page += 1

    print(f"Fetched {len(blocks)} blocks (oldest at index 0, newest at end)")
    return blocks, ERROR_NONE


def _handle_api_error(response):
    """Map HTTP status to error code. Returns None if status is 200."""
    if response is None:
        return ERROR_NETWORK
    if response.status_code == 401:
        return ERROR_UNAUTHORIZED
    if response.status_code == 404:
        return ERROR_CHANNEL_NOT_FOUND
    if response.status_code in (502, 503, 504):
        return ERROR_SERVER
    if response.status_code != 200:
        return ERROR_NETWORK
    return None


def fetch_newest_blocks(slug, token=None, per_page=50):
    """Fetch the newest blocks from a channel.

    The API paginates oldest-first, so this fetches page 1 to discover
    the total size, then fetches the last page to get the newest blocks.
    One API call for small channels, two for large ones.
    Returns (blocks, error_code).
    """
    headers = get_headers(token)
    url = f"{ARENA_API}/channels/{slug}/contents"

    params = {"page": 1, "per": per_page}
    response = request_with_retry("GET", url, params=params, headers=headers)

    error = _handle_api_error(response)
    if error:
        return None, error

    data = response.json()
    contents = data.get("contents", [])

    if len(contents) < per_page:
        blocks = [p for b in contents if (p := parse_block(b))]
        print(f"Fetched {len(blocks)} blocks (single page)")
        return blocks, ERROR_NONE

    length = data.get("length", 0)
    if length <= per_page:
        blocks = [p for b in contents if (p := parse_block(b))]
        return blocks, ERROR_NONE

    last_page = (length + per_page - 1) // per_page
    print(f"Channel has {length} blocks across {last_page} pages, fetching last page...")

    params = {"page": last_page, "per": per_page}
    response = request_with_retry("GET", url, params=params, headers=headers)

    if response is None or response.status_code != 200:
        blocks = [p for b in contents if (p := parse_block(b))]
        print("Failed to fetch last page, falling back to page 1")
        return blocks, ERROR_NONE

    last_data = response.json()
    blocks = [p for b in last_data.get("contents", []) if (p := parse_block(b))]
    print(f"Fetched {len(blocks)} newest blocks from page {last_page}")
    return blocks, ERROR_NONE


def get_channel_info(slug, token=None):
    """Fetch user and channel display names from Are.na API."""
    try:
        headers = get_headers(token)
        url = f"{ARENA_API}/channels/{slug}"
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            data = response.json()
            user_name = (
                data.get("user", {}).get("full_name")
                or data.get("user", {}).get("username", "")
            )
            channel_name = data.get("title", slug)
            return user_name, channel_name
    except Exception as e:
        print(f"Error fetching channel info: {e}")
    return None, slug


# ---------------------------------------------------------------------------
# Content download
# ---------------------------------------------------------------------------

def clear_content_dir():
    CONTENT_DIR.mkdir(exist_ok=True)
    for old_file in CONTENT_DIR.glob("*"):
        old_file.unlink()


def download_block(block, token=None):
    """Download block content to disk. Returns path or None."""
    clear_content_dir()

    bclass = block.get("class")
    name = block.get("name", f"block_{block['id']}")
    headers = get_headers(token)

    if bclass == "Text":
        content = block.get("content", "")
        out_path = CONTENT_DIR / f"{name}.txt"
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"Text saved: {out_path.name}")
        return out_path

    image_url = block.get("image_url")
    if not image_url:
        print(f"No image URL for block: {name}")
        return None

    ext = ext_from_url(image_url)
    out_path = CONTENT_DIR / f"{name}{ext}"
    response = request_with_retry("GET", image_url, headers=headers)

    if response is None or response.status_code != 200:
        print("Failed to download image")
        return None

    with open(out_path, "wb") as f:
        f.write(response.content)
    print(f"{bclass} saved: {out_path.name}")
    return out_path


# ---------------------------------------------------------------------------
# Mode implementations
# ---------------------------------------------------------------------------

def should_refresh_cache(state):
    last_cache = state.get("last_cache_refresh")
    if not last_cache:
        return True
    try:
        last_time = datetime.fromisoformat(last_cache)
        return datetime.now() - last_time > timedelta(hours=CACHE_REFRESH_HOURS)
    except (ValueError, TypeError):
        return True


def _run_live_mode(slug, token, state):
    """Watch for new blocks. First run shows newest; subsequent runs show new additions.

    Uses fetch_channel_blocks (all pages) every time to reliably detect
    new blocks regardless of channel size or API pagination order.
    """
    print("Mode: Live")

    blocks, error = fetch_channel_blocks(slug, token)
    if error != ERROR_NONE:
        write_error(error, f"Channel: {slug}")
        return None, error
    if not blocks:
        print("No blocks in channel")
        write_error(ERROR_CHANNEL_NOT_FOUND, "No blocks in channel")
        return None, ERROR_CHANNEL_NOT_FOUND

    known_ids = set(state.get("known_ids", []))

    if not state.get("initialized"):
        print(f"Initializing live mode with {len(blocks)} blocks")
        state["known_ids"] = [b["id"] for b in blocks]
        state["initialized"] = True

        newest_block = blocks[-1]
        print(f"Displaying newest: {newest_block['name']} (ID: {newest_block['id']}, pos: {newest_block.get('position')})")

        content_path = download_block(newest_block, token)
        if content_path:
            state["current_block_id"] = newest_block["id"]
            state["last_updated"] = datetime.now().isoformat()
            save_json(STATE_FILE, state)
            clear_error()
            return str(content_path), ERROR_NONE

        save_json(STATE_FILE, state)
        return None, ERROR_NETWORK

    new_blocks = [b for b in blocks if b["id"] not in known_ids]

    if not new_blocks:
        print(f"No new blocks ({len(blocks)} total, {len(known_ids)} known)")
        clear_error()
        return None, ERROR_NONE

    new_block = new_blocks[-1]
    print(f"New block found: {new_block['name']} (ID: {new_block['id']}, pos: {new_block.get('position')})")

    content_path = download_block(new_block, token)
    if content_path:
        state["known_ids"] = list(known_ids | set(b["id"] for b in new_blocks))
        state["current_block_id"] = new_block["id"]
        state["last_updated"] = datetime.now().isoformat()
        save_json(STATE_FILE, state)
        clear_error()
        return str(content_path), ERROR_NONE

    return None, ERROR_NETWORK


def _run_cycle_mode(slug, token, state, order):
    """Cycle through all blocks: newest-first, oldest-first, or random."""
    print(f"Mode: Cycle ({order})")

    if should_refresh_cache(state) or not state.get("cached_blocks"):
        print("Refreshing block cache...")
        blocks, error = fetch_channel_blocks(slug, token)

        if error != ERROR_NONE:
            blocks = state.get("cached_blocks", [])
            if not blocks:
                print(f"No cached blocks, error: {error}")
                write_error(error, f"Channel: {slug}")
                return None, error
            print(f"Using stale cache ({len(blocks)} blocks)")
        else:
            state["cached_blocks"] = blocks
            state["last_cache_refresh"] = datetime.now().isoformat()
            state["displayed_ids"] = []
            state["cycle_index"] = 0
            print(f"Cached {len(blocks)} blocks")
    else:
        blocks = state.get("cached_blocks", [])
        print(f"Using cache ({len(blocks)} blocks)")

    if not blocks:
        print("No blocks in channel")
        write_error(ERROR_CHANNEL_NOT_FOUND, "No blocks in channel")
        return None, ERROR_CHANNEL_NOT_FOUND

    displayed_ids = set(state.get("displayed_ids", []))

    if order == "random":
        available = [b for b in blocks if b["id"] not in displayed_ids]
        if not available:
            print("Cycle complete, resetting")
            state["displayed_ids"] = []
            available = blocks
        next_block = random.choice(available)
    else:
        cycle_index = state.get("cycle_index", 0)
        total_blocks = len(blocks)

        if cycle_index >= total_blocks:
            print("Cycle complete, resetting")
            cycle_index = 0
            state["displayed_ids"] = []

        if order == "newest":
            actual_index = total_blocks - 1 - cycle_index
        else:
            actual_index = cycle_index

        next_block = blocks[actual_index]
        state["cycle_index"] = cycle_index + 1

    print(f"Displaying: {next_block['name']} (ID: {next_block['id']}, pos: {next_block.get('position')})")

    content_path = download_block(next_block, token)
    if content_path:
        state["displayed_ids"] = list(displayed_ids | {next_block["id"]})
        state["current_block_id"] = next_block["id"]
        state["last_updated"] = datetime.now().isoformat()
        save_json(STATE_FILE, state)
        clear_error()
        return str(content_path), ERROR_NONE

    return None, ERROR_NETWORK


# ---------------------------------------------------------------------------
# Source class
# ---------------------------------------------------------------------------

class ArenaSource(ContentSource):
    """Fetches content from an Are.na channel."""

    def fetch(self, state=None):
        config = load_config()
        slug = config.get("channel_slug")
        token = config.get("arena_token")
        refresh = config.get("refresh", "live")
        order = config.get("order", "newest")

        if not slug:
            print("Error: No channel_slug in config")
            write_error(ERROR_CHANNEL_NOT_FOUND, "No channel configured")
            return None, ERROR_CHANNEL_NOT_FOUND

        if token:
            print("Using authenticated API access")

        if state is None:
            state = {}

        if state.get("channel_slug") != slug:
            print(f"Channel changed to '{slug}' - resetting state")
            state.update(get_fresh_state(slug))

        if refresh != "live" and state.get("last_order") != order:
            print(f"Order changed to '{order}' - resetting cycle")
            state["displayed_ids"] = []
            state["cycle_index"] = 0

        state["last_order"] = order
        print(f"Channel: {slug}")

        if refresh == "live":
            return _run_live_mode(slug, token, state)
        else:
            return _run_cycle_mode(slug, token, state, order)
