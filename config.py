"""Unified configuration and state management for Arena Frame."""

import json
import os
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).parent
CONFIG_FILE = Path("/etc/photoframe/config.json")
STATE_FILE = BASE_DIR / "state.json"
CONTENT_DIR = BASE_DIR / "content"
ERROR_FILE = Path("/tmp/arena-frame-error")
AP_MODE_FLAG = Path("/tmp/force_ap_mode")
FONT_DIR = Path("/home/pi")
LOGO_FILE = Path("/etc/photoframe/arena.svg")

ARENA_API = "https://api.are.na/v2"

CONFIG_DEFAULTS = {
    "channel_slug": "",
    "arena_token": None,
    "refresh": "live",
    "order": "newest",
    "show_info": True,
    "dark_mode": False,
}

ERROR_NONE = "none"
ERROR_NETWORK = "network"
ERROR_CHANNEL_NOT_FOUND = "channel_not_found"
ERROR_UNAUTHORIZED = "unauthorized"
ERROR_SERVER = "server"

REFRESH_INTERVALS = {
    "live": 60,
    "5min": 300,
    "15min": 900,
    "30min": 1800,
    "1hour": 3600,
    "12hour": 43200,
    "24hour": 86400,
}

REFRESH_OPTIONS = [
    ("live", "Live"),
    ("5min", "5 Minutes"),
    ("15min", "15 Minutes"),
    ("30min", "30 Minutes"),
    ("1hour", "1 Hour"),
    ("12hour", "12 Hours"),
    ("24hour", "24 Hours"),
]

ORDER_OPTIONS = [
    ("random", "Random"),
    ("oldest", "Oldest First"),
    ("newest", "Newest First"),
]


def load_json(path, default=None):
    try:
        with open(path, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default if default is not None else {}


def save_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def load_config():
    config = load_json(CONFIG_FILE, CONFIG_DEFAULTS.copy())
    for key, default in CONFIG_DEFAULTS.items():
        config.setdefault(key, default)
    return config


def save_config(config):
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    save_json(CONFIG_FILE, config)


def load_state():
    return load_json(STATE_FILE, {})


def save_state(state):
    save_json(STATE_FILE, state)


def get_fresh_state(slug):
    return {
        "channel_slug": slug,
        "known_ids": [],
        "displayed_ids": [],
        "cycle_index": 0,
        "cached_blocks": [],
        "last_cache_refresh": None,
        "current_block_id": None,
        "last_updated": None,
        "initialized": False,
        "last_order": None,
    }


def write_error(error_type, message=""):
    try:
        with open(ERROR_FILE, "w") as f:
            json.dump(
                {
                    "type": error_type,
                    "message": message,
                    "time": datetime.now().isoformat(),
                },
                f,
            )
    except Exception:
        pass


def clear_error():
    try:
        if ERROR_FILE.exists():
            ERROR_FILE.unlink()
    except Exception:
        pass


def get_error_message():
    try:
        if ERROR_FILE.exists():
            data = load_json(ERROR_FILE)
            error_type = data.get("type", "")
            messages = {
                "channel_not_found": "Channel not found - check spelling",
                "network": "Can't connect to Are.na",
                "unauthorized": "Access denied - check token",
            }
            return messages.get(error_type)
    except Exception:
        pass
    return None
