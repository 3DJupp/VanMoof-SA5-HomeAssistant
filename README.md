# VanMoof SA5 Home Assistant Integration

Home Assistant integration for the VanMoof S/A5 e-bike series. This custom integration exposes sensors, binary sensors and buttons for VanMoof S/A5 bikes so you can monitor bike state and interact with supported features from Home Assistant.

> **STATUS: BETA** — use at your own risk.

## Features

**Sensors**
- Battery and module battery, total distance, bike state (off / standby / on), lock state
- Region and speed limit, firmware version
- Firmware update entity: shows when the bike reports a newer firmware (install it with the VanMoof app)
- Error count with the error map reported by the bike as attributes

**Controls**
- Assist level (off, 1 to 4), light mode (on / off / auto), bell sound
- Alarm, brake light mode, indicator light mode, riding display, start-up animation theme
- Touch unlock (proximity unlock) with selectable distance

**Connection**
- Works with local Bluetooth adapters and ESPHome Bluetooth proxies through the Home Assistant Bluetooth stack
- Every command connects, authenticates, applies the change and reads the new state back

Not exposed on purpose: unlocking, changing the region (legal speed limit), the backup code and firmware flashing.

### Notes

- The bike does not report the touch unlock setting. Home Assistant remembers the last value you set.
- Protocol details: [docs/PROTOCOL.md](docs/PROTOCOL.md)
- Only SA5/A5 bikes are supported. The S6 uses a different Bluetooth service.

## Install via HACS

1. In Home Assistant, open **HACS**
2. Go to **Integrations** → three-dot menu → **Custom repositories**
3. Add: `https://github.com/TimTheBeastNL/VanMoof-SA5-HomeAssistant`
4. Category: **Integration**
5. Install and restart Home Assistant
6. Go to **Settings → Devices & Services → Add Integration** → search "VanMoof SA5"

## Requirements

- Home Assistant with Bluetooth support
- VanMoof S5 or A5 bike
- Recommended: ESP32-S3 as Bluetooth proxy near the bike for stable signal

## Special thanks

- [j-o-a-c-h-i](https://github.com/j-o-a-c-h-i)
- [Victor Lagerfors](https://github.com/victorlagerfors/vanmoof-s5-homey)
