# RadioTape — Developer Guide

## What is this?

RadioTape is a Python CLI tool that records Apple Music playback via a virtual audio loopback device (BlackHole), automatically splits recordings per track, and exports tagged MP3 files. It does **not** circumvent DRM — it captures post-decryption audio output.

## Project structure

```
src/radiotape/
├── cli.py          # click CLI entry points: setup, doctor, devices, record
├── doctor.py       # read-only environment checks (shared by `doctor` and `setup`)
├── recorder.py     # AudioRecorder — sounddevice InputStream → numpy → WAV
├── monitor.py      # TrackMonitor — polls Music.app via JXA (osascript)
├── orchestrator.py # RecordingSession — wires monitor + recorder + encoder + tagger
├── encoder.py      # WAV → MP3 via pydub/ffmpeg
└── tagger.py       # ID3 tagging (mutagen) + iTunes Search API artwork
```

## Architecture

- **TrackMonitor** runs in a daemon thread, polling Music.app every ~1s via `osascript -l JavaScript`. Emits `TrackEvent` objects onto a `queue.Queue`.
- **AudioRecorder** runs a `sounddevice.InputStream` callback on a PortAudio thread, pushing numpy chunks to a queue. Never blocks in the callback. Audio lives on one continuous **frame timeline** (absolute frame index since start); `frame_at(wall_time)` maps a `time.time()` timestamp to a frame. Tracks are cut with `take(end_frame)` / `discard_until(frame)` — audio after a cut stays buffered, so nothing is lost while the main thread encodes.
- **Orchestrator** (main thread) consumes events from TrackMonitor. On track change: decides the boundary frame → `take()` old track audio → WAV → MP3 → tags.
- WAV is the intermediate format. MP3 encoding happens after recording, not in real-time.

### Track splitting (`--split-mode`)

- **`position` (default):** the JXA poll also returns `Music.playerPosition()`, bracketed by `Date.now()` timestamps inside the script (so osascript startup time doesn't matter). The monitor converts this into an *anchor*: `frame_at(query_time) - position * samplerate` = frame where the current track started. After a change, the orchestrator collects 3 anchors of the new track (~3s), takes the median, applies `--cut-offset-ms`, then snaps to the nearest silent 10ms block (< -50 dBFS) within ±150ms (`--no-snap` disables). Same idea as Spytify / striputary: rough event + exact timing info + quiet-point search.
- **`poll` (legacy fallback):** cut at the frame where the change was observed (0–1.2s late → up to ~1s of the next track bleeds into the previous file). Position mode also falls back to this automatically if Music.app reports no `playerPosition`.
- A pause resolves a pending cut immediately (anchors after a pause no longer point at the track start).

### Threading model

```
Main Thread          Monitor Thread         Recorder Thread
    │                     │                      │
    │ start()             │                      │
    ├────────────────────►│ poll Music.app       │
    ├─────────────────────┼─────────────────────►│ sd.InputStream
    │                     │                      │ callback → queue
    │                     │ track changed!       │
    │                     │──► event_queue.put() │
    │ ◄── event_queue.get()                      │
    │                     │                      │
    │ signal recorder: flush                     │
    │──────────────────────────────────────────► │ drain queue → WAV
    │                                            │
    │ encode(WAV → MP3)                          │
    │ tag(MP3, metadata)                         │
    │ save to disk                               │
    │                     │                      │
    │ signal recorder: new file                  │
    │──────────────────────────────────────────► │ reset buffer
    │                     │                      │
    Ctrl+C                │                      │
    │ flush last track    │                      │
    │ print summary       │                      │
    └─────────────────────┴──────────────────────┘
```

## Key commands

```bash
uv run radiotape setup      # run checks + print one-time setup instructions
uv run radiotape doctor      # run checks only (exit 1 on failure); play a song to test the signal
uv run radiotape devices     # list audio devices
uv run radiotape record      # start recording session
```

## Dependencies

- **Python:** sounddevice, numpy, soundfile, pydub, audioop-lts, mutagen, click
- **System:** BlackHole 2ch (`brew install blackhole-2ch`), ffmpeg (`brew install ffmpeg`)
- **audioop-lts** is required because Python 3.14 removed `audioop` from stdlib and pydub depends on it.

## Important technical notes

- BlackHole defaults to **48000 Hz** sample rate. The recorder uses 48kHz to match.
- macOS Tahoe may fail to read track metadata for streaming-only tracks (not added to library). The monitor logs a warning in this case.
- The JXA scripting bridge takes ~37ms per Apple Event, but each `osascript` invocation takes ~130–150ms wall time (process startup). Polling at 1s intervals.
- Album artwork is fetched from the iTunes Search API (free, no auth) and cached per album during a session.
- Silence detection threshold for skipping empty recordings: -60 dBFS (peak < 0.001 float32).

## Testing

No test suite yet. Smoke test with:

```bash
uv run python -c "
from radiotape.recorder import AudioRecorder
rec = AudioRecorder()
idx = rec.find_device()
print(f'BlackHole device: {idx}')
rec.device = idx
rec.start()
import time; time.sleep(1)
rec.stop()
print('OK')
"
```

## Backlog

See `BACKLOG.md` for future improvements.

## Legal context

This tool records post-decryption audio output (the "analog hole"). It does not interact with DRM. See the Legal section in `README.md` for full analysis with citations. Any new features should preserve this property — never add code that decrypts, descrambles, or bypasses any protection measure.
