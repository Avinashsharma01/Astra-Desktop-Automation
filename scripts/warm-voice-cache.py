#!/usr/bin/env python3
"""Pre-generates common voice announcements to warm up tts-cache."""

import hashlib
import subprocess
from pathlib import Path

base = Path.home() / "Automation"
cache = base / "tts-cache"
models = base / "tts-models"
python = base / "piper-venv/bin/python"

messages = [
    # Core charger, battery, network, resume, and health (event-voice.py)
    "Laptop charger connected. Let's get to work.",
    "Charger disconnected. You are now on battery.",
    "Wi-Fi connected.",
    "Wi-Fi disconnected. Please check your connection.",
    "Battery is below twenty percent. Consider charging.",
    "Battery is critically low. Please connect your charger.",
    "Battery is fully charged.",
    "Welcome back. Your laptop has resumed.",
    "Warning. CPU usage is very high.",
    "Warning. Memory usage is very high.",
    "Warning. Your laptop temperature is high.",
    "Warning. Your home disk is almost full.",

    # Desktop settings (desktop-events.py)
    "Dark style enabled.",
    "Light style enabled.",
    "Night Light enabled.",
    "Night Light disabled.",
    "Performance power mode enabled.",
    "Balanced power mode enabled.",
    "Power saver mode enabled.",
    "Airplane mode may be enabled. Wireless radios are blocked.",
    "Wireless radios are no longer all blocked.",

    # Advanced events (advanced-events.py)
    "Screen locked.",
    "Screen unlocked.",
    "Audio output device changed.",
    "Microphone or audio input device changed.",
    "Audio mute state changed.",
    "Display or external monitor connection changed.",
    "Screen brightness changed.",
    "Internet connection restored.",
    "Internet connection appears unavailable.",
    "Battery is draining faster than usual.",
    "Warning. Temperature is high but fan speed reports zero.",
    "A development server process has started.",
    "A development server process has stopped.",

    # Core USB (events.py)
    "USB device connected.",
    "USB device disconnected.",
]

cache.mkdir(parents=True, exist_ok=True)

for message in messages:
    digest = hashlib.sha256(message.encode("utf-8")).hexdigest()
    output = cache / f"{digest}.wav"

    if output.exists() and output.stat().st_size > 44:
        print("Cached:", message)
        continue

    temp = cache / f".{digest}.warm.wav"

    result = subprocess.run([
        str(python), "-m", "piper",
        "-m", "en_US-amy-medium",
        "--data-dir", str(models),
        "-f", str(temp),
        "--", message,
    ], capture_output=True, text=True)

    if result.returncode == 0 and temp.exists():
        temp.replace(output)
        print("Generated:", message)
    else:
        temp.unlink(missing_ok=True)
        print("FAILED:", message, result.stderr[-300:])

print("Voice cache warm-up complete.")
