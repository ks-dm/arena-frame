"""WiFi scanning and WPA configuration utilities."""

import os
import re
import subprocess

WPA_CONF = "/etc/wpa_supplicant/wpa_supplicant.conf"
WIFI_INTERFACE = "wlan0"
COUNTRY_CODE = "GB"


def get_current_ssid():
    """Get currently connected or last saved WiFi SSID."""
    try:
        result = subprocess.run(
            ["iwgetid", "-r"], capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except Exception:
        pass

    try:
        if os.path.exists(WPA_CONF):
            with open(WPA_CONF, "r") as f:
                content = f.read()
            matches = re.findall(r'ssid="([^"]+)"', content)
            if matches:
                return matches[-1]
    except Exception:
        pass

    return None


def scan_wifi_networks():
    """Scan for available WiFi networks, sorted by signal strength."""
    networks = []
    try:
        result = subprocess.run(
            ["iwlist", WIFI_INTERFACE, "scan"],
            capture_output=True, text=True, timeout=30,
        )
        current = {}
        for line in result.stdout.split("\n"):
            line = line.strip()
            if "Cell" in line and "Address" in line:
                if current.get("ssid"):
                    networks.append(current)
                current = {"signal": 0}
            if "ESSID:" in line:
                match = re.search(r'ESSID:"(.+)"', line)
                if match:
                    current["ssid"] = match.group(1)
            if "Signal level=" in line:
                match = re.search(r"Signal level=(-?\d+)", line)
                if match:
                    dbm = int(match.group(1))
                    current["signal"] = max(0, min(100, 2 * (dbm + 100)))
        if current.get("ssid"):
            networks.append(current)

        seen = set()
        unique = []
        for net in networks:
            if net["ssid"] not in seen and net["ssid"]:
                seen.add(net["ssid"])
                unique.append(net)
        unique.sort(key=lambda x: x["signal"], reverse=True)
        return unique
    except Exception:
        return []


def save_wifi_config(ssid, password):
    """Save WiFi credentials to wpa_supplicant.conf."""
    try:
        header = (
            f"ctrl_interface=DIR=/var/run/wpa_supplicant GROUP=netdev\n"
            f"update_config=1\n"
            f"country={COUNTRY_CODE}\n"
        )
        networks = []
        if os.path.exists(WPA_CONF):
            with open(WPA_CONF, "r") as f:
                content = f.read()
            parts = re.split(r"(network\s*=\s*\{)", content)
            i = 1
            while i < len(parts):
                if "network" in parts[i] and i + 1 < len(parts):
                    block = parts[i] + parts[i + 1]
                    ssid_match = re.search(r'ssid="([^"]+)"', block)
                    if ssid_match and ssid_match.group(1) != ssid:
                        networks.append(block.strip())
                    i += 2
                else:
                    i += 1

        networks.append(
            f'network={{\n    ssid="{ssid}"\n    psk="{password}"\n    key_mgmt=WPA-PSK\n}}'
        )

        with open(WPA_CONF, "w") as f:
            f.write(header + "\n" + "\n\n".join(networks) + "\n")
        os.chmod(WPA_CONF, 0o600)
        return True
    except Exception:
        return False


def has_saved_networks():
    """Check if wpa_supplicant.conf contains any saved networks."""
    try:
        if os.path.exists(WPA_CONF):
            with open(WPA_CONF, "r") as f:
                return "ssid=" in f.read()
    except Exception:
        pass
    return False
