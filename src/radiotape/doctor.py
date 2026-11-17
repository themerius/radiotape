"""Doctor — read-only checks that everything needed for recording works.

Nothing here changes system settings. The only side effect: the Music.app check
may make macOS show its one-time "… wants to control Music" consent dialog.
"""

import shutil
from dataclasses import dataclass

import numpy as np
import sounddevice as sd

SETUP_DOCS = "README.md → 'One-time audio setup' (https://github.com/themerius/radiotape#one-time-audio-setup)"

OK, WARN, FAIL, SKIP = "ok", "warn", "fail", "skip"
SYMBOLS = {OK: "✔", WARN: "!", FAIL: "✘", SKIP: "–"}

# Peak below this counts as no signal (matches the recorder's silence threshold).
SILENCE_PEAK = 0.001  # ~-60 dBFS
SIGNAL_SECONDS = 1.5


@dataclass
class Check:
    name: str
    status: str
    detail: str
    fix: str = ""


def output_looks_routed(device_name: str) -> bool:
    """Heuristic: does this output device feed BlackHole?"""
    name = device_name.lower()
    return any(k in name for k in ("multi", "blackhole", "aggregate"))


def find_blackhole(device: str = "BlackHole 2ch", channels: int = 2) -> tuple[int, dict] | None:
    for i, d in enumerate(sd.query_devices()):
        if device.lower() in d["name"].lower() and d["max_input_channels"] >= channels:
            return i, d
    return None


def check_ffmpeg() -> Check:
    path = shutil.which("ffmpeg")
    if path:
        return Check("ffmpeg", OK, path)
    return Check("ffmpeg", FAIL, "not found", "brew install ffmpeg")


def check_blackhole(device: str, samplerate: int) -> Check:
    found = find_blackhole(device)
    if not found:
        return Check("BlackHole", FAIL, f"no input device matching '{device}'", "brew install blackhole-2ch")
    _, d = found
    rate = int(d["default_samplerate"])
    if rate != samplerate:
        return Check("BlackHole", WARN, f"{d['name']} runs at {rate} Hz, RadioTape records at {samplerate} Hz",
                     f"Set BlackHole to {samplerate} Hz in Audio MIDI Setup")
    return Check("BlackHole", OK, f"{d['name']} ({rate} Hz)")


def check_multi_output() -> Check:
    names = [d["name"] for d in sd.query_devices() if d["max_output_channels"] > 0]
    multi = [n for n in names if "multi" in n.lower() or "aggregate" in n.lower()]
    if multi:
        return Check("Multi-Output Device", OK, ", ".join(multi))
    return Check("Multi-Output Device", WARN, "none found (it may have a custom name)",
                 "Audio MIDI Setup → '+' → Create Multi-Output Device with BlackHole 2ch + your speakers")


def check_system_output() -> Check:
    try:
        name = sd.query_devices(kind="output")["name"]
    except Exception as e:
        return Check("System output", WARN, f"could not read default output ({e})")
    if output_looks_routed(name):
        return Check("System output", OK, name)
    return Check("System output", FAIL, f"'{name}' — audio does not reach BlackHole",
                 "System Settings → Sound → Output: select the Multi-Output Device")


def check_music_access() -> tuple[Check, dict | None]:
    from .monitor import MusicQueryError, query_music
    try:
        data = query_music()
    except MusicQueryError as e:
        return Check("Music.app access", FAIL, str(e)), None
    state = data.get("state", "unknown")
    if state == "playing" and data.get("name"):
        detail = f"OK — playing: {data.get('artist', '')} – {data['name']}"
    elif state == "playing" and data.get("error"):
        return Check("Music.app access", WARN, f"playing, but track info unreadable ({data['error']})",
                     "Add the album to your library (macOS Tahoe can't read streaming-only tracks)"), data
    else:
        detail = f"OK — player {state.replace('_', ' ')}"
    return Check("Music.app access", OK, detail), data


def check_signal(device: str, samplerate: int, music_playing: bool | None) -> Check:
    """music_playing: True/False from Music.app, or None if it could not be queried."""
    found = find_blackhole(device)
    if not found:
        return Check("Audio signal", SKIP, "no BlackHole device")
    idx, _ = found
    try:
        audio = sd.rec(int(SIGNAL_SECONDS * samplerate), samplerate=samplerate, channels=2,
                       dtype="float32", device=idx, blocking=True)
    except Exception as e:
        return Check("Audio signal", FAIL, f"could not record from BlackHole ({e})")
    peak = float(np.max(np.abs(audio))) if len(audio) else 0.0
    if peak >= SILENCE_PEAK:
        db = 20 * np.log10(peak)
        level = f"peak {db:.1f} dBFS over {SIGNAL_SECONDS:g}s"
        if db < -30:
            return Check("Audio signal", WARN, f"{level} — quite low",
                         "Turn up the volume in Music.app (it sets the recording level)")
        return Check("Audio signal", OK, level)
    if music_playing:
        return Check("Audio signal", FAIL, "Music.app is playing but BlackHole receives silence",
                     "Route the system output through the Multi-Output Device (see 'System output')")
    if music_playing is None:
        return Check("Audio signal", SKIP, "BlackHole is silent; can't tell whether Music.app is playing (no access)")
    return Check("Audio signal", SKIP, "nothing playing — start a song in Music.app and re-run to test the signal")


def run_checks(device: str = "BlackHole 2ch", samplerate: int = 48000) -> list[Check]:
    checks = [
        check_ffmpeg(),
        check_blackhole(device, samplerate),
        check_multi_output(),
        check_system_output(),
    ]
    music, data = check_music_access()
    checks.append(music)
    playing = None if data is None else data.get("state") == "playing"
    checks.append(check_signal(device, samplerate, music_playing=playing))
    return checks


def print_checks(checks: list[Check]) -> int:
    """Print results; return the number of failed checks."""
    width = max(len(c.name) for c in checks)
    for c in checks:
        print(f"  {SYMBOLS[c.status]} {c.name:<{width}}  {c.detail}")
        if c.fix and c.status in (WARN, FAIL):
            print(f"    {'':<{width}}  → {c.fix}")
    failed = sum(c.status == FAIL for c in checks)
    warned = sum(c.status == WARN for c in checks)
    print()
    if failed or warned:
        parts = [f"{failed} problem(s)" if failed else "", f"{warned} warning(s)" if warned else ""]
        print(f"{', '.join(p for p in parts if p)}. Setup guide: {SETUP_DOCS}")
    else:
        print("All checks passed. Ready to record: radiotape record")
    return failed
