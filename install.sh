#!/bin/bash
set -e

echo "========================================="
echo "  Arena Frame Installer"
echo "========================================="
echo ""

# Check if running on Raspberry Pi
if ! grep -q "Raspberry Pi" /proc/cpuinfo 2>/dev/null; then
    echo "Warning: This doesn't appear to be a Raspberry Pi"
    read -p "Continue anyway? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# Check if running as root
if [ "$EUID" -eq 0 ]; then
    echo "Please run without sudo. The script will ask for sudo when needed."
    exit 1
fi

INSTALL_DIR="$HOME/arena-frame"
VENV_DIR="$HOME/.virtualenvs/pimoroni"

echo "[1/8] Installing system dependencies..."
sudo apt update
sudo apt install -y \
    python3-pip \
    python3-venv \
    python3-dev \
    hostapd \
    dnsmasq \
    libopenjp2-7 \
    libtiff5 \
    git

echo "[2/8] Setting up Python virtual environment..."
mkdir -p "$HOME/.virtualenvs"
python3 -m venv "$VENV_DIR"
source "$VENV_DIR/bin/activate"

echo "[3/8] Installing Python packages..."
pip install --upgrade pip
pip install inky[rpi] flask pillow requests gpiozero gpiod

echo "[4/8] Cloning Arena Frame..."
if [ -d "$INSTALL_DIR" ]; then
    echo "Directory exists, pulling latest..."
    cd "$INSTALL_DIR"
    git pull
else
    git clone https://github.com/ks-dm/arena-frame.git "$INSTALL_DIR"
    cd "$INSTALL_DIR"
fi

# Create content directory
mkdir -p "$INSTALL_DIR/content"

echo "[5/8] Setting up configuration..."
# Create config directory
sudo mkdir -p /etc/photoframe

# Default config
sudo tee /etc/photoframe/config.json > /dev/null << 'CONFIGEOF'
{
  "refresh": "live",
  "order": "newest",
  "show_info": true,
  "dark_mode": false
}
CONFIGEOF

# Copy logo
if [ -f "$INSTALL_DIR/assets/arena.svg" ]; then
    sudo cp "$INSTALL_DIR/assets/arena.svg" /etc/photoframe/
fi

# Copy fonts to home directory
if [ -f "$INSTALL_DIR/assets/Areal-Bold.ttf" ]; then
    cp "$INSTALL_DIR/assets/Areal-Bold.ttf" "$HOME/"
    cp "$INSTALL_DIR/assets/Areal-Regular.ttf" "$HOME/"
fi

echo "[6/8] Setting up WiFi portal..."
# Configure hostapd
sudo cp "$INSTALL_DIR/system/config/hostapd.conf" /etc/hostapd/hostapd.conf

sudo tee /etc/default/hostapd > /dev/null << 'DEFAULTEOF'
DAEMON_CONF="/etc/hostapd/hostapd.conf"
DEFAULTEOF

# Configure dnsmasq
sudo cp "$INSTALL_DIR/system/config/wifi-portal.conf" /etc/dnsmasq.d/wifi-portal.conf

# Disable hostapd auto-start (wifi-manager controls it)
sudo systemctl disable hostapd 2>/dev/null || true

echo "[7/8] Installing systemd services..."

# Arena Frame main service
sudo tee /etc/systemd/system/arena-frame.service > /dev/null << 'SERVICEEOF'
[Unit]
Description=Arena Frame Display
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/arena-frame
ExecStart=/home/pi/.virtualenvs/pimoroni/bin/python /home/pi/arena-frame/main.py
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
SERVICEEOF

# Button handler service
sudo tee /etc/systemd/system/arena-buttons.service > /dev/null << 'SERVICEEOF'
[Unit]
Description=Arena Frame Button Handler
After=multi-user.target

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/arena-frame
ExecStart=/home/pi/.virtualenvs/pimoroni/bin/python -m hardware.buttons
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
SERVICEEOF

# LED blinker service
sudo tee /etc/systemd/system/arena-led.service > /dev/null << 'SERVICEEOF'
[Unit]
Description=Arena Frame LED Blinker

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/arena-frame
ExecStart=/home/pi/.virtualenvs/pimoroni/bin/python -m hardware.led
Restart=on-failure

[Install]
WantedBy=multi-user.target
SERVICEEOF

# WiFi manager service
sudo tee /etc/systemd/system/wifi-manager.service > /dev/null << 'SERVICEEOF'
[Unit]
Description=WiFi Manager - Auto AP/Client switching
After=network.target
Wants=network.target

[Service]
Type=simple
WorkingDirectory=/home/pi/arena-frame
ExecStartPre=/bin/sleep 10
ExecStart=/home/pi/.virtualenvs/pimoroni/bin/python -m wifi.manager
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
SERVICEEOF

# WiFi portal web service
sudo tee /etc/systemd/system/wifi-portal-web.service > /dev/null << 'SERVICEEOF'
[Unit]
Description=WiFi Configuration Web Portal
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/home/pi/arena-frame
ExecStart=/home/pi/.virtualenvs/pimoroni/bin/python -m portal.app
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
SERVICEEOF

# Reconnect handler
sudo tee /etc/systemd/system/arena-reconnect.service > /dev/null << 'SERVICEEOF'
[Unit]
Description=Arena Frame Reconnect Handler
After=network-online.target

[Service]
Type=oneshot
ExecStart=/bin/bash -c 'sleep 5 && systemctl restart arena-frame'

[Install]
WantedBy=multi-user.target
SERVICEEOF

echo "[8/8] Enabling services and finalizing..."
sudo systemctl daemon-reload
sudo systemctl enable arena-frame
sudo systemctl enable arena-buttons
sudo systemctl enable wifi-manager

# Set up sudoers for services
sudo tee /etc/sudoers.d/arena-frame > /dev/null << 'SUDOEOF'
pi ALL=(ALL) NOPASSWD: /usr/bin/systemctl restart wifi-manager
pi ALL=(ALL) NOPASSWD: /usr/bin/systemctl restart arena-frame
pi ALL=(ALL) NOPASSWD: /usr/bin/systemctl start arena-led
pi ALL=(ALL) NOPASSWD: /usr/bin/systemctl stop arena-led
pi ALL=(ALL) NOPASSWD: /usr/bin/systemctl start hostapd
pi ALL=(ALL) NOPASSWD: /usr/bin/systemctl stop hostapd
pi ALL=(ALL) NOPASSWD: /usr/bin/systemctl start dnsmasq
pi ALL=(ALL) NOPASSWD: /usr/bin/systemctl stop dnsmasq
pi ALL=(ALL) NOPASSWD: /usr/bin/systemctl start wifi-portal-web
pi ALL=(ALL) NOPASSWD: /usr/bin/systemctl stop wifi-portal-web
SUDOEOF
sudo chmod 440 /etc/sudoers.d/arena-frame

# Enable SPI (required for Inky display)
if ! grep -q "^dtparam=spi=on" /boot/firmware/config.txt 2>/dev/null; then
    echo "Enabling SPI..."
    sudo bash -c 'echo "dtparam=spi=on" >> /boot/firmware/config.txt'
fi

# Set WiFi country
sudo raspi-config nonint do_wifi_country GB

echo ""
echo "========================================="
echo "  Installation Complete!"
echo "========================================="
echo ""
echo "Next steps:"
echo "1. Reboot: sudo reboot"
echo "2. Connect to 'ArenaFrame-Setup' WiFi (password: arenaframe)"
echo "3. Open http://192.168.4.1 to configure"
echo ""
echo "Commands:"
echo "  View logs:    sudo journalctl -u arena-frame -f"
echo "  Restart:      sudo systemctl restart arena-frame"
echo "  Update:       cd ~/arena-frame && git pull"
echo ""
