#!/bin/bash
echo "Installing Auto-Hotspot Dependencies..."
sudo apt update
sudo apt install -y hostapd dnsmasq git

# Download the standard Raspberry Pi Auto-Hotspot script by RaspberryConnect
cd ~
git clone https://github.com/RaspberryConnect/AutoHotspot-Setup.git
cd AutoHotspot-Setup
sudo ./autohotspot-setup.sh

echo "Select 'Install AutoHotspot' from the menu, then configure your AP name."
echo "Once done, exit and reboot."