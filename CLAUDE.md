# Arena Frame - Project Context

## Overview
E-ink photo frame displaying content from Are.na channels. Runs on Raspberry Pi Zero 2 W with Pimoroni Inky Impression display (7.3" or 13.3").

## Architecture

### Project Structure
```
arena-frame/
├── main.py                 # Entry point — scheduler loop (direct imports, no subprocesses)
├── config.py               # Unified config/state/error management, all path constants
│
├── sources/                # Content sources (swappable via ContentSource base class)
│   ├── __init__.py         # ContentSource ABC
│   ├── arena.py            # Are.na API client, block parsing, download, live/cycle modes
│   └── local.py            # (future) Local folder source stub
│
├── display/                # Display handling
│   ├── __init__.py
│   ├── eink.py             # Hardware abstraction (Inky auto-detect, canvas, rotation)
│   ├── renderer.py         # Image compositing, overlays, channel info, error display
│   ├── dither.py           # Dithering algorithm plugin point (default = PIL built-in)
│   └── text.py             # Font loading, text measurement, wrapping, rendering
│
├── wifi/                   # WiFi management
│   ├── __init__.py
│   ├── manager.py          # Python state machine replacing wifi-manager.sh
│   └── utils.py            # WiFi scanning, WPA config, SSID detection
│
├── portal/                 # Web portal
│   ├── __init__.py
│   ├── app.py              # Flask routes (uses config, wifi.utils, wifi.manager)
│   └── templates/          # Extracted HTML templates (were inline Python strings)
│       ├── setup.html
│       └── connecting.html
│
├── hardware/               # Hardware interfaces
│   ├── __init__.py
│   ├── buttons.py          # GPIO button handler (gpiozero)
│   └── led.py              # LED blinker (gpiod)
│
├── utils/                  # Shared utilities (logging, AP trigger, duration formatting)
│   └── __init__.py
│
├── system/                 # System config files + legacy scripts for reference
│   ├── config/
│   │   ├── hostapd.conf
│   │   └── wifi-portal.conf
│   ├── wifi-manager.sh     # Original bash script (replaced by wifi/manager.py)
│   └── wifi_portal.py      # Original portal (replaced by portal/app.py)
│
├── content/                # Downloaded content (temporary, auto-cleared)
├── state.json              # Runtime state (auto-generated)
└── CLAUDE.md
```

### System Services (`/etc/systemd/system/`)
- `arena-frame.service` — ExecStart: `python main.py`
- `arena-buttons.service` — ExecStart: `python -m hardware.buttons`
- `arena-led.service` — ExecStart: `python -m hardware.led`
- `wifi-manager.service` — ExecStart: `python -m wifi.manager`
- `wifi-portal-web.service` — ExecStart: `python -m portal.app`

### Configuration
- `/etc/photoframe/config.json` - User settings (channel, refresh, theme)
- `/etc/hostapd/hostapd.conf` - AP configuration
- `/etc/dnsmasq.d/wifi-portal.conf` - DNS/DHCP for captive portal
- `/home/pi/Areal-Bold.ttf`, `Areal-Regular.ttf` - Custom fonts

## Key Technical Details

### Display
- Uses `inky.auto` for hardware detection
- Resolution read dynamically from `display.resolution`
- Canvas rotated 90° CCW before display
- `fit_width()` scales images to match width, maintains aspect ratio, centers vertically
- Supports 7.3" (800x480) and 13.3" (1600x1200) displays

### GPIO Conflicts
- 13.3" display uses GPIO16 for SPI chip select
- Buttons must avoid GPIO16 - currently only using GPIO5 (Button A)

### WiFi Flow
1. Boot → wifi-manager checks for saved networks
2. No networks → Start AP mode ("ArenaFrame-Setup")
3. User connects → Captive portal at 192.168.4.1
4. User saves config → Switch to client mode
5. Connection fails → Return to AP mode

### Error Handling
- `/tmp/arena-frame-error` - JSON with error type
- wifi-manager monitors for channel errors → restarts AP

### Config Format
```json
{
  "channel_slug": "my-channel",
  "arena_token": null,
  "refresh": "live",
  "order": "newest",
  "show_info": true,
  "dark_mode": false
}
```

## Development Commands
```bash
# SSH access
ssh pi@frame.local           # WiFi
ssh pi@192.168.7.2           # USB

# Manual display test
~/.virtualenvs/pimoroni/bin/python -m display.renderer ~/test.jpg

# Restart services
sudo systemctl restart arena-frame
sudo systemctl restart wifi-manager

# View logs
sudo journalctl -u arena-frame -f
sudo journalctl -u wifi-manager -f

# Sync from Mac to Pi
./sync-to-pi.sh              # or: ./sync-to-pi.sh pi@192.168.7.2

# Clear WiFi for testing
sudo bash -c 'cat > /etc/wpa_supplicant/wpa_supplicant.conf << EOF
ctrl_interface=DIR=/var/run/wpa_supplicant GROUP=netdev
update_config=1
country=GB
EOF'
sudo reboot
```

## Completed Refactoring

1. **Modular dithering** — Plugin-style algorithms in `display/dither.py`
2. **Content source abstraction** — `ContentSource` ABC in `sources/__init__.py`; `ArenaSource` implemented
3. **Display abstraction** — `EinkDisplay` wrapper in `display/eink.py`
4. **Unified config** — Single `config.py` with all paths, constants, config/state/error helpers
5. **Python wifi-manager** — `wifi/manager.py` replaces bash script
6. **Separate templates** — HTML extracted to `portal/templates/`
7. **Direct imports** — `main.py` calls modules directly instead of spawning subprocesses

## Future Work

- Implement `sources/local.py` for local folder content
- Add custom dithering algorithms (Atkinson, etc.) in `display/dither.py`
- RSS/URL content source
- Display driver abstraction for non-Inky displays

## Known Issues

- First cold boot can fail WiFi connection (timing issue with brcmfmac driver)
- Client devices cache WPA credentials causing "incorrect password" on reconnect
- Captive portal auto-open inconsistent on iOS