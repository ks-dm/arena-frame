#!/usr/bin/env python3
"""Arena Frame — E-ink photo frame displaying content from Are.na channels.

Entry point: coordinates fetching content and updating the display on a
configurable interval. Replaces the old subprocess-based scheduler with
direct module imports.
"""

import sys
import time

from config import (
    load_config, load_state, save_state,
    REFRESH_INTERVALS, ERROR_CHANNEL_NOT_FOUND,
    ERROR_UNAUTHORIZED, ERROR_NETWORK, ERROR_SERVER,
)
from sources.arena import ArenaSource
from display.renderer import display_content, display_error_only
from utils import log, trigger_ap_mode, format_duration

RETRY_INTERVAL = 30
MAX_PERSISTENT_ERRORS = 3
MIN_SLEEP = 10


def is_persistent_error(error):
    return error in (ERROR_CHANNEL_NOT_FOUND, ERROR_UNAUTHORIZED, ERROR_NETWORK)


def fetch_and_display(source, state):
    """Fetch new content and push to display. Returns (success, is_persistent_error)."""
    log("Fetching content...")

    content_path, error = source.fetch(state)
    save_state(state)

    if error == ERROR_SERVER:
        log("Temporary server error, will retry")
        return False, False

    if is_persistent_error(error) and content_path is None:
        log(f"Persistent error: {error}")
        return False, True

    if content_path:
        log(f"Displaying: {content_path}")
        success = display_content(content_path)
        if success:
            log("Display updated successfully")
        else:
            log("Display update failed")
        return True, False

    if error and error != "none":
        log(f"Fetch error ({error}) but no content to show")
        return False, True

    log("No new content to display")
    return True, False


def wait_for_config():
    """Block until a channel_slug appears in config, triggering AP mode if needed."""
    config = load_config()
    if config.get("channel_slug"):
        return config

    log("No channel_slug configured - triggering AP mode")
    trigger_ap_mode()

    while True:
        time.sleep(60)
        config = load_config()
        if config.get("channel_slug"):
            log("Configuration found!")
            return config


def main():
    log("Arena Frame starting...")

    config = wait_for_config()

    log(f"Channel: {config.get('channel_slug')}")
    log(f"Refresh: {config.get('refresh', 'live')}, Order: {config.get('order', 'newest')}")

    source = ArenaSource()
    state = load_state()
    persistent_error_count = 0

    # Initial display update with retries
    log("Initial display update...")
    while True:
        success, is_persistent = fetch_and_display(source, state)

        if success:
            log("Initial fetch successful")
            persistent_error_count = 0
            break

        if is_persistent:
            persistent_error_count += 1
            log(f"Persistent error ({persistent_error_count}/{MAX_PERSISTENT_ERRORS})")
            if persistent_error_count >= MAX_PERSISTENT_ERRORS:
                log("Too many persistent errors - entering AP mode")
                trigger_ap_mode()
                config = wait_for_config()
                source = ArenaSource()
                state = load_state()
                persistent_error_count = 0
                continue

        log(f"Retrying in {RETRY_INTERVAL}s...")
        time.sleep(RETRY_INTERVAL)

    # Main loop
    while True:
        config = load_config()
        refresh = config.get("refresh", "live")
        target_sleep = REFRESH_INTERVALS.get(refresh, 60)

        log(f"Sleeping for {format_duration(target_sleep)}")
        time.sleep(target_sleep)

        log("Waking up, updating display...")

        source = ArenaSource()
        success, is_persistent = fetch_and_display(source, state)

        if success:
            persistent_error_count = 0
            continue

        if is_persistent:
            persistent_error_count += 1
            log(f"Persistent error ({persistent_error_count}/{MAX_PERSISTENT_ERRORS})")
            if persistent_error_count >= MAX_PERSISTENT_ERRORS:
                log("Too many persistent errors - entering AP mode")
                trigger_ap_mode()
        else:
            log(f"Temporary error, retrying in {RETRY_INTERVAL}s")
            time.sleep(RETRY_INTERVAL)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log("Arena Frame stopped")
        sys.exit(0)
