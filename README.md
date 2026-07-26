# ZeroMouse - Home Assistant Integration

[![hacs_badge](https://img.shields.io/badge/HACS-Default-41BDF5.svg)](https://hacs.xyz/)
[![GitHub release](https://img.shields.io/github/v/release/totalitarian/ha-zeromouse)](https://github.com/totalitarian/ha-zeromouse/releases)

Home Assistant integration for the [ZeroMouse Smart Cat Flap](https://www.zero-mouse.com). Monitors cat activity, detects prey, and controls flap settings — all from Home Assistant.

## Features

- **AI-powered detection** — classifies entries as clean, prey, inconclusive, or leaving
- **Live event GIFs** — animated previews of the most recent detection and last prey event
- **Remote controls** — block unknown cats, block prey, set inconclusive handling mode, adjust prey block duration
- **Device health** — Wi-Fi RSSI, firmware version, MQTT errors, PIR trigger count, boot count
- **Cloud-polled** — reads from the ZeroMouse cloud API (same backend as the official app)

## Installation

### HACS (recommended)

1. Open HACS in Home Assistant
2. Go to **Integrations** -> **Three-dot menu** -> **Custom repositories**
3. Add `https://github.com/totalitarian/ha-zeromouse` as an **Integration**
4. Search for **ZeroMouse** and install
5. Restart Home Assistant

### Manual

1. Download the [latest release](https://github.com/totalitarian/ha-zeromouse/releases)
2. Copy the `custom_components/zeromouse` folder into your Home Assistant `config/custom_components/`
3. Restart Home Assistant

## Configuration

1. Go to **Settings** -> **Devices & Services** -> **Add Integration**
2. Search for **ZeroMouse**
3. Enter your ZeroMouse app login credentials (email and password)
4. The integration will attempt to discover your devices automatically
5. Select your device from the list, or enter the Owner ID and Device ID manually

### Options

After setup, configure via **Settings** -> **Devices & Services** -> **ZeroMouse** -> **Configure**:

| Option | Default | Description |
|--------|---------|-------------|
| **Poll interval** | 60 seconds | How often to fetch new events from the cloud |
| **Include exits** | On | Include "Leaving detected" events in the Last Event sensor/image |

## Entities

### Sensors

| Entity | Description |
|--------|-------------|
| **Last Event** | Classification of the most recent event (e.g. "No prey detected", "Prey detected") |
| **Last Event Time** | Timestamp of the most recent event (uses actual event time from the cloud) |
| **Event History** | Recent event summary |
| **Session Status** | Current session status |
| **Wi-Fi RSSI** | Device Wi-Fi signal strength |
| **Device Event Count** | Lifetime event count |
| **IR Sensor Status** | Raw proximity/IR sensor reading |
| **Firmware Version** | Current firmware version |
| **MQTT Error Count** | MQTT connection error count |
| **PIR Trigger Count** | Motion sensor trigger count |
| **AI Personalization Status** | AI training progress (0-100%) |
| **Feedback Score** | User feedback score (0-100%) |
| **Block Count** | Times the RFID mechanism blocked entry |
| **Unblock Count** | Times a normal entry occurred |
| **Boot Count** | Device reboot count |

### Binary Sensors

| Entity | Description |
|--------|-------------|
| **Connected** | Whether the device is currently connected |
| **Prey Detected** | Whether prey was detected in the last event |

### Switches

| Entity | Description |
|--------|-------------|
| **Block Unknown Cats** | Deny entry to cats not in your known-cat clusters |
| **Block Prey** | Deny entry to any cat detected carrying prey |

### Numbers

| Entity | Description |
|--------|-------------|
| **Prey Block Duration** | How long the flap stays blocked after prey detection (10-3600 seconds) |

### Selects

| Entity | Description |
|--------|-------------|
| **Inconclusive Handling Mode** | How to handle inconclusive events: Smart mode, Always allow, Always block |

### Images

| Entity | Description |
|--------|-------------|
| **Last Event** | GIF of the most recent detection event |
| **Last Prey Detected** | GIF of the most recent prey event |
| **Latest Detection** | Latest detection image |
| **Early** | Early classification image |
| **Entering Clean** | Clean entry image |
| **Inconclusive** | Inconclusive classification image |
| **Leaving** | Exit event image |
| **Undecidable** | Undecidable classification image |
| **Last Entry Not An Exit** | Last non-exit entry image |

## Troubleshooting

### Integration fails to authenticate

- Verify you're using the same email and password as the ZeroMouse app
- Check that your ZeroMouse account is active

### Entities show as unavailable

- Check the device is online in the ZeroMouse app
- Review the Home Assistant logs for connection errors
- Try increasing the poll interval in options

### Prey detection images not loading

- Prey images are backfilled once per Home Assistant restart
- If no prey events exist in the event history, the entity will remain unavailable until one occurs

## Contributing

Contributions are welcome! Please open an issue or pull request on [GitHub](https://github.com/totalitarian/ha-zeromouse).

## License

This project is licensed under the MIT License.
