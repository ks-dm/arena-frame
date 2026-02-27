# Arena Frame

An open-source e-ink photo frame that displays content from your [Are.na](https://are.na) channels. Built for Raspberry Pi with Pimoroni Inky Impression displays.

![Arena Frame](https://are.na/images/arena-logo.svg)

## Features

- **Live sync** — Displays new blocks as they're added to your channel
- **Multiple refresh modes** — Live, 5min, 15min, 30min, 1hr, 12hr, 24hr
- **Cycle modes** — Random, oldest first, newest first
- **Dark mode** — Easy on the eyes
- **WiFi setup portal** — Configure via your phone, no command line needed
- **Open source** — Hack it, extend it, make it yours

## Hardware Required

- Raspberry Pi Zero 2 W (recommended) or Pi 3/4
- [Pimoroni Inky Impression](https://shop.pimoroni.com/products/inky-impression) (7.3" or 13.3")
- MicroSD card (8GB+)
- USB-C power supply

## Installation

### Option 1: Pre-built Image (Recommended)

The easiest way to get started.

1. **Download the image**
   - Go to [Releases](https://github.com/ks-dm/arena-frame/releases)
   - Download `arenaframe.img.gz`

2. **Flash to SD card**
   - Download [Raspberry Pi Imager](https://www.raspberrypi.com/software/)
   - Insert your SD card
   - Open Raspberry Pi Imager
   - Click **Choose OS** → scroll down → **Use custom**
   - Select the downloaded `arenaframe.img.gz`
   - Click **Choose Storage** → select your SD card
   - Click **Write** and wait for it to complete

3. **First boot**
   - Insert SD card into your Pi
   - Connect the Inky display
   - Power on
   - Wait ~60 seconds for the LED to start blinking

4. **Configure**
   - On your phone, connect to WiFi network **ArenaFrame-Setup** (password: `arenaframe`)
   - A setup page should open automatically (or go to http://192.168.4.1)
   - Select your WiFi network and enter password
   - Enter your Are.na channel slug (the last part of the URL, e.g., `my-channel` from `are.na/user/my-channel`)
   - Tap **Save**

5. **Done!**
   - The frame will connect to WiFi and start displaying your channel

---

### Option 2: Install Script

For existing Raspberry Pi OS installations or if you want more control.

**Requirements:**
- Raspberry Pi with Raspberry Pi OS (Bookworm or later)
- Pimoroni Inky Impression connected via GPIO

**Steps:**

1. **Clone the repository**
```bash
   git clone https://github.com/ks-dm/arena-frame.git
   cd arena-frame
```

2. **Run the installer**
```bash
   ./install.sh
```
   This will:
   - Install system dependencies
   - Set up Python virtual environment
   - Install Python packages (inky, flask, pillow, etc.)
   - Configure WiFi portal and hostapd
   - Install and enable systemd services

3. **Reboot**
```bash
   sudo reboot
```

4. **Configure**
   - Connect to **ArenaFrame-Setup** WiFi (password: `arenaframe`)
   - Open http://192.168.4.1
   - Enter your WiFi credentials and Are.na channel
   - Save

---

## Configuration Options

| Setting | Description |
|---------|-------------|
| **Network** | Your WiFi network name |
| **Password** | Your WiFi password |
| **Channel** | Are.na channel slug |
| **Refresh** | How often to check for new content (Live, 5min, 15min, etc.) |
| **Order** | Display order when cycling (Random, Oldest first, Newest first) |
| **Show Channel Name** | Display channel info overlay on images |
| **Dark Mode** | Dark background for text blocks |
| **Token** | For private channels — get from [dev.are.na](https://dev.are.na/oauth/applications) |

## Usage

### Physical Button

- **Button A** (hold 3 seconds): Enter setup mode to reconfigure WiFi or channel

### Re-entering Setup Mode

If you need to change settings:
1. Hold Button A for 3 seconds, OR
2. If the frame can't connect to WiFi, it automatically enters setup mode (LED blinks)

### Updating

SSH into your Pi and run:
```bash
cd ~/arena-frame
git pull
sudo systemctl restart arena-frame
```

## Troubleshooting

**LED keeps blinking**
- WiFi credentials may be incorrect
- Channel slug may be wrong
- Reconnect to ArenaFrame-Setup and check settings

**Display not updating**
- Check logs: `sudo journalctl -u arena-frame -f`
- Restart service: `sudo systemctl restart arena-frame`

**Can't connect to ArenaFrame-Setup**
- Make sure you're within range
- Try forgetting the network on your phone and reconnecting
- Power cycle the Pi

**Private channel not working**
- Make sure you've added an access token in the Advanced section
- Get your token from [dev.are.na](https://dev.are.na/oauth/applications)

## Project Structure
```
arena-frame/
├── main.py                 # Entry point
├── config.py               # Configuration management
├── sources/                # Content sources (Are.na API)
├── display/                # E-ink display handling
├── portal/                 # WiFi setup web portal
├── hardware/               # Buttons and LED
├── wifi/                   # WiFi management
└── utils/                  # Shared utilities
```

## Contributing

Contributions welcome! Some ideas:

- Additional content sources (RSS, local folders, other APIs)
- New dithering algorithms
- Support for other e-ink displays
- UI improvements

## License

MIT License — do whatever you want with it.

## Credits

- Built for [Are.na](https://are.na)
- Display library by [Pimoroni](https://github.com/pimoroni/inky)
- Fonts: Areal by [Your Font Source]

---

Made with ♥ for the Are.na community
