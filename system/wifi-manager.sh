#!/bin/bash
# WiFi Manager - Switches between AP mode and Client mode

WIFI_INTERFACE="wlan0"
AP_SSID="ArenaFrame-Setup"
AP_PASSWORD="arenaframe"
AP_IP="192.168.4.1"
WPA_CONF="/etc/wpa_supplicant/wpa_supplicant.conf"
CONNECTION_TIMEOUT=30

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1"
}

get_country_code() {
    if [ -f "/etc/photoframe/config.json" ]; then
        country=$(grep -o '"country": *"[^"]*"' /etc/photoframe/config.json | cut -d'"' -f4)
        if [ -n "$country" ]; then
            echo "$country"
            return
        fi
    fi
    echo "US"
}

check_force_ap_mode() {
    if [ -f "/tmp/force_ap_mode" ]; then
        return 0
    fi
    return 1
}

check_wifi_connected() {
    local state=$(wpa_cli -i ${WIFI_INTERFACE} status 2>/dev/null | grep "wpa_state=" | cut -d= -f2)
    local ssid=$(wpa_cli -i ${WIFI_INTERFACE} status 2>/dev/null | grep "^ssid=" | cut -d= -f2)
    if [ "$state" = "COMPLETED" ] && [ -n "$ssid" ] && [ "$ssid" != "$AP_SSID" ]; then
        return 0
    fi
    return 1
}

check_internet() {
    ping -c 1 -W 5 8.8.8.8 > /dev/null 2>&1
}

cleanup() {
    log "Cleaning up..."
    systemctl stop hostapd 2>/dev/null || true
    systemctl stop dnsmasq 2>/dev/null || true
    systemctl stop wifi-portal-web 2>/dev/null || true
    pkill -9 hostapd 2>/dev/null || true
    pkill -9 wpa_supplicant 2>/dev/null || true
    pkill -9 dhclient 2>/dev/null || true
    rm -f /var/run/wpa_supplicant/wlan0 2>/dev/null || true
    ip addr flush dev ${WIFI_INTERFACE} 2>/dev/null || true
    iptables -t nat -F 2>/dev/null || true
}

start_ap_mode() {
    log "Starting AP mode..."
    
    cleanup
    sleep 2
    
    ip link set ${WIFI_INTERFACE} down
    sleep 1
    iw dev ${WIFI_INTERFACE} set type __ap
    sleep 1
    ip link set ${WIFI_INTERFACE} up
    sleep 1
    
    ip addr add ${AP_IP}/24 dev ${WIFI_INTERFACE}
    
    if ! systemctl start hostapd; then
        log "ERROR: hostapd failed to start"
        return 1
    fi
    sleep 2
    # Update hostapd country code
    COUNTRY=$(get_country_code)
    sed -i "s/country_code=.*/country_code=$COUNTRY/" /etc/hostapd/hostapd.conf
    
    systemctl start dnsmasq || true
    
    iptables -t nat -A PREROUTING -i ${WIFI_INTERFACE} -p tcp --dport 80 -j DNAT --to-destination ${AP_IP}:80
    iptables -t nat -A PREROUTING -i ${WIFI_INTERFACE} -p tcp --dport 443 -j DNAT --to-destination ${AP_IP}:80
    
    systemctl start wifi-portal-web || true
    
    log "AP mode started. SSID: ${AP_SSID}"
   # Start LED blinker
    systemctl start arena-led 2>/dev/null || true
    log "LED blinker started"
    return 0
}

start_client_mode() {
    log "Starting client mode..."
   # Stop LED blinker
    systemctl stop arena-led 2>/dev/null || true
    
    cleanup
    sleep 2
    
    ip link set ${WIFI_INTERFACE} down
    sleep 1
    iw dev ${WIFI_INTERFACE} set type managed
    sleep 1
    ip link set ${WIFI_INTERFACE} up
    sleep 2
    
    wpa_supplicant -B -i ${WIFI_INTERFACE} -c ${WPA_CONF}
    sleep 5
    
    log "Waiting for WiFi connection..."
    for i in $(seq 1 ${CONNECTION_TIMEOUT}); do
        if check_wifi_connected; then
            log "Connected to WiFi!"
            dhclient ${WIFI_INTERFACE} 2>/dev/null || true
            sleep 2
            return 0
        fi
        sleep 1
    done
    
    log "Failed to connect to WiFi"
    return 1
}

has_saved_networks() {
    [ -f "${WPA_CONF}" ] && grep -q "ssid=" "${WPA_CONF}" 2>/dev/null
}

main() {
    log "WiFi Manager starting..."
    
    # Initial delay to let system settle
    sleep 5
    
    while true; do
        # Check for forced AP mode
        if check_force_ap_mode; then
            log "Force AP mode requested"
            start_ap_mode
            sleep 120
            continue
        fi
        
        if check_wifi_connected; then
            if check_internet; then
                log "Connected with internet access"
                sleep 30
                continue
            fi
        fi
        
        log "No connection detected"
        
        if has_saved_networks; then
            log "Trying saved networks..."
            if start_client_mode; then
                continue
            fi
        fi
        
        log "Starting AP for configuration..."
        start_ap_mode
        
        # Stay in AP mode for 2 minutes before checking again
        sleep 120
    done
}

case "${1:-}" in
    start-ap) start_ap_mode ;;
    start-client) start_client_mode ;;
    status) check_wifi_connected && echo "Connected: $(wpa_cli -i ${WIFI_INTERFACE} status | grep ^ssid= | cut -d= -f2)" || echo "Not connected" ;;
    *) main ;;
esac
EOF
