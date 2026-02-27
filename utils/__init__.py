"""Shared utilities for Arena Frame."""

import subprocess
from datetime import datetime
from pathlib import Path

AP_MODE_FLAG = Path("/tmp/force_ap_mode")


def log(message):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {message}", flush=True)


def trigger_ap_mode():
    """Write AP flag and restart wifi-manager to force setup mode."""
    log("Triggering AP mode for reconfiguration...")
    try:
        AP_MODE_FLAG.write_text("1")
        subprocess.run(["sudo", "systemctl", "restart", "wifi-manager"], timeout=30)
    except Exception as e:
        log(f"Error triggering AP mode: {e}")


def format_duration(seconds):
    seconds = int(seconds)
    if seconds < 60:
        return f"{seconds}s"
    elif seconds < 3600:
        return f"{seconds // 60}m"
    elif seconds < 86400:
        hours = seconds // 3600
        mins = (seconds % 3600) // 60
        return f"{hours}h {mins}m" if mins else f"{hours}h"
    else:
        return f"{seconds // 86400}d"
