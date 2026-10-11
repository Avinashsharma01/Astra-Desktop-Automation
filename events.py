#!/usr/bin/env python3

import argparse
import hashlib
import os
import queue
import re
import shutil
import subprocess
import threading
import time
from pathlib import Path

import psutil # type: ignore

try:
    import pyudev # type: ignore
except ImportError:
    pyudev = None

BASE = Path.home() / "Automation"
CACHE = BASE / "tts-cache"
MODELS = BASE / "tts-models"
PIPER_PYTHON = BASE / "piper-venv/bin/python"
PLAYER = "/usr/bin/mpv"
VOICE = "en_US-amy-medium"
USER_NAME = os.environ.get("ASTRA_USER", "Avinash")

STATE_INTERVAL = 1
METRICS_INTERVAL = 30

BATTERY_WARNINGS = (20, 10)
CPU_LIMIT = 80
RAM_LIMIT = 80
TEMP_LIMIT_C = 75
DISK_LIMIT = 80

SPEECH_QUEUE = queue.Queue(maxsize=50)
WAKE_EVENT = threading.Event()
COOLDOWNS = {}
COOLDOWN_LOCK = threading.Lock()
READY_FILE = (
    Path(os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}"))
    / "automation-astra.ready"
)

MESSAGES = {
    "charger_connected": "Laptop charger connected. Let's get to work.",
    "charger_disconnected": "Charger disconnected. You are now on battery.",
    "wifi_connected": "Wi-Fi connected.",
    "wifi_disconnected": "Wi-Fi disconnected. Please check your connection.",
    "battery_20": "Battery is below twenty percent. Consider charging.",
    "battery_10": "Battery is critically low. Please connect your charger.",
    "battery_full": "Battery is fully charged.",
    "usb_connected": "USB device connected.",
    "usb_disconnected": "USB device disconnected.",
    "resumed": "Welcome back. Your laptop has resumed.",
    "cpu_high": "Warning. CPU usage is very high.",
    "ram_high": "Warning. Memory usage is very high.",
    "temperature_high": "Warning. Your laptop temperature is high.",
    "disk_high": "Warning. Your home disk is almost full.",
}


def announce(message, key=None, cooldown=0):
    if not message:
        return

    now = time.monotonic()
    if key and cooldown:
        with COOLDOWN_LOCK:
            if now - COOLDOWNS.get(key, -1e12) < cooldown:
                return
            COOLDOWNS[key] = now

    try:
        SPEECH_QUEUE.put_nowait(message)
    except queue.Full:
        print("Speech queue full; dropping announcement.", flush=True)


def generate_audio(message):
    CACHE.mkdir(parents=True, exist_ok=True)

    digest = hashlib.sha256(message.encode("utf-8")).hexdigest()
    audio = CACHE / f"{digest}.wav"

    if audio.is_file() and audio.stat().st_size > 44:
        return audio

    temp = CACHE / f".{digest}.{os.getpid()}.tmp.wav"
    command = [
        str(PIPER_PYTHON),
        "-m",
        "piper",
        "-m",
        VOICE,
        "--data-dir",
        str(MODELS),
        "-f",
        str(temp),
        "--",
        message,
    ]

    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=90,
            check=False,
        )

        if result.returncode != 0 or not temp.is_file():
            print(f"Piper error: {result.stderr[-1000:]}", flush=True)
            temp.unlink(missing_ok=True)
            return None

        os.replace(temp, audio)
        return audio

    except (OSError, subprocess.TimeoutExpired) as error:
        print(f"Speech generation error: {error}", flush=True)
        temp.unlink(missing_ok=True)
        return None


def play_audio(audio):
    import fcntl

    CACHE.mkdir(parents=True, exist_ok=True)
    lock_path = CACHE / "playback.lock"

    with lock_path.open("a") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        try:
            return subprocess.run(
                [PLAYER, "--no-video", "--really-quiet", str(audio)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=90,
                check=False,
            )
        finally:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


def speech_worker():
    while True:
        message = SPEECH_QUEUE.get()
        try:
            audio = generate_audio(message)
            if audio is None:
                continue
            play_audio(audio)
        except (OSError, subprocess.TimeoutExpired) as error:
            print(f"Playback error: {error}", flush=True)
        finally:
            SPEECH_QUEUE.task_done()


def read_command(args):
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=3, check=False)
        return result.stdout.strip() if result.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired):
        return None


def charger_state():
    found = False
    online = False

    for path in Path("/sys/class/power_supply").glob("*"):
        try:
            kind = (path / "type").read_text().strip()
            if kind in ("Mains", "USB", "USB_C", "USB_PD"):
                found = True
                online |= (path / "online").read_text().strip() == "1"
        except (OSError, ValueError):
            continue

    if found:
        return online

    try:
        battery = psutil.sensors_battery()
        return battery.power_plugged if battery else None
    except (AttributeError, OSError):
        return None


def power_profile():
    try:
        result = subprocess.run(
            ["powerprofilesctl", "get"],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        pass
    return None


def wifi_state():
    try:
        result = subprocess.run(
            ["nmcli", "-t", "-f", "TYPE,STATE", "device", "status"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )

        if result.returncode != 0:
            return None

        for line in result.stdout.splitlines():
            fields = line.split(":", 1)
            if len(fields) == 2 and fields[0] == "wifi":
                return fields[1] == "connected"

        return None
    except (OSError, subprocess.TimeoutExpired):
        return None


def bluetooth_devices():
    try:
        result = subprocess.run(
            ["bluetoothctl", "devices", "Connected"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )

        if result.returncode != 0:
            return None

        devices = {}
        for line in result.stdout.splitlines():
            parts = line.split(maxsplit=2)
            if len(parts) == 3 and parts[0] == "Device":
                devices[parts[1]] = parts[2]

        return devices
    except (OSError, subprocess.TimeoutExpired):
        return None


def check_battery():
    try:
        battery = psutil.sensors_battery()
    except (AttributeError, OSError):
        return

    if battery is None:
        return

    percent = battery.percent

    if battery.power_plugged:
        if percent >= 99.5:
            announce(MESSAGES["battery_full"], key="battery_full", cooldown=3600)
        return

    for level in BATTERY_WARNINGS:
        if percent <= level:
            announce(MESSAGES[f"battery_{level}"], key=f"battery_{level}", cooldown=3600)

    with COOLDOWN_LOCK:
        for level in BATTERY_WARNINGS:
            if percent > level + 5:
                COOLDOWNS.pop(f"battery_{level}", None)
        if percent < 95:
            COOLDOWNS.pop("battery_full", None)


def temperature_celsius():
    try:
        sensors = psutil.sensors_temperatures(fahrenheit=False)
    except (AttributeError, OSError):
        return None

    readings = []
    for entries in sensors.values():
        for entry in entries:
            value = entry.current
            if value is not None and 0 < value < 150:
                readings.append(value)

    return max(readings) if readings else None


def check_system_health():
    cpu = psutil.cpu_percent(interval=None)
    ram = psutil.virtual_memory().percent
    disk = psutil.disk_usage(str(Path.home())).percent
    temp = temperature_celsius()

    if cpu >= CPU_LIMIT:
        announce(MESSAGES["cpu_high"], key="cpu_high", cooldown=1800)

    if ram >= RAM_LIMIT:
        announce(MESSAGES["ram_high"], key="ram_high", cooldown=1800)

    if temp is not None and temp >= TEMP_LIMIT_C:
        announce(MESSAGES["temperature_high"], key="temperature_high", cooldown=1800)

    if disk >= DISK_LIMIT:
        announce(MESSAGES["disk_high"], key="disk_high", cooldown=21600)


def network_event_watcher():
    while True:
        process = None
        try:
            process = subprocess.Popen(
                ["nmcli", "monitor"],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                bufsize=1,
            )

            for line in process.stdout:
                if line.strip():
                    WAKE_EVENT.set()
        except (OSError, TypeError) as error:
            print(f"Network watcher: {error}", flush=True)
        finally:
            if process is not None:
                if process.poll() is None:
                    process.terminate()
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    process.kill()
        time.sleep(5)


def usb_event_watcher():
    if pyudev is None:
        print("pyudev unavailable; USB event monitoring disabled.", flush=True)
        return

    try:
        context = pyudev.Context()
        monitor = pyudev.Monitor.from_netlink(context)
        monitor.filter_by(subsystem="usb", device_type="usb_device")

        for device in iter(monitor.poll, None):
            action = device.action
            if action not in ("add", "remove"):
                continue

            props = device.properties
            vendor_id = props.get("ID_VENDOR_ID", "")
            if vendor_id.lower() == "1d6b":
                continue

            name = (
                props.get("ID_MODEL_FROM_DATABASE")
                or props.get("ID_MODEL")
                or props.get("PRODUCT")
                or "USB device"
            )
            name = re.sub(r"[_\s]+", " ", name).strip()
            name = name[:80] or "USB device"

            message = f"{name} connected." if action == "add" else f"{name} disconnected."
            announce(message, key=f"usb:{action}:{name}", cooldown=5)
    except Exception as error:
        print(f"USB event watcher stopped: {error}", flush=True)


def snapshot():
    return {
        "charger": charger_state(),
        "wifi": wifi_state(),
        "bluetooth": bluetooth_devices(),
    }


def battery_percent():
    try:
        battery = psutil.sensors_battery()
        if battery is None:
            return None
        return battery.percent
    except (AttributeError, OSError):
        return None


def startup_summary():
    charger = charger_state()
    power = power_profile()
    wifi = wifi_state()
    bluetooth = bluetooth_devices() or {}
    battery = battery_percent()

    now = time.localtime()
    hour = now.tm_hour
    if 5 <= hour < 12:
        greeting = "Good morning"
    elif 12 <= hour < 17:
        greeting = "Good afternoon"
    elif 17 <= hour < 22:
        greeting = "Good evening"
    else:
        greeting = "Good night"

    day_date = time.strftime("%A, %B %-d, %Y", now)
    current_time = time.strftime("%-I:%M %p", now)
    parts = [
        f"{greeting}, {USER_NAME}. Astra online.",
        f"Today is {day_date}. The time is {current_time}.",
    ]

    if charger is True:
        parts.append("Laptop charger connected.")
    elif charger is False:
        parts.append("Running on battery power.")
    else:
        parts.append("Power status unknown.")

    if power:
        parts.append(f"{power.capitalize()} power mode is active.")

    if wifi is True:
        parts.append("Wi-Fi is connected and ready.")
    elif wifi is False:
        parts.append("Wi-Fi is not connected.")
    else:
        parts.append("Wi-Fi status is unavailable.")

    if bluetooth:
        parts.append(f"{len(bluetooth)} Bluetooth device(s) ready.")
    else:
        parts.append("Bluetooth is idle.")

    if battery is not None:
        parts.append(f"Battery at {int(battery)+1} percent.")
    else:
        parts.append("Battery level unavailable.")

    parts.append("All systems are online and ready for your command.")
    return " ".join(parts)


def run_startup_greeting():
    message = startup_summary()
    audio = generate_audio(message)
    if audio is None:
        print("Startup greeting could not be generated.", flush=True)
        return
    play_audio(audio)


def mark_startup_ready():
    try:
        READY_FILE.touch()
    except OSError as error:
        print(f"Could not mark startup readiness: {error}", flush=True)


def parse_args():
    parser = argparse.ArgumentParser(description="Astra desktop automation and voice status announcements.")
    parser.add_argument("--startup", action="store_true", help="Speak a one-time startup summary when the machine boots or logs in.")
    parser.add_argument("--once", action="store_true", help="Run a single status check and exit.")
    parser.add_argument("--say", nargs="+", metavar="TEXT", help="Speak an ad hoc message and exit.")
    return parser.parse_args()


def main():
    args = parse_args()

    print("Ubuntu offline event automation (Astra Core) started.", flush=True)
    threading.Thread(target=speech_worker, daemon=True).start()
    READY_FILE.unlink(missing_ok=True)

    if args.say:
        message = " ".join(args.say)
        audio = generate_audio(message)
        if audio is not None:
            play_audio(audio)
        return

    if args.startup or args.once:
        run_startup_greeting()

    if args.once:
        return

    mark_startup_ready()
    print("Astra startup greeting complete. Core monitor ready; watching USB events.", flush=True)

    while True:
        try:
            usb_event_watcher()
            time.sleep(5)
        except KeyboardInterrupt:
            break
        except Exception as error:
            print(f"USB monitor encountered error: {error}", flush=True)
            time.sleep(5)


if __name__ == "__main__":
    main()
