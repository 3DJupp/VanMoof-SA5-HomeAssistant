# VanMoof SA5 Home Assistant Integration

Home Assistant integration for the VanMoof S/A5 e-bike series. This custom integration exposes sensors, binary sensors and buttons for VanMoof S/A5 bikes so you can monitor bike state and interact with supported features from Home Assistant.

STATUS: BETA — use at your own risk. Functionality is still under development and the integration may change.

## Features

- Battery and range sensors
- Ride/state sensors and binary sensors
- Action buttons (where supported)
- BLE-based communication with the bike

## Install via HACS

1. In Home Assistant, open **HACS**.
2. Go to **Integrations** → click the three-dot menu (top right) → **Custom repositories**.
3. Add repository URL: `https://github.com/your-username/VanMoof-SA5-HomeAssistant` and set **Category** to **Integration**.
4. Install the integration from HACS and restart Home Assistant when prompted.
5. After restart, go to **Settings → Devices & Services → Add Integration** and search for "VanMoof SA5" to configure.

If you prefer manual installation: place the `vanmoof_sa5` folder under `custom_components/` and restart Home Assistant.

## Configuration

Follow the integration setup UI after adding the integration. Bluetooth access to the Home Assistant host is required for BLE pairing with the bike.

## Limitations & Beta Notes

- This integration is in beta and may have missing or unstable features.
- BLE reliability depends on your Home Assistant host hardware and environment.
- Use caution when interacting with bike controls — unintended actions could affect the bike.

## Support

Open issues or feature requests on the repository issue tracker.

## License

See `manifest.json` for license information.
