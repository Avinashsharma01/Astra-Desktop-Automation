#!/usr/bin/env python3
"""Supplementary desktop and developer event monitor for Ubuntu/GNOME."""

import hashlib
import os
import queue
import subprocess
import sys
import threading
import time
from pathlib import Path

try:
    import psutil
except ImportError:
    psutil = None

BASE = Path.home() / "Automation"
CACHE = BASE / "tts-cache"
MODELS = BASE / "tts-models"
PIPER = BASE / "piper-venv/bin/python"
PLAYER = "/usr/bin/mpv"
VOICE = "en_US-amy-medium"
LOCK = CACHE / "playback.lock"

INTERVAL = 3
COOLDOWN = {}
COOLDOWN_LOCK = threading.Lock()
LAST = {}
FILE_TRACK = {}
ACTIVE_DOWNLOADS = {}
PROCESS_TRACK = {}

BATTERY_DRAIN_WARN = 12  # percentage points per hour while unplugged
LARGE_FILE_GB = 5
DOWNLOAD_EXTS = {".part", ".crdownload", ".tmp", ".download"}

DEV_PATTERNS = (
    "npm run dev", "npm start", "pnpm dev", "yarn dev",
    "vite", "next dev", "next start", "uvicorn", "gunicorn",
    "flask run", "django", "python -m http.server", "webpack serve"
)
DEV_TOOL_EXCLUSIONS = {
    "vim", "nvim", "nano", "code", "git", "grep", "cat", "less",
    "bash", "zsh", "sh", "systemctl", "journalctl", "find", "pip", "pip3"
}

SPEECH_QUEUE = queue.Queue(maxsize=30)
LAST_NET_CHECK = 0
LAST_INTERNET_RESULT = False


def command(args, timeout=2):
    try:
        p = subprocess.run(args, text=True, capture_output=True, timeout=timeout)
        return p.returncode, p.stdout.strip(), p.stderr.strip()
    except (OSError, subprocess.TimeoutExpired):
        return 127, "", ""


def play_audio(wav):
    command([
        "/usr/bin/flock", "-x", str(LOCK),
        PLAYER, "--no-video", "--really-quiet", str(wav)
    ], timeout=120)


def speech_worker():
    CACHE.mkdir(parents=True, exist_ok=True)
    while True:
        message = SPEECH_QUEUE.get()
        try:
            digest = hashlib.sha256(message.encode("utf-8")).hexdigest()
            wav = CACHE / f"{digest}.wav"
            if not wav.exists() or wav.stat().st_size <= 44:
                temp = CACHE / f".{digest}.{os.getpid()}.tmp.wav"
                rc, _, err = command([
                    str(PIPER), "-m", "piper", "-m", VOICE,
                    "--data-dir", str(MODELS), "-f", str(temp), "--", message
                ], timeout=45)
                if rc != 0 or not temp.exists() or temp.stat().st_size <= 44:
                    try:
                        temp.unlink(missing_ok=True)
                    except OSError:
                        pass
                    print(f"Piper failed: {err}", flush=True)
                    continue
                try:
                    temp.replace(wav)
                except OSError:
                    temp.unlink(missing_ok=True)
                    if not wav.exists():
                        continue
            play_audio(wav)
        except Exception as err:
            print(f"Speech worker error: {err}", flush=True)
        finally:
            SPEECH_QUEUE.task_done()


def say(message, key=None, cooldown=60):
    if not message:
        return
    now = time.monotonic()
    if key and cooldown:
        with COOLDOWN_LOCK:
            if now - COOLDOWN.get(key, -1e9) < cooldown:
                return
            COOLDOWN[key] = now
    try:
        SPEECH_QUEUE.put_nowait(message)
    except queue.Full:
        print("Speech queue full; dropping announcement.", flush=True)


def remember(key, value, message, cooldown=0):
    old = LAST.get(key, object())
    LAST[key] = value
    if old != value and message:
        say(message, key=f"change:{key}", cooldown=cooldown)


def read_int(path):
    try:
        return int(Path(path).read_text().strip())
    except (OSError, ValueError):
        return None


def battery_state():
    root = Path("/sys/class/power_supply")
    batteries = list(root.glob("BAT*"))
    if not batteries:
        return None
    b = batteries[0]
    capacity = read_int(b / "capacity")
    status = (b / "status").read_text().strip() if (b / "status").exists() else "Unknown"
    ac = False
    for p in list(root.glob("AC*")) + list(root.glob("ADP*")) + list(root.glob("USB*")):
        online = read_int(p / "online")
        if online == 1:
            ac = True
    return capacity, status, ac


def temperatures():
    vals = []
    for p in Path("/sys/class/thermal").glob("thermal_zone*/temp"):
        n = read_int(p)
        if n is not None:
            c = n / 1000 if n > 1000 else n
            if 0 < c < 130:
                vals.append(c)
    if not vals:
        rc, out, _ = command(["/usr/bin/sensors"], timeout=3)
        import re
        for m in re.finditer(r"([+-]?\d+(?:\.\d+)?)\s*°?C", out):
            c = float(m.group(1))
            if 0 < c < 130:
                vals.append(c)
    return max(vals) if vals else None


def fan_rpms():
    vals = []
    for p in Path("/sys/class/hwmon").glob("hwmon*/fan*_input"):
        n = read_int(p)
        if n is not None:
            vals.append(n)
    return vals


def network_state():
    global LAST_NET_CHECK, LAST_INTERNET_RESULT
    rc, out, _ = command(["/usr/bin/nmcli", "-t", "-f", "STATE", "general"], timeout=3)
    nm = out.lower()
    now = time.monotonic()
    if "connected" not in nm:
        internet = False
        LAST_INTERNET_RESULT = False
    elif now - LAST_NET_CHECK >= 30:
        rc2, _, _ = command(["/usr/bin/curl", "-Is", "--max-time", "3", "https://connectivitycheck.gstatic.com/generate_204"], timeout=4)
        internet = (rc2 == 0)
        LAST_NET_CHECK = now
        LAST_INTERNET_RESULT = internet
    else:
        internet = LAST_INTERNET_RESULT
    return nm, internet


def desktop_state():
    rc, out, _ = command([
        "/usr/bin/gdbus", "call", "--session", "--dest", "org.gnome.ScreenSaver",
        "--object-path", "/org/gnome/ScreenSaver", "--method",
        "org.gnome.ScreenSaver.GetActive"
    ])
    locked = ("true" in out.lower()) if rc == 0 else None
    return locked


def audio_state():
    rc, sinks, _ = command(["/usr/bin/pactl", "list", "short", "sinks"])
    rc2, sources, _ = command(["/usr/bin/pactl", "list", "short", "sources"])
    rc3, vol, _ = command(["/usr/bin/pactl", "get-sink-volume", "@DEFAULT_SINK@"])
    rc4, mute, _ = command(["/usr/bin/pactl", "get-sink-mute", "@DEFAULT_SINK@"])

    def names(s):
        return ",".join(line.split("\t")[1] for line in s.splitlines() if len(line.split("\t")) > 1)

    mute_clean = mute if mute.startswith("Mute:") else ""
    return (names(sinks), names(sources), vol, mute_clean)


def display_state():
    connected = []
    for p in Path("/sys/class/drm").glob("card*-*"):
        status = p / "status"
        if status.exists():
            try:
                if status.read_text().strip() == "connected":
                    connected.append(p.name)
            except OSError:
                pass
    brightness = []
    for p in Path("/sys/class/backlight").glob("*/"):
        cur, mx = read_int(p / "brightness"), read_int(p / "max_brightness")
        if cur is not None and mx:
            brightness.append(f"{p.name}:{round(cur * 100 / mx)}%")
    return tuple(sorted(connected)), tuple(sorted(brightness))


def init_downloads():
    folder = Path.home() / "Downloads"
    if not folder.exists():
        return
    now = time.monotonic()
    try:
        for p in folder.iterdir():
            if p.is_file():
                try:
                    st = p.stat()
                    sig = (st.st_size, st.st_mtime_ns)
                    FILE_TRACK[str(p)] = (sig, now, True)
                except OSError:
                    pass
    except OSError:
        pass


def watch_files():
    folder = Path.home() / "Downloads"
    if not folder.exists():
        return
    now = time.monotonic()
    seen = set()
    current_download_stems = set()

    try:
        for p in folder.iterdir():
            if not p.is_file() or p.name.startswith("."):
                continue

            # Track files actively being downloaded (.crdownload, .part, etc.)
            if p.suffix in DOWNLOAD_EXTS:
                stem = p.stem  # e.g. myfile.zip from myfile.zip.crdownload
                current_download_stems.add(stem)
                ACTIVE_DOWNLOADS[stem] = now
                continue

            seen.add(str(p))
            try:
                st = p.stat()
                sig = (st.st_size, st.st_mtime_ns)
                prev = FILE_TRACK.get(str(p))

                # If this file was an active browser download that just finished
                if p.name in ACTIVE_DOWNLOADS or p.stem in ACTIVE_DOWNLOADS:
                    ACTIVE_DOWNLOADS.pop(p.name, None)
                    ACTIVE_DOWNLOADS.pop(p.stem, None)
                    FILE_TRACK[str(p)] = (sig, now, True)
                    size = st.st_size / (1024**3)
                    if size >= LARGE_FILE_GB:
                        say(f"Large download complete: {p.name}, about {size:.1f} gigabytes.", key=f"file:{p.name}", cooldown=300)
                    else:
                        say(f"Download complete: {p.name}.", key=f"file:{p.name}", cooldown=180)
                    continue

                if prev is None:
                    # New file started copying / downloading
                    FILE_TRACK[str(p)] = (sig, now, False)
                elif prev[0] != sig:
                    # File is actively changing
                    FILE_TRACK[str(p)] = (sig, now, False)
                elif not prev[2] and now - prev[1] >= 10 and st.st_size > 0:
                    # File stopped changing for 10s -> completed
                    FILE_TRACK[str(p)] = (sig, prev[1], True)
                    size = st.st_size / (1024**3)
                    if size >= LARGE_FILE_GB:
                        say(f"Large download or copied file complete: {p.name}, about {size:.1f} gigabytes.", key=f"file:{p.name}", cooldown=300)
                    else:
                        say(f"Download or file copy appears complete: {p.name}.", key=f"file:{p.name}", cooldown=180)
            except OSError:
                pass
    except OSError:
        pass

    # Clean up stale active download records
    for stem in list(ACTIVE_DOWNLOADS):
        if stem not in current_download_stems and now - ACTIVE_DOWNLOADS[stem] > 3600:
            ACTIVE_DOWNLOADS.pop(stem, None)

    for key in list(FILE_TRACK):
        if key not in seen and now - FILE_TRACK[key][1] > 3600:
            FILE_TRACK.pop(key, None)


def scan_dev_processes():
    if psutil is None:
        return {}
    found = {}
    for proc in psutil.process_iter(["pid", "cmdline", "name"]):
        try:
            name = (proc.info.get("name") or "").lower()
            if name in DEV_TOOL_EXCLUSIONS:
                continue
            cmdline = proc.info.get("cmdline") or []
            cmd = " ".join(cmdline)
            if not cmd or "advanced-events.py" in cmd:
                continue
            cmd_lower = cmd.lower()
            if any(pattern in cmd_lower for pattern in DEV_PATTERNS):
                first_arg = Path(cmdline[0]).name.lower() if cmdline else ""
                if first_arg in DEV_TOOL_EXCLUSIONS:
                    continue
                found[proc.info["pid"]] = cmd[:120]
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue
    return found


def watch_dev_processes():
    if psutil is None:
        return
    current = scan_dev_processes()
    for pid in current.keys() - PROCESS_TRACK.keys():
        say("A development server process has started.", key="dev-server", cooldown=10)
        break
    for pid in PROCESS_TRACK.keys() - current.keys():
        say("A development server process has stopped.", key="dev-server-stop", cooldown=10)
        break
    PROCESS_TRACK.clear()
    PROCESS_TRACK.update(current)


def main():
    threading.Thread(target=speech_worker, daemon=True).start()

    # Pre-populate state so nothing is falsely announced on startup
    init_downloads()
    PROCESS_TRACK.update(scan_dev_processes())

    initial_lock = desktop_state()
    initial_battery = battery_state()
    initial = {
        "battery": initial_battery,
        "lock": initial_lock,
        "audio": audio_state(),
        "display": display_state(),
        "network": network_state(),
    }
    LAST.update(initial)

    if initial_battery:
        cap, _status, ac = initial_battery
        if cap is not None:
            LAST["battery-drain"] = (time.monotonic(), cap)

    print("Advanced offline desktop event monitor started.", flush=True)

    while True:
        try:
            b = battery_state()
            if b:
                cap, _status, ac = b
                old_battery = LAST.get("battery")
                old_ac = old_battery[2] if (old_battery and len(old_battery) > 2) else ac

                if old_ac != ac or "battery-drain" not in LAST:
                    LAST["battery-drain"] = (time.monotonic(), cap)
                elif cap is not None:
                    t0, c0 = LAST.get("battery-drain", (time.monotonic(), cap))
                    elapsed = time.monotonic() - t0
                    if elapsed >= 600:
                        drain = (c0 - cap) * 3600 / elapsed
                        if not ac and drain >= BATTERY_DRAIN_WARN:
                            say("Battery is draining faster than usual.", key="drain", cooldown=1800)
                        LAST["battery-drain"] = (time.monotonic(), cap)
                LAST["battery"] = b

            lock = desktop_state()
            if lock is not None:
                remember("lock", lock, "Screen locked." if lock else "Screen unlocked.", 5)

            audio = audio_state()
            if audio[0] or audio[1]:
                old = LAST.get("audio")
                if old and old[0] != audio[0]:
                    say("Audio output device changed.", key="audio-sink", cooldown=10)
                if old and old[1] != audio[1]:
                    say("Microphone or audio input device changed.", key="audio-source", cooldown=10)
                if old and audio[3] and old[3] != audio[3]:
                    say("Audio mute state changed.", key="audio-mute", cooldown=10)
                LAST["audio"] = audio

            disp = display_state()
            old_disp = LAST.get("display")
            if old_disp and old_disp[0] != disp[0]:
                say("Display or external monitor connection changed.", key="monitor", cooldown=10)
            if old_disp and old_disp[1] != disp[1]:
                say("Screen brightness changed.", key="brightness", cooldown=15)
            LAST["display"] = disp

            net = network_state()
            old_net = LAST.get("network")
            if old_net and old_net[1] != net[1]:
                say("Internet connection restored." if net[1] else "Internet connection appears unavailable.",
                    key="internet", cooldown=15)
            LAST["network"] = net

            fans = fan_rpms()
            temp = temperatures()
            if fans and all(x == 0 for x in fans) and temp is not None and temp >= 75:
                say("Warning. Temperature is high but fan speed reports zero.", key="fan-zero", cooldown=600)

            watch_dev_processes()
            watch_files()
            time.sleep(INTERVAL)
        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"Advanced event monitor error: {e}", file=sys.stderr, flush=True)
            time.sleep(INTERVAL)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--say":
        msg = " ".join(sys.argv[2:])
        digest = hashlib.sha256(msg.encode("utf-8")).hexdigest()
        wav = CACHE / f"{digest}.wav"
        if not wav.exists() or wav.stat().st_size <= 44:
            CACHE.mkdir(parents=True, exist_ok=True)
            temp = CACHE / f".{digest}.{os.getpid()}.tmp.wav"
            rc, _, err = command([
                str(PIPER), "-m", "piper", "-m", VOICE,
                "--data-dir", str(MODELS), "-f", str(temp), "--", msg
            ], timeout=45)
            if rc == 0 and temp.exists():
                temp.replace(wav)
            else:
                try:
                    temp.unlink(missing_ok=True)
                except OSError:
                    pass
        if wav.exists():
            play_audio(wav)
    else:
        main()
