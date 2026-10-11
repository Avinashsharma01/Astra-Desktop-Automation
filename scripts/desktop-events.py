#!/usr/bin/env python3
"""GNOME Desktop Settings Voice Automation."""

import fcntl
import hashlib
import os
import queue
import re
import subprocess
import threading
import time
from pathlib import Path

BASE = Path.home() / "Automation"
CACHE = BASE / "tts-cache"
MODELS = BASE / "tts-models"
PIPER = BASE / "piper-venv/bin/python"
PLAYER = "/usr/bin/mpv"
VOICE = "en_US-amy-medium"

CHECK_INTERVAL = 2
speech_queue = queue.Queue(maxsize=20)
COOLDOWNS = {}
COOLDOWN_LOCK = threading.Lock()

MESSAGES = {
    "dark_on": "Dark style enabled.",
    "dark_off": "Light style enabled.",
    "night_on": "Night Light enabled.",
    "night_off": "Night Light disabled.",
    "performance": "Performance power mode enabled.",
    "balanced": "Balanced power mode enabled.",
    "power-saver": "Power saver mode enabled.",
    "airplane_on": "Airplane mode may be enabled. Wireless radios are blocked.",
    "airplane_off": "Wireless radios are no longer all blocked.",
}


def read_command(args):
    try:
        result = subprocess.run(
            args, capture_output=True, text=True,
            timeout=3, check=False
        )
        return result.stdout.strip() if result.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired):
        return None


def get_state():
    color = read_command([
        "gsettings", "get",
        "org.gnome.desktop.interface", "color-scheme"
    ])
    night = read_command([
        "gsettings", "get",
        "org.gnome.settings-daemon.plugins.color",
        "night-light-enabled"
    ])
    power = read_command(["powerprofilesctl", "get"])
    rfkill = read_command(["rfkill", "list"])

    # Approximate radio-blocking state; not a definitive
    # GNOME Airplane Mode indicator.
    airplane = None
    if rfkill is not None:
        blocks = [
            line.split(":", 1)[1].strip().lower() == "yes"
            for line in rfkill.splitlines()
            if "soft blocked:" in line.lower()
        ]
        if blocks:
            airplane = all(blocks)

    return {
        "dark": (
            True if color == "'prefer-dark'"
            else False if color in ("'prefer-light'", "'default'")
            else None
        ),
        "night": (
            True if night == "true"
            else False if night == "false"
            else None
        ),
        "power": power,
        "airplane": airplane,
    }


def play_audio(audio):
    """Serialize audio playback across all automation services."""
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


def speak_worker():
    CACHE.mkdir(parents=True, exist_ok=True)

    while True:
        message = speech_queue.get()
        try:
            digest = hashlib.sha256(
                message.encode("utf-8")
            ).hexdigest()
            audio = CACHE / f"{digest}.wav"

            if not audio.is_file() or audio.stat().st_size <= 44:
                temp = CACHE / f".{digest}.{os.getpid()}.tmp.wav"
                result = subprocess.run(
                    [
                        str(PIPER), "-m", "piper",
                        "-m", VOICE,
                        "--data-dir", str(MODELS),
                        "-f", str(temp),
                        "--", message,
                    ],
                    capture_output=True, text=True,
                    timeout=90, check=False,
                )

                if result.returncode != 0 or not temp.is_file():
                    print(
                        f"Piper error: {result.stderr[-500:]}",
                        flush=True
                    )
                    temp.unlink(missing_ok=True)
                    continue

                os.replace(temp, audio)

            print(f"[DesktopEvents] Playing audio: {audio.name} ({message})", flush=True)
            play_audio(audio)
        except (OSError, subprocess.TimeoutExpired) as error:
            print(f"[DesktopEvents] Speech error: {error}", flush=True)
        finally:
            speech_queue.task_done()


def announce(message, key=None, cooldown=0):
    if not message:
        return

    now = time.monotonic()
    if key and cooldown:
        with COOLDOWN_LOCK:
            if now - COOLDOWNS.get(key, -1e12) < cooldown:
                print(f"[DesktopEvents] Cooldown active for key '{key}', skipping: {message}", flush=True)
                return
            COOLDOWNS[key] = now

    try:
        print(f"[DesktopEvents] Queued announcement: {message}", flush=True)
        speech_queue.put_nowait(message)
    except queue.Full:
        print("[DesktopEvents] Speech queue full; announcement skipped.", flush=True)


CURRENT_POWER = None
POWER_LOCK = threading.Lock()


def set_power_profile(new_profile, source="poll"):
    global CURRENT_POWER
    if not new_profile:
        return

    with POWER_LOCK:
        old_profile = CURRENT_POWER
        if old_profile == new_profile:
            return
        CURRENT_POWER = new_profile

    if old_profile is None:
        print(f"[DesktopEvents] Initial power profile detected ({source}): {new_profile}", flush=True)
        return

    print(f"[DesktopEvents] Power profile changed ({source}): {old_profile} -> {new_profile}", flush=True)
    if new_profile in MESSAGES:
        announce(
            MESSAGES[new_profile],
            key=f"desktop:power:{new_profile}",
            cooldown=1,
        )


def power_profile_dbus_listener():
    """Real-time listener for power profile changes via D-Bus PropertiesChanged signals."""
    while True:
        process = None
        try:
            process = subprocess.Popen(
                ["gdbus", "monitor", "--system", "--dest", "net.hadess.PowerProfiles"],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                bufsize=1,
            )
            for line in process.stdout:
                match = re.search(r"'ActiveProfile':\s*<['\"]([^'\"]+)['\"]>", line)
                if match:
                    new_profile = match.group(1).strip()
                    set_power_profile(new_profile, source="dbus-signal")
        except Exception as error:
            print(f"[DesktopEvents] Power D-Bus listener error: {error}", flush=True)
        finally:
            if process is not None:
                if process.poll() is None:
                    process.terminate()
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    process.kill()
        time.sleep(2)


def main():
    threading.Thread(target=speak_worker, daemon=True).start()
    previous = get_state()
    set_power_profile(previous.get("power"), source="startup")
    threading.Thread(target=power_profile_dbus_listener, daemon=True).start()
    print(f"[DesktopEvents] Desktop voice watcher started. Baseline: {previous}", flush=True)

    while True:
        time.sleep(CHECK_INTERVAL)
        current = get_state()

        if current["dark"] is not None and previous["dark"] is not None:
            if current["dark"] != previous["dark"]:
                announce(
                    MESSAGES["dark_on" if current["dark"] else "dark_off"],
                    key="desktop:dark",
                    cooldown=2,
                )

        if current["night"] is not None and previous["night"] is not None:
            if current["night"] != previous["night"]:
                announce(
                    MESSAGES["night_on" if current["night"] else "night_off"],
                    key="desktop:night",
                    cooldown=2,
                )

        if current["power"]:
            set_power_profile(current["power"], source="polling")

        if (
            current["airplane"] is not None
            and previous["airplane"] is not None
            and current["airplane"] != previous["airplane"]
        ):
            key = "airplane_on" if current["airplane"] else "airplane_off"
            announce(
                MESSAGES[key],
                key="desktop:airplane",
                cooldown=3,
            )

        for key in current:
            if current[key] is None:
                current[key] = previous[key]

        previous = current


if __name__ == "__main__":
    main()
