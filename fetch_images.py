#!/usr/bin/env python3
"""
Fetches blocks from Are.na channel and tracks display history.

Are.na API returns blocks in "position" order:
- position 1 (index 0) = OLDEST (first added to channel)
- higher positions = NEWER (more recently added)

Modes:
- Live: Shows newest block on init, then watches for new additions
- Cycle: Cycles through all blocks in specified order (newest/oldest/random)
"""

import json
import os
import re
import sys
import time
import random
import requests
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urlparse

BASE_DIR = Path(__file__).parent
CONFIG_FILE = Path("/etc/photoframe/config.json")
STATE_FILE = BASE_DIR / "state.json"
CONTENT_DIR = BASE_DIR / "content"
ERROR_FILE = Path("/tmp/arena-frame-error")
ARENA_API = "https://api.are.na/v2"

SUPPORTED_TYPES = {"Image", "Text", "Link", "Attachment", "Media", "File"}
MAX_RETRIES = 5
RETRY_DELAY = 10
CACHE_REFRESH_HOURS = 1

ERROR_NONE = "none"
ERROR_NETWORK = "network"
ERROR_CHANNEL_NOT_FOUND = "channel_not_found"
ERROR_UNAUTHORIZED = "unauthorized"
ERROR_SERVER = "server"


def write_error(error_type, message=""):
    try:
        with open(ERROR_FILE, 'w') as f:
            json.dump({"type": error_type, "message": message, "time": datetime.now().isoformat()}, f)
    except:
        pass


def clear_error():
    try:
        if ERROR_FILE.exists():
            ERROR_FILE.unlink()
    except:
        pass


def load_json(path, default=None):
    try:
        with open(path, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default or {}


def save_json(path, data):
    with open(path, 'w') as f:
        json.dump(data, f, indent=2)


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
            
        except (requests.exceptions.ConnectionError, 
                requests.exceptions.Timeout,
                requests.exceptions.RequestException) as e:
            print(f"Request failed (attempt {attempt + 1}/{MAX_RETRIES}): {e}")
            if attempt < MAX_RETRIES - 1:
                print(f"Retrying in {RETRY_DELAY}s...")
                time.sleep(RETRY_DELAY)
            else:
                print("Max retries exceeded")
                return None
    return None


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
    """Parse API block response into our block format"""
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


def fetch_channel_blocks(slug, token=None):
    """
    Fetch all blocks from channel.
    Returns blocks in position order:
    - index 0 = position 1 = OLDEST
    - last index = highest position = NEWEST
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


def fetch_latest_blocks(slug, token=None, limit=50):
    """
    Fetch the latest blocks from channel (first page only).
    Returns blocks in position order (index 0 = oldest in this batch).
    Returns (blocks, error_code).
    """
    headers = get_headers(token)
    url = f"{ARENA_API}/channels/{slug}/contents"
    params = {"page": 1, "per": limit}
    
    response = request_with_retry("GET", url, params=params, headers=headers)
    
    if response is None:
        return None, ERROR_NETWORK
    
    if response.status_code == 401:
        return None, ERROR_UNAUTHORIZED
    if response.status_code == 404:
        return None, ERROR_CHANNEL_NOT_FOUND
    if response.status_code in (502, 503, 504):
        return None, ERROR_SERVER
    if response.status_code != 200:
        return None, ERROR_NETWORK
    
    data = response.json()
    blocks = []
    for block in data.get("contents", []):
        parsed = parse_block(block)
        if parsed:
            blocks.append(parsed)
    
    return blocks, ERROR_NONE


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
    
    else:
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
        
        with open(out_path, 'wb') as f:
            f.write(response.content)
        
        print(f"{bclass} saved: {out_path.name}")
        return out_path


def should_refresh_cache(state):
    """Check if block cache should be refreshed"""
    last_cache = state.get("last_cache_refresh")
    if not last_cache:
        return True
    
    try:
        last_time = datetime.fromisoformat(last_cache)
        return datetime.now() - last_time > timedelta(hours=CACHE_REFRESH_HOURS)
    except (ValueError, TypeError):
        return True


def get_fresh_state(slug):
    """Return a fresh state dict for a channel"""
    return {
        "channel_slug": slug,
        "known_ids": [],           # All block IDs we know about (for live mode)
        "displayed_ids": [],       # IDs displayed this cycle (for cycle mode)
        "cycle_index": 0,          # Current position in cycle (for ordered modes)
        "cached_blocks": [],       # Full block data cache
        "last_cache_refresh": None,
        "current_block_id": None,
        "last_updated": None,
        "initialized": False,
        "last_order": None,
    }


def run_live_mode(slug, token, state):
    """
    Live mode: Watch for new blocks added to channel.
    On first run: Display the newest block (last in list), mark all as known.
    On subsequent runs: Display any new blocks not in known_ids.
    """
    print("Mode: Live")
    
    # Fetch latest blocks
    blocks, error = fetch_latest_blocks(slug, token, limit=50)
    
    if error != ERROR_NONE:
        write_error(error, f"Channel: {slug}")
        return None, error
    
    if not blocks:
        print("No blocks in channel")
        write_error(ERROR_CHANNEL_NOT_FOUND, "No blocks in channel")
        return None, ERROR_CHANNEL_NOT_FOUND
    
    current_ids = [b["id"] for b in blocks]
    known_ids = set(state.get("known_ids", []))
    
    # First run - initialize
    if not state.get("initialized"):
        print(f"Initializing live mode with {len(current_ids)} blocks")
        
        # Mark all current blocks as known
        state["known_ids"] = current_ids
        state["initialized"] = True
        
        # Display the NEWEST block (LAST in list, highest position)
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
    
    # Subsequent runs - check for new blocks
    new_blocks = [b for b in blocks if b["id"] not in known_ids]
    
    if not new_blocks:
        print("No new blocks")
        clear_error()
        return None, ERROR_NONE
    
    # Display the newest new block (last in filtered list = highest position)
    new_block = new_blocks[-1]
    print(f"New block found: {new_block['name']} (ID: {new_block['id']}, pos: {new_block.get('position')})")
    
    content_path = download_block(new_block, token)
    if content_path:
        # Add all new blocks to known list
        state["known_ids"] = list(known_ids | set(b["id"] for b in new_blocks))
        state["current_block_id"] = new_block["id"]
        state["last_updated"] = datetime.now().isoformat()
        save_json(STATE_FILE, state)
        clear_error()
        return str(content_path), ERROR_NONE
    
    return None, ERROR_NETWORK


def run_cycle_mode(slug, token, state, order):
    """
    Cycle mode: Cycle through all blocks in the channel.
    
    API returns: index 0 = oldest (position 1), last index = newest
    
    Order options:
    - newest: Start with last index, decrement toward 0
    - oldest: Start with index 0, increment toward end
    - random: Pick randomly, track what's been shown
    """
    print(f"Mode: Cycle ({order})")
    
    # Refresh cache if needed
    if should_refresh_cache(state) or not state.get("cached_blocks"):
        print("Refreshing block cache...")
        blocks, error = fetch_channel_blocks(slug, token)
        
        if error != ERROR_NONE:
            # Try to use existing cache
            blocks = state.get("cached_blocks", [])
            if not blocks:
                print(f"No cached blocks, error: {error}")
                write_error(error, f"Channel: {slug}")
                return None, error
            print(f"Using stale cache ({len(blocks)} blocks)")
        else:
            state["cached_blocks"] = blocks
            state["last_cache_refresh"] = datetime.now().isoformat()
            # Reset cycle when cache refreshes
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
    
    # Select next block based on order
    displayed_ids = set(state.get("displayed_ids", []))
    
    if order == "random":
        # Random: pick from blocks not yet shown this cycle
        available = [b for b in blocks if b["id"] not in displayed_ids]
        
        if not available:
            print("Cycle complete, resetting")
            state["displayed_ids"] = []
            available = blocks
        
        next_block = random.choice(available)
        
    else:
        # Ordered modes use cycle_index
        # blocks[0] = oldest, blocks[-1] = newest
        
        cycle_index = state.get("cycle_index", 0)
        total_blocks = len(blocks)
        
        # Reset if we've gone through all blocks
        if cycle_index >= total_blocks:
            print("Cycle complete, resetting")
            cycle_index = 0
            state["displayed_ids"] = []
        
        if order == "newest":
            # Start from end (newest), work backward
            # cycle_index 0 -> blocks[-1] (newest)
            # cycle_index 1 -> blocks[-2]
            # etc.
            actual_index = total_blocks - 1 - cycle_index
        else:
            # oldest: start from beginning
            # cycle_index 0 -> blocks[0] (oldest)
            # cycle_index 1 -> blocks[1]
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


def main():
    config = load_json(CONFIG_FILE)
    state = load_json(STATE_FILE, {})
    
    slug = config.get("channel_slug")
    if not slug:
        print("Error: No channel_slug in config")
        write_error(ERROR_CHANNEL_NOT_FOUND, "No channel configured")
        return None, ERROR_CHANNEL_NOT_FOUND
    
    token = config.get("arena_token")
    refresh = config.get("refresh", "live")
    order = config.get("order", "newest")
    
    if token:
        print("Using authenticated API access")
    
    # Check if channel changed - reset state
    if state.get("channel_slug") != slug:
        print(f"Channel changed to '{slug}' - resetting state")
        state = get_fresh_state(slug)
    
    # Check if order changed in cycle mode - reset cycle
    if refresh != "live" and state.get("last_order") != order:
        print(f"Order changed to '{order}' - resetting cycle")
        state["displayed_ids"] = []
        state["cycle_index"] = 0
    
    state["last_order"] = order
    
    print(f"Channel: {slug}")
    
    if refresh == "live":
        return run_live_mode(slug, token, state)
    else:
        return run_cycle_mode(slug, token, state, order)


if __name__ == "__main__":
    result, error = main()
    if result:
        print(f"OUTPUT:{result}")
    if error in (ERROR_CHANNEL_NOT_FOUND, ERROR_NETWORK, ERROR_UNAUTHORIZED):
        sys.exit(2)
    elif error == ERROR_SERVER:
        sys.exit(1)
    else:
        sys.exit(0)
