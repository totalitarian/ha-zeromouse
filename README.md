# ZeroMouse - Home Assistant Integration

[![Version](https://img.shields.io/github/manifest-json/v/totalitarian/ha-zeromouse?filename=custom_components%2Fzeromouse%2Fmanifest.json&color=slateblue&label=Version&style=for-the-badge)](https://github.com/totalitarian/ha-zeromouse/releases)
![Downloads](https://img.shields.io/github/downloads/totalitarian/ha-zeromouse/total?label=Downloads&style=for-the-badge)
[![Validate](https://img.shields.io/github/actions/workflow/status/totalitarian/ha-zeromouse/hassfest.yaml?branch=main&label=Hassfest&style=for-the-badge)](https://github.com/totalitarian/ha-zeromouse/actions/workflows/hassfest.yaml)
[![HACS Validation](https://img.shields.io/github/actions/workflow/status/totalitarian/ha-zeromouse/hacs.yaml?branch=main&label=HACS&style=for-the-badge)](https://github.com/totalitarian/ha-zeromouse/actions/workflows/hacs.yaml)
[![HACS](https://img.shields.io/badge/HACS-Custom-orange.svg?logo=HomeAssistantCommunityStore&logoColor=white&style=for-the-badge)](https://github.com/hacs/integration)
[![Community Forum](https://img.shields.io/static/v1.svg?label=Community&message=Forum&color=41bdf5&logo=HomeAssistant&logoColor=white&style=for-the-badge)](https://community.home-assistant.io/)

![Logo](https://raw.githubusercontent.com/totalitarian/ha-zeromouse/main/brand/zeromouse_icon.svg)

Home Assistant integration for the [ZeroMouse Smart Cat Flap](https://www.zero-mouse.com). Monitors cat activity, detects prey, and controls flap settings — all from Home Assistant.

## Features

- **AI-powered detection** — classifies entries as clean, prey, inconclusive, or leaving
- **Live event GIFs** — animated previews of the most recent detection and last prey event
- **Remote controls** — block unknown cats, block prey, set inconclusive handling mode, adjust prey block duration
- **Device health** — Wi-Fi RSSI, firmware version, MQTT errors, PIR trigger count, boot count
- **Cloud-polled** — reads from the ZeroMouse cloud API (same backend as the official app)

## Installation

### Via [HACS](https://hacs.xyz/)

<a href="https://my.home-assistant.io/redirect/hacs_repository/?owner=totalitarian&repository=ha-zeromouse&category=integration" target="_blank"><img src="https://my.home-assistant.io/badges/hacs_repository.svg" alt="Open your Home Assistant instance and open a repository inside the Home Assistant Community Store." /></a>

### Manually

1. Download the [latest release](https://github.com/totalitarian/ha-zeromouse/releases)
2. Copy the `custom_components/zeromouse` folder into your Home Assistant `config/custom_components/`
3. Restart Home Assistant

## Configuration

<a href="https://my.home-assistant.io/redirect/config_flow_start/?domain=zeromouse" target="_blank"><img src="https://my.home-assistant.io/badges/config_flow_start.svg" alt="Open your Home Assistant instance and start setting up a new integration." /></a>

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

## Troubleshooting

### Integration fails to authenticate

- Verify you're using the same email and password as the ZeroMouse app
- Check that your ZeroMouse account is active

### Entities show as unavailable

- Check the device is online in the ZeroMouse app
- Review the Home Assistant logs for connection errors
- Try increasing the poll interval in options

## Contributing

Contributions are welcome! Please open an issue or pull request on [GitHub](https://github.com/totalitarian/ha-zeromouse).
