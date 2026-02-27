#!/usr/bin/env python3
"""WiFi state machine — manages AP mode (setup) and client mode (normal operation).

Replaces the original wifi-manager.sh bash script with equivalent Python logic.
Runs as a systemd service.
"""

import os
import subprocess
import sys
import time

from config import AP_MODE_FLAG, load_config, clear_error
from utils import log
from wifi.utils import WPA_CONF, WIFI_INTERFACE, has_saved_networks

AP_SSID = "ArenaFrame-Setup"
AP_IP = "192.168.4.1"
CONNECTION_TIMEOUT = 30
AP_DWELL_TIME = 120


def run(cmd, timeout=30):
    """Run a shell command, suppressing errors."""
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except (subprocess.TimeoutExpired, subprocess.CalledProcessError, FileNotFoundError):
        return None


def get_country_code():
    config = load_config()
    return config.get("country", "US")


def check_force_ap_mode():
    return AP_MODE_FLAG.exists()


def check_wifi_connected():
    result = run(["wpa_cli", "-i", WIFI_INTERFACE, "status"])
    if result and result.returncode == 0:
        state = ""
        ssid = ""
        for line in result.stdout.split("\n"):
            if line.startswith("wpa_state="):
                state = line.split("=", 1)[1]
            elif line.startswith("ssid="):
                ssid = line.split("=", 1)[1]
        if state == "COMPLETED" and ssid and ssid != AP_SSID:
            return True
    return False


def check_internet():
    result = run(["ping", "-c", "1", "-W", "5", "8.8.8.8"])
    return result is not None and result.returncode == 0


def cleanup():
    log("Cleaning up...")
    for service in ["hostapd", "dnsmasq", "wifi-portal-web"]:
        run(["systemctl", "stop", service])
    for proc in ["hostapd", "wpa_supplicant", "dhclient"]:
        run(["pkill", "-9", proc])
    run(["rm", "-f", "/var/run/wpa_supplicant/wlan0"])
    run(["ip", "addr", "flush", "dev", WIFI_INTERFACE])
    run(["iptables", "-t", "nat", "-F"])


def start_ap_mode():
    log("Starting AP mode...")
    cleanup()
    time.sleep(2)

    run(["ip", "link", "set", WIFI_INTERFACE, "down"])
    time.sleep(1)
    run(["iw", "dev", WIFI_INTERFACE, "set", "type", "__ap"])
    time.sleep(1)
    run(["ip", "link", "set", WIFI_INTERFACE, "up"])
    time.sleep(1)
    run(["ip", "addr", "add", f"{AP_IP}/24", "dev", WIFI_INTERFACE])

    result = run(["systemctl", "start", "hostapd"])
    if result is None or result.returncode != 0:
        log("ERROR: hostapd failed to start")
        return False

    time.sleep(2)

    country = get_country_code()
    run(["sed", "-i", f"s/country_code=.*/country_code={country}/",
         "/etc/hostapd/hostapd.conf"])

    run(["systemctl", "start", "dnsmasq"])

    run(["iptables", "-t", "nat", "-A", "PREROUTING", "-i", WIFI_INTERFACE,
         "-p", "tcp", "--dport", "80", "-j", "DNAT", "--to-destination", f"{AP_IP}:80"])
    run(["iptables", "-t", "nat", "-A", "PREROUTING", "-i", WIFI_INTERFACE,
         "-p", "tcp", "--dport", "443", "-j", "DNAT", "--to-destination", f"{AP_IP}:80"])

    run(["systemctl", "start", "wifi-portal-web"])
    run(["systemctl", "start", "arena-led"])

    log(f"AP mode started. SSID: {AP_SSID}")
    return True


def start_client_mode():
    log("Starting client mode...")
    run(["systemctl", "stop", "arena-led"])

    cleanup()
    time.sleep(2)

    run(["ip", "link", "set", WIFI_INTERFACE, "down"])
    time.sleep(1)
    run(["iw", "dev", WIFI_INTERFACE, "set", "type", "managed"])
    time.sleep(1)
    run(["ip", "link", "set", WIFI_INTERFACE, "up"])
    time.sleep(2)

    run(["wpa_supplicant", "-B", "-i", WIFI_INTERFACE, "-c", WPA_CONF])
    time.sleep(5)

    log("Waiting for WiFi connection...")
    for _ in range(CONNECTION_TIMEOUT):
        if check_wifi_connected():
            log("Connected to WiFi!")
            run(["dhclient", WIFI_INTERFACE])
            time.sleep(2)
            return True
        time.sleep(1)

    log("Failed to connect to WiFi")
    return False


def trigger_reconnect():
    """Clear AP flag and restart wifi-manager (called from portal after saving config)."""
    try:
        if AP_MODE_FLAG.exists():
            AP_MODE_FLAG.unlink()
    except Exception:
        pass
    clear_error()
    run(["systemctl", "restart", "wifi-manager"])
    run(["systemctl", "start", "arena-reconnect"])


def main():
    log("WiFi Manager starting...")
    time.sleep(5)

    while True:
        if check_force_ap_mode():
            log("Force AP mode requested")
            start_ap_mode()
            time.sleep(AP_DWELL_TIME)
            continue

        if check_wifi_connected():
            if check_internet():
                log("Connected with internet access")
                time.sleep(30)
                continue

        log("No connection detected")

        if has_saved_networks():
            log("Trying saved networks...")
            if start_client_mode():
                continue

        log("Starting AP for configuration...")
        start_ap_mode()
        time.sleep(AP_DWELL_TIME)


if __name__ == "__main__":
    try:
        if len(sys.argv) > 1:
            cmd = sys.argv[1]
            if cmd == "start-ap":
                start_ap_mode()
            elif cmd == "start-client":
                start_client_mode()
            elif cmd == "status":
                if check_wifi_connected():
                    result = run(["wpa_cli", "-i", WIFI_INTERFACE, "status"])
                    for line in (result.stdout if result else "").split("\n"):
                        if line.startswith("ssid="):
                            print(f"Connected: {line.split('=', 1)[1]}")
                            break
                else:
                    print("Not connected")
            else:
                main()
        else:
            main()
    except KeyboardInterrupt:
        log("WiFi Manager stopped")
        sys.exit(0)
