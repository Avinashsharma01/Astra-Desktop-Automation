<div align="center">

# ✨ Astra Desktop Automation

### Your private, offline voice command center for Linux

<p>
  <img src="https://img.shields.io/badge/Status-Active-22c55e?style=for-the-badge" alt="Active">
  <img src="https://img.shields.io/badge/Platform-Ubuntu%20%7C%20GNOME-f97316?style=for-the-badge" alt="Ubuntu and GNOME">
  <img src="https://img.shields.io/badge/Python-3.10%2B-3776ab?style=for-the-badge&logo=python&logoColor=white" alt="Python 3.10 or newer">
  <img src="https://img.shields.io/badge/TTS-Piper%20Offline-8b5cf6?style=for-the-badge" alt="Piper offline TTS">
</p>
<p>
  <img src="https://img.shields.io/badge/Privacy-100%25%20Local-16a34a?style=flat-square" alt="100 percent local">
  <img src="https://img.shields.io/badge/License-MIT-2563eb?style=flat-square" alt="MIT License">
  <img src="https://img.shields.io/badge/Audio-mpv%20%2B%20PipeWire-06b6d4?style=flat-square" alt="mpv and PipeWire">
  <img src="https://img.shields.io/badge/Services-systemd%20user-f59e0b?style=flat-square" alt="systemd user services">
</p>

<p>
  <em>“Good afternoon, Avinash. Astra online. All systems are ready for your command.”</em>
</p>

</div>

> [!IMPORTANT]
> Astra is designed for a local Ubuntu/GNOME machine. It uses offline Piper speech synthesis, local system telemetry, and `systemd --user` services—no cloud account or API key is required.

**Astra** monitors hardware telemetry, power profiles, desktop settings, network interfaces, and developer workflows. It announces meaningful transitions and daily summaries in real time using high-quality offline neural speech synthesis.

<div align="center">

| 🛡️ Private | ⚡ Fast | 🎙️ Natural | 🧩 Modular |
|:---:|:---:|:---:|:---:|
| Local-only speech | SHA-256 audio cache | Piper neural voice | Four focused services |

</div>

---

## Table of Contents

- [Features](#features)
- [Architecture](#architecture)
- [System Requirements](#system-requirements)
- [Quick Start Installation](#quick-start-installation)
- [Manual Step-by-Step Installation](#manual-step-by-step-installation)
- [Configuration & Personalization](#configuration--personalization)
- [Command Line Usage](#command-line-usage)
- [Service Management](#service-management)
- [Event Ownership Matrix](#event-ownership-matrix)
- [Audio Pipeline & Caching](#audio-pipeline--caching)
- [Troubleshooting](#troubleshooting)
- [Uninstallation](#uninstallation)
- [Contributing](#contributing)
- [License](#license)
- [Privacy & Security](#privacy--security)

---

## Features

<div align="center">

| Area | What Astra does |
|:---|:---|
| 🌅 **Startup intelligence** | Announces the time-aware greeting, day, date, time, power, network, Bluetooth, and battery status |
| 🔋 **Hardware awareness** | Tracks charger, battery thresholds, CPU, RAM, temperature, disk space, USB, and suspend/resume |
| 🖥️ **Desktop awareness** | Tracks GNOME appearance, Night Light, power profiles, airplane mode, audio, displays, and brightness |
| 👨‍💻 **Developer awareness** | Tracks development servers, downloads, and build/test command outcomes |
| 🔒 **Privacy by design** | Synthesizes speech locally and stores generated audio in a local cache |

</div>

### 🎙️ 100% Offline Neural Speech
- Powered by [Piper TTS](https://github.com/rhasspy/piper) using local ONNX neural voice models.
- **Zero cloud telemetry, zero API keys, and zero external network calls** for audio synthesis.
- Ultra-low latency playback powered by `mpv` and PipeWire/PulseAudio.

### 🌅 Intelligent Startup Summary
- Greeting dynamically tailored to the time of day (`Good morning`, `Good afternoon`, `Good evening`, `Good night`).
- Announces the current local day, date, and time, for example: `Today is Sunday, October 11, 2026. The time is 12:50 PM.`
- Reads live system telemetry on login/boot:
  - Charger connection and current power supply status
  - Active power profile (`Performance`, `Balanced`, `Power-saver`)
  - Live battery percentage
  - Wi-Fi connection and signal readiness
  - Connected Bluetooth devices count

### ⚡ Instant Desktop & Power Mode Monitoring
- Real-time **D-Bus signal monitoring** for `net.hadess.PowerProfiles` (`performance`, `balanced`, `power-saver`) with sub-millisecond reaction time.
- GNOME Dark / Light style transitions.
- Night Light toggles.
- Airplane mode and wireless radio block tracking.

### 🔋 Battery & Hardware Health
- Immediate announcement upon plugging or unplugging the charger.
- Battery threshold alerts (20% warning, 10% critical, and 100% full charge).
- High temperature, CPU load spikes, RAM exhaustion, and low disk space warnings.
- Screen lock and unlock detection.

### 💻 Developer Workflow & Build Notifier
- **`auto-run` tool**: Wrap any command (e.g. `auto-run npm run build` or `auto-run cargo test`) to get spoken feedback upon completion or failure.
- Background detection of local development servers (`Vite`, `Next.js`, `Uvicorn`, `Flask`, etc.).
- Browser download completion tracking (`.crdownload`, `.part`).

### 🔒 Serialized Audio Playback
- Audio concurrency is synchronized via a cross-process POSIX file lock (`playback.lock`), guaranteeing that alerts never speak over each other.

---

## Architecture

Astra is split into four decoupled user services orchestrated via `systemd --user`. This multi-service architecture guarantees fault isolation and eliminates duplicate alerts.

### 🧠 Service Map

| Service | Role | Primary signals |
|:---|:---|:---|
| `automation-astra.service` | **Core & startup** | Greeting, date/time, system summary, USB |
| `event-voice.service` | **Hardware & health** | Charger, battery, Wi-Fi, Bluetooth, CPU, RAM, temperature, disk |
| `desktop-events.service` | **Desktop settings** | Power profiles, theme, Night Light, airplane mode |
| `advanced-events.service` | **Deep awareness** | Audio, displays, Internet, downloads, dev servers |

> [!TIP]
> Every event category has one owner. This prevents the same state change from being announced by multiple services.

```mermaid
flowchart LR
    subgraph Inputs ["🧩 Linux Inputs"]
        direction TB
        DBus["⚡ D-Bus<br/>Power Profiles"]
        SysFS["🖥️ /sys & /proc<br/>Power · Fans · ACPI"]
        NM["🌐 NetworkManager<br/>Wi-Fi · Bluetooth"]
        Udev["🔌 Linux udev<br/>USB Hotplug"]
        Desktop["🎨 GNOME Session<br/>Theme · Night Light · Audio"]
    end

    subgraph Services ["🧠 Astra Services"]
        direction TB
        A["🌅 Astra Core<br/><small>automation-astra.service</small><br/><small>Greeting · Date/Time · USB</small>"]
        B["🔋 Hardware & Health<br/><small>event-voice.service</small><br/><small>Power · Battery · Network · Warnings</small>"]
        C["⚙️ Desktop Settings<br/><small>desktop-events.service</small><br/><small>Profiles · Theme · Night Light</small>"]
        D["🚀 Deep Awareness<br/><small>advanced-events.service</small><br/><small>Audio · Displays · Downloads · Dev Servers</small>"]
    end

    subgraph Audio ["🎙️ Offline Speech Pipeline"]
        direction TB
        Lock["🔒 playback.lock<br/><small>Cross-process audio lock</small>"]
        Cache["⚡ tts-cache/<br/><small>SHA-256 WAV cache</small>"]
        Piper["🗣️ Piper TTS<br/><small>en_US-amy-medium</small>"]
        Player["🔊 mpv<br/><small>PipeWire / ALSA output</small>"]
    end

    DBus --> C
    SysFS --> B
    NM --> B
    Udev --> A
    Desktop --> C
    Desktop --> D

    A --> Lock
    B --> Lock
    C --> Lock
    D --> Lock
    Lock --> Cache
    Cache --> Piper
    Piper --> Player

    classDef input fill:#172554,stroke:#60a5fa,color:#dbeafe,stroke-width:2px;
    classDef core fill:#3b0764,stroke:#c084fc,color:#f3e8ff,stroke-width:2px;
    classDef health fill:#052e16,stroke:#4ade80,color:#dcfce7,stroke-width:2px;
    classDef desktop fill:#431407,stroke:#fb923c,color:#ffedd5,stroke-width:2px;
    classDef advanced fill:#164e63,stroke:#22d3ee,color:#cffafe,stroke-width:2px;
    classDef audio fill:#4c0519,stroke:#fb7185,color:#ffe4e6,stroke-width:2px;

    class DBus,SysFS,NM,Udev,Desktop input;
    class A core;
    class B health;
    class C desktop;
    class D advanced;
    class Lock,Cache,Piper,Player audio;

    style Inputs fill:#0f172a,stroke:#3b82f6,stroke-width:2px,color:#bfdbfe;
    style Services fill:#111827,stroke:#a855f7,stroke-width:2px,color:#e9d5ff;
    style Audio fill:#1f0a13,stroke:#f43f5e,stroke-width:2px,color:#fecdd3;
```

---

## System Requirements

- **Operating System:** Ubuntu 22.04 LTS / 24.04 LTS, Debian 12+, or GNOME-based Linux distributions.
- **Init System:** `systemd` with user session support (`systemd --user`).
- **Python:** Python 3.10, 3.11, 3.12, 3.13, or 3.14.
- **Audio:** PipeWire or PulseAudio with `mpv` installed.

### System Packages

```bash
sudo apt-get update
sudo apt-get install -y \
  python3 python3-venv python3-pip \
  mpv curl rfkill network-manager bluez \
  power-profiles-daemon libasound2
```

---

## Quick Start Installation

You can install and activate Astra in one command using the included automated installer:

> [!NOTE]
> The installer configures the local Python environment, voice model, audio cache, and all four user services.

```bash
# 1. Clone the repository into ~/Automation
git clone https://github.com/your-username/Astra-Desktop-Automation.git ~/Automation
cd ~/Automation

# 2. Run the installer
chmod +x install.sh
./install.sh
```

The script will automatically:
1. Verify and install missing system dependencies via `apt-get`.
2. Provision a dedicated Python virtual environment (`piper-venv`).
3. Download the Piper neural ONNX voice model.
4. Pre-warm the voice cache for instant playback.
5. Install and enable the four `systemd --user` service units.

When installation is complete, log out and back in—or restart the user services—to hear the Astra startup briefing.

---

## Manual Step-by-Step Installation

If you prefer installing manually without running the install script:

### 1. Set Up the Virtual Environment

```bash
cd ~/Automation
python3 -m venv piper-venv
piper-venv/bin/pip install --upgrade pip
piper-venv/bin/pip install -r requirements.txt
```

### 2. Download the Neural Voice Model

Astra defaults to the expressive `en_US-amy-medium` Piper model:

```bash
mkdir -p ~/Automation/tts-models
cd ~/Automation/tts-models

curl -L -o en_US-amy-medium.onnx \
  "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/amy/medium/en_US-amy-medium.onnx"

curl -L -o en_US-amy-medium.onnx.json \
  "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/amy/medium/en_US-amy-medium.onnx.json"
```

### 3. Pre-warm the Audio Cache

Generate static audio files for instant, zero-latency system responses:

```bash
cd ~/Automation
chmod +x events.py scripts/*.py bin/*
~/Automation/piper-venv/bin/python ~/Automation/scripts/warm-voice-cache.py
```

### 4. Install and Enable Systemd Services

Copy the provided unit templates into your user systemd directory:

```bash
mkdir -p ~/.config/systemd/user
cp ~/Automation/systemd/*.service ~/.config/systemd/user/

# Reload systemd and enable all units
systemctl --user daemon-reload
systemctl --user enable --now \
  automation-astra.service \
  event-voice.service \
  desktop-events.service \
  advanced-events.service
```

---

## Configuration & Personalization

### Customizing the Assistant Greeting Name
By default, Astra addresses the user as `Avinash`. You can customize this by setting the `ASTRA_USER` environment variable in your `~/.bashrc` or `~/.profile`:

```bash
export ASTRA_USER="Commander"
```

To persist this inside the systemd service, edit `~/.config/systemd/user/automation-astra.service`:

```ini
[Service]
Environment="ASTRA_USER=Alex"
```

### Changing Voice Models
Astra is compatible with all Piper ONNX voice models.
1. Download any `.onnx` and `.onnx.json` model file from the [Piper Voice Library](https://github.com/rhasspy/piper/blob/master/VOICES.md).
2. Save both files inside `~/Automation/tts-models/`.
3. Update the `VOICE` constant in `events.py` and `scripts/*.py`:
   ```python
   VOICE = "en_GB-alan-medium"
   ```

### Tuning Thresholds
Limits can be adjusted directly in `events.py` and `scripts/event-voice.py`:

```python
BATTERY_WARNINGS = (20, 10)  # Battery percentage warnings
CPU_LIMIT = 85               # CPU threshold (%)
RAM_LIMIT = 85               # RAM threshold (%)
TEMP_LIMIT_C = 80            # Temperature threshold (°C)
DISK_LIMIT = 85              # Disk usage threshold (%)
```

---

## Command Line Usage

Astra includes rich CLI utilities for manual execution and scripts:

### Test the Startup Greeting
```bash
python3 ~/Automation/events.py --startup
```

### Speak an Ad-hoc Message
```bash
python3 ~/Automation/events.py --say "System update finished successfully."
```

### Build & Test Auto-Notifier (`auto-run`)
Run long builds, test suites, or scripts and have Astra announce the outcome:

```bash
~/Automation/bin/auto-run make build
~/Automation/bin/auto-run pytest
```

---

## Service Management

All Astra services run under your personal systemd user session:

```bash
# Check status of all monitors
systemctl --user status automation-astra.service event-voice.service desktop-events.service advanced-events.service --no-pager

# Restart all services
systemctl --user restart automation-astra.service event-voice.service desktop-events.service advanced-events.service

# Stop all services
systemctl --user stop automation-astra.service event-voice.service desktop-events.service advanced-events.service

# Follow live log stream
journalctl --user -f \
  -u automation-astra.service \
  -u event-voice.service \
  -u desktop-events.service \
  -u advanced-events.service
```

---

## Event Ownership Matrix

To prevent audio collisions and duplicated messages, events are strictly partitioned across the services:

| Event Category | Monitored Signals | Owning Service |
| :--- | :--- | :--- |
| **Startup Summary** | Time-of-day greeting, local day/date/time, charger, power mode, Wi-Fi, Bluetooth, Battery % | `automation-astra.service` |
| **USB Devices** | USB connect/disconnect via `pyudev` netlink | `automation-astra.service` |
| **Power Supply** | AC plug/unplug, battery thresholds (20%, 10%, 100%) | `event-voice.service` |
| **Network Interfaces** | Wi-Fi connect/disconnect (`nmcli monitor`), Bluetooth devices | `event-voice.service` |
| **System Health** | High CPU, high RAM, critical temp, low disk | `event-voice.service` |
| **Power Profiles** | Performance, Balanced, Power-saver via D-Bus | `desktop-events.service` |
| **Desktop Settings** | GNOME Dark/Light style, Night Light, Airplane mode | `desktop-events.service` |
| **Audio Subsystem** | Audio sink changes, microphone inputs, volume mute | `advanced-events.service` |
| **Display & Session** | Screen lock/unlock, external monitors, brightness | `advanced-events.service` |
| **Developer Tools** | Dev servers (`vite`, `next`, `flask`, etc.), completed downloads | `advanced-events.service` |

---

## Audio Pipeline & Caching

1. **Hash Verification:** Every phrase is hashed with SHA-256 (e.g. `e24c16c5...wav`).
2. **Instant Playback:** If the file exists in `tts-cache/`, Piper is skipped and audio plays instantly via `mpv`.
3. **On-the-fly Synthesis:** Dynamic phrases (e.g. dynamic battery percent or custom `--say` messages) are synthesized on the fly via Piper and added to the cache.
4. **Playback Lock:** An advisory `fcntl.flock` ensures sequential, interruption-free speech across all concurrent monitors.

### 🎧 Low-Latency Speech Flow

```text
Event detected
     ↓
Message fingerprinted with SHA-256
     ↓
Cached WAV found? ── Yes ──► Play immediately with mpv
     │
     No
     ↓
Generate locally with Piper → Save to tts-cache/ → Play with mpv
```

Static announcements are pre-generated by `scripts/warm-voice-cache.py`. Dynamic
messages—such as a device name, temperature, download name, or custom
`--say` text—are generated only when required.

---

## Troubleshooting

> [!WARNING]
> If multiple copies of the same script are running, announcements can overlap. Check the systemd services before launching a monitor manually.

### Performance Mode Changes Not Announcing
- Astra listens directly to `net.hadess.PowerProfiles` on the system D-Bus.
- Ensure `power-profiles-daemon` is running:
  ```bash
  systemctl status power-profiles-daemon
  ```
- Test setting a profile manually:
  ```bash
  powerprofilesctl set performance
  ```
- Check logs:
  ```bash
  journalctl --user -u desktop-events.service -n 50 --no-pager
  ```

### No Audio Output
- Verify that `mpv` can play files through your sound server:
  ```bash
  mpv --no-video ~/Automation/tts-cache/*.wav
  ```
- If PipeWire or PulseAudio is muted, inspect volume via `pactl info` and `pactl get-sink-mute @DEFAULT_SINK@`.

### USB Announcements Not Working
- Ensure `pyudev` is installed in the virtual environment:
  ```bash
  ~/Automation/piper-venv/bin/python -c "import pyudev; print('pyudev is installed')"
  ```

---

## Uninstallation

To cleanly stop, disable, and remove Astra systemd user services:

```bash
cd ~/Automation
chmod +x uninstall.sh
./uninstall.sh
```

---

## Contributing

Contributions from the open-source community are welcome!
1. Fork the repository.
2. Create a feature branch (`git checkout -b feature/new-monitor`).
3. Validate Python syntax:
   ```bash
   python3 -m py_compile events.py scripts/*.py
   ```
4. Commit your changes (`git commit -m 'Add support for new sensor'`).
5. Push to your branch and open a Pull Request.

---

## License

This project is licensed under the **MIT License** — see the [LICENSE](LICENSE) file for details.

## Privacy & Security

<div align="center">

| 🔐 Local speech | 🧱 No credentials | 📴 No cloud TTS |
|:---:|:---:|:---:|
| Piper runs on your machine | No API keys are required | Audio synthesis stays offline |

</div>

Astra reads local operating-system state through standard Linux utilities and
stores generated audio under `tts-cache/`. The advanced monitor performs a
small Internet reachability check so it can distinguish local network
availability from Internet availability. No passwords, tokens, or private
credentials are collected by the application.
