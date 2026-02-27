#!/usr/bin/env python3
"""Flask web portal for WiFi and channel configuration.

Serves at 192.168.4.1:80 during AP setup mode.
"""

import os
import threading
from flask import Flask, request, render_template, redirect, send_file

from config import (
    FONT_DIR, LOGO_FILE,
    load_config, save_config, get_error_message,
    REFRESH_OPTIONS, ORDER_OPTIONS,
)
from wifi.utils import scan_wifi_networks, save_wifi_config, get_current_ssid
from wifi.manager import trigger_reconnect

app = Flask(__name__, template_folder="templates")


@app.route("/logo")
def logo():
    if LOGO_FILE.exists():
        return send_file(str(LOGO_FILE), mimetype="image/svg+xml")
    return "", 404


@app.route("/fonts/<filename>")
def fonts(filename):
    font_path = FONT_DIR / filename
    if font_path.exists():
        return send_file(str(font_path), mimetype="font/ttf")
    return "", 404


@app.route("/")
def index():
    return render_template(
        "setup.html",
        networks=scan_wifi_networks(),
        config=load_config(),
        refresh_options=REFRESH_OPTIONS,
        order_options=ORDER_OPTIONS,
        current_ssid=get_current_ssid(),
        message=get_error_message(),
    )


@app.route("/connect", methods=["POST"])
def connect():
    ssid = request.form.get("ssid", "")
    password = request.form.get("password", "")

    if ssid == "__manual__":
        ssid = request.form.get("manual_ssid", "")

    config = load_config()
    config["channel_slug"] = request.form.get("channel_slug", "").strip()
    config["arena_token"] = request.form.get("arena_token", "").strip() or None
    config["refresh"] = request.form.get("refresh", "live")
    config["order"] = request.form.get("order", "newest")
    config["show_info"] = request.form.get("show_info") == "1"
    config["dark_mode"] = request.form.get("dark_mode") == "1"
    save_config(config)

    if ssid and password:
        save_wifi_config(ssid, password)

    threading.Thread(target=trigger_reconnect, daemon=False).start()
    return render_template("connecting.html")


@app.route("/generate_204")
@app.route("/gen_204")
@app.route("/hotspot-detect.html")
@app.route("/canonical.html")
@app.route("/success.txt")
@app.route("/ncsi.txt")
@app.route("/connecttest.txt")
@app.route("/redirect")
@app.route("/library/test/success.html")
def captive():
    return redirect("/")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=80)
