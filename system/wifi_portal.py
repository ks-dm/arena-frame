#!/usr/bin/env python3
"""
WiFi Configuration Portal - Minimal Dark Theme
"""

from flask import Flask, request, render_template_string, redirect, send_file
import subprocess
import os
import re
import threading
import json

app = Flask(__name__)

WPA_CONF = "/etc/wpa_supplicant/wpa_supplicant.conf"
WIFI_INTERFACE = "wlan0"
CONFIG_FILE = "/etc/photoframe/config.json"
LOGO_FILE = "/etc/photoframe/arena.svg"
FONT_DIR = "/home/pi"
AP_MODE_FLAG = "/tmp/force_ap_mode"
ERROR_FILE = "/tmp/arena-frame-error"
COUNTRY_CODE = "GB"

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

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>Frame Setup</title>
    <style>
        @font-face {
            font-family: 'Areal';
            src: url('/fonts/Areal-Regular.ttf') format('truetype');
            font-weight: normal;
        }
        @font-face {
            font-family: 'Areal';
            src: url('/fonts/Areal-Bold.ttf') format('truetype');
            font-weight: bold;
        }
        * {
            box-sizing: border-box;
            margin: 0;
            padding: 0;
            -webkit-tap-highlight-color: transparent;
        }
        body {
            font-family: 'Areal', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #000;
            min-height: 100vh;
            min-height: -webkit-fill-available;
            display: flex;
            justify-content: center;
            padding: 16px;
            color: #fff;
        }
        html {
            height: -webkit-fill-available;
        }
        .container {
            width: 100%;
            max-width: 380px;
        }
        .logo-header {
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 10px;
            margin-bottom: 20px;
        }
        .logo {
            height: 28px;
            filter: invert(1);
        }
        .logo-text {
            font-family: 'Areal', Arial, sans-serif;
            font-weight: bold;
            font-size: 24px;
            color: #fff;
        }
        .error-banner {
            background: #3a2a2a;
            color: #ff6b6b;
            padding: 10px 14px;
            border-radius: 12px;
            margin-bottom: 12px;
            font-size: 13px;
            text-align: center;
        }
        .group {
            background: #1c1c1e;
            border-radius: 12px;
            margin-bottom: 8px;
            overflow: hidden;
        }
        .row {
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 12px 14px;
            border-bottom: 1px solid #2c2c2e;
        }
        .row:last-child {
            border-bottom: none;
        }
        .row-label {
            color: #8e8e93;
            font-size: 14px;
            flex-shrink: 0;
        }
        .row-value {
            display: flex;
            align-items: center;
            gap: 6px;
        }
        select, input[type="text"], input[type="password"] {
            background: transparent;
            border: none;
            color: #007AFF;
            font-size: 14px;
            font-family: 'Areal', -apple-system, BlinkMacSystemFont, sans-serif;
            text-align: right;
            outline: none;
            min-width: 100px;
            max-width: 160px;
        }
        select {
            -webkit-appearance: none;
            appearance: none;
            cursor: pointer;
        }
        input::placeholder {
            color: #555;
        }
        select option {
            background: #1c1c1e;
            color: #fff;
        }
        .refresh-btn {
            background: transparent;
            border: none;
            color: #007AFF;
            font-size: 16px;
            cursor: pointer;
            padding: 0;
            line-height: 1;
        }
        .chevron {
            color: #007AFF;
            font-size: 11px;
        }
        .toggle-container {
            position: relative;
            width: 46px;
            height: 28px;
        }
        .toggle-input {
            opacity: 0;
            width: 0;
            height: 0;
        }
        .toggle-slider {
            position: absolute;
            cursor: pointer;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            background-color: #39393d;
            transition: 0.3s;
            border-radius: 28px;
        }
        .toggle-slider:before {
            position: absolute;
            content: "";
            height: 24px;
            width: 24px;
            left: 2px;
            bottom: 2px;
            background-color: #fff;
            transition: 0.3s;
            border-radius: 50%;
        }
        .toggle-input:checked + .toggle-slider {
            background-color: #30d158;
        }
        .toggle-input:checked + .toggle-slider:before {
            transform: translateX(18px);
        }
        .save-btn {
            width: 100%;
            padding: 14px;
            background: #007AFF;
            color: white;
            border: none;
            border-radius: 12px;
            font-size: 16px;
            font-family: 'Areal', -apple-system, BlinkMacSystemFont, sans-serif;
            font-weight: 600;
            cursor: pointer;
            margin-top: 12px;
        }
        .save-btn:active {
            background: #0056b3;
        }
        .save-btn:disabled {
            background: #555;
            cursor: not-allowed;
        }
        .section-label {
            color: #8e8e93;
            font-size: 12px;
            text-transform: uppercase;
            margin: 12px 0 6px 14px;
            letter-spacing: 0.5px;
        }
        .help-text {
            color: #6e6e73;
            font-size: 11px;
            margin: 3px 14px 8px 14px;
            line-height: 1.3;
        }
        .help-text a {
            color: #007AFF;
            text-decoration: none;
        }
        .manual-ssid {
            display: none;
        }
        .manual-ssid.show {
            display: flex;
        }
        .loading {
            display: none;
            position: fixed;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            background: rgba(0,0,0,0.8);
            justify-content: center;
            align-items: center;
            flex-direction: column;
            z-index: 100;
        }
        .spinner {
            border: 3px solid #333;
            border-top: 3px solid #007AFF;
            border-radius: 50%;
            width: 36px;
            height: 36px;
            animation: spin 1s linear infinite;
            margin-bottom: 14px;
        }
        @keyframes spin {
            0% { transform: rotate(0deg); }
            100% { transform: rotate(360deg); }
        }
        .loading p {
            color: #8e8e93;
            font-size: 14px;
        }
        select:disabled {
            opacity: 0.5;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="logo-header">
            <img src="/logo" alt="Are.na" class="logo">
            <span class="logo-text">Frame</span>
        </div>
        
        {% if message %}
        <div class="error-banner">{{ message }}</div>
        {% endif %}
        
        <form id="wifi-form" action="/connect" method="POST">
            <div class="group">
                <div class="row">
                    <span class="row-label">Network</span>
                    <div class="row-value">
                        <select id="ssid-select" name="ssid" onchange="handleSSIDChange()">
                            <option value="">{{ current_ssid if current_ssid else 'Select' }}</option>
                            {% for network in networks %}
                            {% if network.ssid != current_ssid %}
                            <option value="{{ network.ssid }}">{{ network.ssid }}</option>
                            {% endif %}
                            {% endfor %}
                            <option value="__manual__">Other...</option>
                        </select>
                        <button type="button" class="refresh-btn" onclick="location.reload()">↻</button>
                    </div>
                </div>
                <div class="row manual-ssid" id="manual-ssid-row">
                    <span class="row-label">SSID</span>
                    <input type="text" id="manual-ssid" name="manual_ssid" placeholder="Network name" autocomplete="off" autocorrect="off" autocapitalize="off" spellcheck="false">
                </div>
                <div class="row">
                    <span class="row-label">Password</span>
                    <input type="password" id="password" name="password" placeholder="••••••••">
                </div>
            </div>
            
            <div class="group">
                <div class="row">
                    <span class="row-label">Channel</span>
                    <input type="text" id="channel-slug" name="channel_slug" placeholder="channel-slug" value="{{ config.channel_slug or '' }}" autocomplete="off" autocorrect="off" autocapitalize="off" spellcheck="false">
                </div>
            </div>
            <p class="help-text">Last part of URL: are.na/user/<strong>my-channel</strong></p>
            
            <div class="group">
                <div class="row">
                    <span class="row-label">Refresh</span>
                    <div class="row-value">
                        <select id="refresh" name="refresh" onchange="handleRefreshChange()">
                            {% for value, label in refresh_options %}
                            <option value="{{ value }}" {{ 'selected' if config.refresh == value else '' }}>{{ label }}</option>
                            {% endfor %}
                        </select>
                        <span class="chevron">›</span>
                    </div>
                </div>
                <div class="row">
                    <span class="row-label">Order</span>
                    <div class="row-value">
                        <select id="order" name="order" {{ 'disabled' if config.refresh == 'live' else '' }}>
                            {% for value, label in order_options %}
                            <option value="{{ value }}" {{ 'selected' if config.order == value else '' }}>{{ label }}</option>
                            {% endfor %}
                        </select>
                        <span class="chevron">›</span>
                    </div>
                </div>
            </div>
            
            <div class="section-label">Display</div>
            <div class="group">
                <div class="row">
                    <span class="row-label">Show Channel Name</span>
                    <label class="toggle-container">
                        <input type="checkbox" class="toggle-input" name="show_info" value="1" {{ 'checked' if config.show_info != false else '' }}>
                        <span class="toggle-slider"></span>
                    </label>
                </div>
                <div class="row">
                    <span class="row-label">Dark Mode</span>
                    <label class="toggle-container">
                        <input type="checkbox" class="toggle-input" name="dark_mode" value="1" {{ 'checked' if config.dark_mode else '' }}>
                        <span class="toggle-slider"></span>
                    </label>
                </div>
            </div>
            
            <div class="section-label">Advanced</div>
            <div class="group">
                <div class="row">
                    <span class="row-label">Token</span>
                    <input type="password" id="arena-token" name="arena_token" placeholder="Optional" value="{{ config.arena_token or '' }}">
                </div>
            </div>
            <p class="help-text">For private channels. Get from <a href="https://dev.are.na/oauth/applications" target="_blank">dev.are.na</a></p>
            
            <button type="submit" class="save-btn" id="submit-btn">Save</button>
        </form>
        
        <div class="loading" id="loading">
            <div class="spinner"></div>
            <p>Saving...</p>
        </div>
    </div>

    <script>
        function handleSSIDChange() {
            const select = document.getElementById('ssid-select');
            const manualRow = document.getElementById('manual-ssid-row');
            manualRow.classList.toggle('show', select.value === '__manual__');
        }
        
        function handleRefreshChange() {
            const refresh = document.getElementById('refresh').value;
            const order = document.getElementById('order');
            order.disabled = refresh === 'live';
        }
        
        document.getElementById('wifi-form').addEventListener('submit', function(e) {
            document.getElementById('loading').style.display = 'flex';
            document.getElementById('submit-btn').disabled = true;
        });
    </script>
</body>
</html>
"""

CONNECTING_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Settings Saved</title>
    <style>
        @font-face {
            font-family: 'Areal';
            src: url('/fonts/Areal-Regular.ttf') format('truetype');
            font-weight: normal;
        }
        @font-face {
            font-family: 'Areal';
            src: url('/fonts/Areal-Bold.ttf') format('truetype');
            font-weight: bold;
        }
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: 'Areal', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #000;
            min-height: 100vh;
            display: flex;
            justify-content: center;
            align-items: center;
            text-align: center;
            color: #fff;
            padding: 24px;
        }
        .container { max-width: 280px; }
        .checkmark {
            font-size: 48px;
            margin-bottom: 16px;
        }
        h1 { font-size: 20px; font-weight: bold; margin-bottom: 12px; }
        p { color: #8e8e93; font-size: 15px; line-height: 1.5; margin-bottom: 8px; }
        .hint {
            color: #6e6e73;
            font-size: 13px;
            margin-top: 24px;
            padding-top: 24px;
            border-top: 1px solid #2c2c2e;
            line-height: 1.5;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="checkmark">✓</div>
        <h1>Settings Saved</h1>
        <p>You can close this page now.</p>
        <p class="hint">If the LED starts blinking again, your WiFi password or channel name may be incorrect. Reconnect to "ArenaFrame-Setup" to try again.</p>
    </div>
</body>
</html>
"""


def load_config():
    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, 'r') as f:
                return json.load(f)
    except:
        pass
    return {'refresh': 'live', 'order': 'newest', 'show_info': True, 'dark_mode': False}


def save_config(config):
    try:
        os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
        with open(CONFIG_FILE, 'w') as f:
            json.dump(config, f, indent=2)
        return True
    except:
        return False


def get_current_ssid():
    """Get currently connected or last saved WiFi SSID"""
    # First try actual connection
    try:
        result = subprocess.run(['iwgetid', '-r'], capture_output=True, text=True, timeout=5)
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except:
        pass
    
    # Fall back to last saved network in wpa_supplicant.conf
    try:
        if os.path.exists(WPA_CONF):
            with open(WPA_CONF, 'r') as f:
                content = f.read()
            matches = re.findall(r'ssid="([^"]+)"', content)
            if matches:
                return matches[-1]  # Return last saved network
    except:
        pass
    
    return None


def get_error_message():
    try:
        if os.path.exists(ERROR_FILE):
            with open(ERROR_FILE, 'r') as f:
                error_data = json.load(f)
            error_type = error_data.get("type", "")
            if error_type == "channel_not_found":
                return "Channel not found - check spelling"
            elif error_type == "network":
                return "Can't connect to Are.na"
            elif error_type == "unauthorized":
                return "Access denied - check token"
    except:
        pass
    return None


def clear_error_file():
    try:
        if os.path.exists(ERROR_FILE):
            os.remove(ERROR_FILE)
    except:
        pass


def scan_wifi_networks():
    networks = []
    try:
        result = subprocess.run(['iwlist', WIFI_INTERFACE, 'scan'], capture_output=True, text=True, timeout=30)
        current = {}
        for line in result.stdout.split('\n'):
            line = line.strip()
            if 'Cell' in line and 'Address' in line:
                if current.get('ssid'):
                    networks.append(current)
                current = {'signal': 0}
            if 'ESSID:' in line:
                match = re.search(r'ESSID:"(.+)"', line)
                if match:
                    current['ssid'] = match.group(1)
            if 'Signal level=' in line:
                match = re.search(r'Signal level=(-?\d+)', line)
                if match:
                    dbm = int(match.group(1))
                    current['signal'] = max(0, min(100, 2 * (dbm + 100)))
        if current.get('ssid'):
            networks.append(current)
        seen = set()
        unique = []
        for net in networks:
            if net['ssid'] not in seen and net['ssid']:
                seen.add(net['ssid'])
                unique.append(net)
        unique.sort(key=lambda x: x['signal'], reverse=True)
        return unique
    except:
        return []


def save_wifi_config(ssid, password):
    try:
        header = f"ctrl_interface=DIR=/var/run/wpa_supplicant GROUP=netdev\nupdate_config=1\ncountry={COUNTRY_CODE}\n"
        networks = []
        if os.path.exists(WPA_CONF):
            with open(WPA_CONF, 'r') as f:
                content = f.read()
            parts = re.split(r'(network\s*=\s*\{)', content)
            i = 1
            while i < len(parts):
                if 'network' in parts[i] and i + 1 < len(parts):
                    block = parts[i] + parts[i + 1]
                    ssid_match = re.search(r'ssid="([^"]+)"', block)
                    if ssid_match and ssid_match.group(1) != ssid:
                        networks.append(block.strip())
                    i += 2
                else:
                    i += 1
        networks.append(f'network={{\n    ssid="{ssid}"\n    psk="{password}"\n    key_mgmt=WPA-PSK\n}}')
        with open(WPA_CONF, 'w') as f:
            f.write(header + "\n" + "\n\n".join(networks) + "\n")
        os.chmod(WPA_CONF, 0o600)
        return True
    except:
        return False


def trigger_reconnect():
    try:
        if os.path.exists(AP_MODE_FLAG):
            os.remove(AP_MODE_FLAG)
    except:
        pass
    clear_error_file()
    try:
        subprocess.run(['systemctl', 'restart', 'wifi-manager'], timeout=30)
    except:
        pass
    try:
        subprocess.run(['systemctl', 'start', 'arena-reconnect'], timeout=5)
    except:
        pass


@app.route('/logo')
def logo():
    if os.path.exists(LOGO_FILE):
        return send_file(LOGO_FILE, mimetype='image/svg+xml')
    return '', 404


@app.route('/fonts/<filename>')
def fonts(filename):
    font_path = os.path.join(FONT_DIR, filename)
    if os.path.exists(font_path):
        return send_file(font_path, mimetype='font/ttf')
    return '', 404


@app.route('/')
def index():
    return render_template_string(
        HTML_TEMPLATE,
        networks=scan_wifi_networks(),
        config=load_config(),
        refresh_options=REFRESH_OPTIONS,
        order_options=ORDER_OPTIONS,
        current_ssid=get_current_ssid(),
        message=get_error_message(),
    )


@app.route('/connect', methods=['POST'])
def connect():
    ssid = request.form.get('ssid', '')
    password = request.form.get('password', '')
    
    if ssid == '__manual__':
        ssid = request.form.get('manual_ssid', '')
    
    config = load_config()
    config['channel_slug'] = request.form.get('channel_slug', '').strip()
    config['arena_token'] = request.form.get('arena_token', '').strip() or None
    config['refresh'] = request.form.get('refresh', 'live')
    config['order'] = request.form.get('order', 'newest')
    config['show_info'] = request.form.get('show_info') == '1'
    config['dark_mode'] = request.form.get('dark_mode') == '1'
    save_config(config)
    
    wifi_changed = False
    if ssid and password:
        wifi_changed = save_wifi_config(ssid, password)
    
    threading.Thread(target=trigger_reconnect, daemon=False).start()
    
    return render_template_string(CONNECTING_TEMPLATE)


@app.route('/generate_204')
@app.route('/gen_204')
@app.route('/hotspot-detect.html')
@app.route('/canonical.html')
@app.route('/success.txt')
@app.route('/ncsi.txt')
@app.route('/connecttest.txt')
@app.route('/redirect')
@app.route('/library/test/success.html')
def captive():
    return redirect('/')


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=80)
