#!/usr/bin/env python3
"""
Scheduler daemon - coordinates fetching and displaying images
"""

import json
import subprocess
import time
import sys
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).parent
CONFIG_FILE = Path("/etc/photoframe/config.json")
STATE_FILE = BASE_DIR / "state.json"
FETCH_SCRIPT = BASE_DIR / "fetch_images.py"
DISPLAY_SCRIPT = BASE_DIR / "display_image.py"
VENV_PYTHON = Path.home() / ".virtualenvs/pimoroni/bin/python"
AP_MODE_FLAG = Path("/tmp/force_ap_mode")

MIN_SLEEP = 10
RETRY_INTERVAL = 30
MAX_PERSISTENT_ERRORS = 3

REFRESH_INTERVALS = {
    "live": 60,        # Check every minute for new blocks
    "5min": 300,
    "15min": 900,
    "30min": 1800,
    "1hour": 3600,
    "12hour": 43200,
    "24hour": 86400,
}

def load_json(path, default=None):
    try:
        with open(path, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default or {}

def log(message):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {message}", flush=True)

def trigger_ap_mode():
    log("Triggering AP mode for reconfiguration...")
    try:
        AP_MODE_FLAG.write_text("1")
        subprocess.run(['sudo', 'systemctl', 'restart', 'wifi-manager'], timeout=30)
    except Exception as e:
        log(f"Error triggering AP mode: {e}")

def fetch_and_display():
    log("Fetching content...")
    
    result = subprocess.run(
        ["python3", str(FETCH_SCRIPT)],
        capture_output=True,
        text=True
    )
    
    if result.stdout:
        for line in result.stdout.strip().split('\n'):
            log(f"  fetch: {line}")
    if result.stderr:
        log(f"  fetch error: {result.stderr}")
    
    if result.returncode == 2:
        log("Persistent error detected")
        return False, True
    
    if result.returncode == 1:
        log("Temporary error, will retry")
        return False, False
    
    content_path = None
    for line in (result.stdout or "").split('\n'):
        if line.startswith("OUTPUT:"):
            content_path = line.replace("OUTPUT:", "").strip()
            break
    
    if content_path:
        log(f"Displaying: {content_path}")
        result = subprocess.run(
            [str(VENV_PYTHON), str(DISPLAY_SCRIPT), content_path],
            capture_output=True,
            text=True
        )
        
        if result.stdout:
            for line in result.stdout.strip().split('\n'):
                log(f"  display: {line}")
        if result.stderr:
            log(f"  display error: {result.stderr}")
        
        if result.returncode == 0:
            log("Display updated successfully")
        else:
            log("Display update failed")
        
        return True, False
    
    log("No new content to display")
    return True, False

def get_sleep_duration(config):
    refresh = config.get("refresh", "live")
    return REFRESH_INTERVALS.get(refresh, 60)

def format_duration(seconds):
    seconds = int(seconds)
    if seconds < 60:
        return f"{seconds}s"
    elif seconds < 3600:
        mins = seconds // 60
        return f"{mins}m"
    elif seconds < 86400:
        hours = seconds // 3600
        mins = (seconds % 3600) // 60
        if mins:
            return f"{hours}h {mins}m"
        return f"{hours}h"
    else:
        days = seconds // 86400
        return f"{days}d"

def main():
    log("Arena Frame Scheduler starting...")
    
    config = load_json(CONFIG_FILE)
    if not config.get("channel_slug"):
        log("No channel_slug configured - triggering AP mode")
        trigger_ap_mode()
        while True:
            time.sleep(60)
            config = load_json(CONFIG_FILE)
            if config.get("channel_slug"):
                log("Configuration found!")
                break
    
    refresh = config.get("refresh", "live")
    order = config.get("order", "newest")
    log(f"Channel: {config.get('channel_slug')}")
    log(f"Refresh: {refresh}, Order: {order}")
    
    persistent_error_count = 0
    
    log("Initial display update...")
    while True:
        success, is_persistent = fetch_and_display()
        
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
                while True:
                    time.sleep(60)
                    config = load_json(CONFIG_FILE)
        
        log(f"Retrying in {RETRY_INTERVAL}s...")
        time.sleep(RETRY_INTERVAL)
    
    while True:
        config = load_json(CONFIG_FILE)
        
        target_sleep = get_sleep_duration(config)
        log(f"Sleeping for {format_duration(target_sleep)}")
        
        time.sleep(target_sleep)
        
        log("Waking up, updating display...")
        success, is_persistent = fetch_and_display()
        
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
        log("Scheduler stopped")
        sys.exit(0)
