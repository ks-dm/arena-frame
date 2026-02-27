#!/bin/bash
PI_HOST="${1:-pi@frame.local}"

# Sync the arena-frame directory (new modular structure)
rsync -avz \
    --exclude='content/*' \
    --exclude='state.json' \
    --exclude='__pycache__' \
    --exclude='.git' \
    ./ $PI_HOST:~/arena-frame/

# Copy system config files
scp system/config/hostapd.conf $PI_HOST:/tmp/hostapd.conf
scp system/config/wifi-portal.conf $PI_HOST:/tmp/wifi-portal.conf
ssh $PI_HOST "sudo cp /tmp/hostapd.conf /etc/hostapd/hostapd.conf && sudo cp /tmp/wifi-portal.conf /etc/dnsmasq.d/wifi-portal.conf"

# Restart services
ssh $PI_HOST "sudo systemctl restart arena-frame arena-buttons"

echo "Synced and restarted services"
echo ""
echo "NOTE: If this is the first deploy of the new structure, update systemd services:"
echo "  arena-frame.service  → ExecStart=...python main.py"
echo "  arena-buttons.service → ExecStart=...python -m hardware.buttons"
echo "  arena-led.service    → ExecStart=...python -m hardware.led"
echo "  wifi-manager.service → ExecStart=...python -m wifi.manager"
echo "  wifi-portal-web.service → ExecStart=...python -m portal.app"
