"""
Are.na content source — fetches blocks from channels and downloads content.

Uses Are.na API v3. Key v3 behaviors:
- Paginated responses return { "data": [...], "meta": { ... } }
- Channel contents default to sort=position_desc (newest first on page 1)
- sort=position_asc gives oldest first (needed for cycle mode full fetch)
- Max 100 items per page

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

SUPPORTED_TYPES = {"Image", "Text", "Link", "Attachment", "Embed", "Media", "File"}
MAX_RETRIES = 5
RETRY_DELAY = 10
CACHE_REFRESH_HOURS = 1
PER_PAGE = 100


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

            if response.status_code == 429:
                reset = response.headers.get("X-RateLimit-Reset")
                if reset:
                    wait = max(1, int(float(reset)) - int(time.time()))
                else:
                    wait = RETRY_DELAY
                print(f"Rate limited, waiting {wait}s (attempt {attempt + 1}/{MAX_RETRIES})")
                time.sleep(wait)
                continue

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


def _handle_api_error(response):
    """Map HTTP status to error code. Returns None if status is 200."""
    if response is None:
        return ERROR_NETWORK
    if response.status_code == 401:
        return ERROR_UNAUTHORIZED
    if response.status_code in (403, 404):
        return ERROR_CHANNEL_NOT_FOUND
    if response.status_code in (502, 503, 504):
        return ERROR_SERVER
    if response.status_code != 200:
        return ERROR_NETWORK
    return None


def _parse_list_response(data):
    """Parse v3 paginated list response. Returns (items, meta)."""
    if "data" in data:
        return data["data"], data.get("meta", {})
    if "contents" in data:
        return data["contents"], data
    return [], {}


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
    img_obj = block.get("image") or {}

    if not isinstance(img_obj, dict):
        return None

    # v3: image.src is the original URL
    if img_obj.get("src"):
        return img_obj["src"]

    # v3: sized variants have src field (prefer large > medium > small > square)
    for size in ("large", "medium", "small", "square"):
        variant = img_obj.get(size)
        if isinstance(variant, dict) and variant.get("src"):
            return variant["src"]

    # v2 fallback: image.original.url, image.display.url, etc.
    for key in ("original", "display", "large", "thumb"):
        v = img_obj.get(key)
        if isinstance(v, dict) and v.get("url"):
            return v["url"]

    # Check attachment/file sub-objects (v2 style)
    for subkey in ("attachment", "file"):
        sub = block.get(subkey) or {}
        if isinstance(sub, dict):
            sub_img = sub.get("image") or {}
            if isinstance(sub_img, dict):
                if sub_img.get("src"):
                    return sub_img["src"]
                for key in ("large", "medium", "small", "original", "display", "thumb"):
                    v = sub_img.get(key)
                    if isinstance(v, dict):
                        if v.get("src"):
                            return v["src"]
                        if v.get("url"):
                            return v["url"]

    return None


def parse_block(block: dict) -> dict | None:
    """Parse API block response into our block format."""
    bclass = block.get("type") or block.get("class", "")
    if bclass not in SUPPORTED_TYPES:
        return None

    # v3: position lives inside block.connection.position
    connection = block.get("connection") or {}
    position = connection.get("position", block.get("position", 0))

    block_info = {
        "id": block["id"],
        "class": bclass,
        "name": block_display_name(block),
        "position": position,
    }

    if bclass == "Text":
        # v3: content is { "markdown": "...", "html": "...", "plain": "..." }
        content = block.get("content", "")
        if isinstance(content, dict):
            content = content.get("plain") or content.get("markdown") or ""
        block_info["content"] = content
    else:
        block_info["image_url"] = best_image_url(block)

    return block_info


# ---------------------------------------------------------------------------
# API calls
# ---------------------------------------------------------------------------

def fetch_channel_blocks(slug, token=None):
    """Fetch all blocks from channel (paginated, oldest first).

    Uses sort=position_asc so index 0 = oldest, last = newest.
    Returns (blocks, error_code).
    """
    blocks = []
    page = 1
    headers = get_headers(token)

    while True:
        url = f"{ARENA_API}/channels/{slug}/contents"
        params = {"page": page, "per": PER_PAGE, "sort": "position_asc"}
        response = request_with_retry("GET", url, params=params, headers=headers)

        error = _handle_api_error(response)
        if error:
            if error == ERROR_UNAUTHORIZED:
                print("Error: Unauthorized - check your access token")
            elif error == ERROR_CHANNEL_NOT_FOUND:
                print(f"Error: Channel '{slug}' not found - check spelling")
            elif error == ERROR_SERVER:
                print(f"Are.na servers temporarily unavailable")
            else:
                print(f"Error fetching channel: {response.status_code if response else 'no response'}")
            return None, error

        data = response.json()
        items, meta = _parse_list_response(data)

        for block in items:
            parsed = parse_block(block)
            if parsed:
                blocks.append(parsed)

        has_more = meta.get("has_more_pages", False)
        if not has_more and len(items) < PER_PAGE:
            break
        if not has_more:
            break

        time.sleep(0.5)
        page += 1

    print(f"Fetched {len(blocks)} blocks (oldest at index 0, newest at end)")
    return blocks, ERROR_NONE


def fetch_newest_blocks(slug, token=None, per_page=PER_PAGE):
    """Fetch the newest blocks from a channel (single API call).

    Uses v3 default sort (position_desc) so page 1 has the newest blocks.
    Returns (blocks, meta, error_code). Blocks are newest-first.
    """
    headers = get_headers(token)
    url = f"{ARENA_API}/channels/{slug}/contents"
    params = {"page": 1, "per": per_page, "sort": "position_desc"}

    response = request_with_retry("GET", url, params=params, headers=headers)

    error = _handle_api_error(response)
    if error:
        return None, {}, error

    data = response.json()
    items, meta = _parse_list_response(data)
    blocks = [p for b in items if (p := parse_block(b))]

    print(f"Fetched {len(blocks)} newest blocks (total: {meta.get('total_count', '?')})")
    return blocks, meta, ERROR_NONE


def get_channel_info(slug, token=None):
    """Fetch owner and channel display names from Are.na API."""
    try:
        headers = get_headers(token)
        url = f"{ARENA_API}/channels/{slug}"
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            data = response.json()
            # v3: owner.name; v2 fallback: user.full_name / user.username
            owner = data.get("owner") or data.get("user") or {}
            user_name = (
                owner.get("name")
                or owner.get("full_name")
                or owner.get("username", "")
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
    """Watch for new blocks added to a channel.

    Uses sort=position_desc so page 1 always has the newest blocks.
    Only needs a single API call per check.
    """
    print("Mode: Live")

    if not state.get("initialized"):
        blocks, meta, error = fetch_newest_blocks(slug, token)
        if error != ERROR_NONE:
            write_error(error, f"Channel: {slug}")
            return None, error
        if not blocks:
            print("No blocks in channel")
            write_error(ERROR_CHANNEL_NOT_FOUND, "No blocks in channel")
            return None, ERROR_CHANNEL_NOT_FOUND

        print(f"Initializing live mode with {len(blocks)} blocks")
        state["known_ids"] = [b["id"] for b in blocks]
        state["initialized"] = True

        newest_block = blocks[0]
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

    blocks, meta, error = fetch_newest_blocks(slug, token)
    if error != ERROR_NONE:
        write_error(error, f"Channel: {slug}")
        return None, error
    if not blocks:
        print("No blocks returned")
        clear_error()
        return None, ERROR_NONE

    known_ids = set(state.get("known_ids", []))
    new_blocks = [b for b in blocks if b["id"] not in known_ids]

    if not new_blocks:
        total = meta.get("total_count", len(blocks))
        print(f"No new blocks ({total} total, {len(known_ids)} known)")
        clear_error()
        return None, ERROR_NONE

    newest_new = new_blocks[0]
    print(f"New block found: {newest_new['name']} (ID: {newest_new['id']}, pos: {newest_new.get('position')})")

    content_path = download_block(newest_new, token)
    if content_path:
        state["known_ids"] = list(known_ids | set(b["id"] for b in new_blocks))
        state["current_block_id"] = newest_new["id"]
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
