# RadioTape — Developer Guide

## What is this?

RadioTape is a Python CLI tool that records Apple Music playback via a virtual audio loopback device (BlackHole), automatically splits recordings per track, and exports tagged MP3 files. It does **not** circumvent DRM — it captures post-decryption audio output.

## Project structure

```
src/radiotape/
├── cli.py          # click CLI entry points: setup, devices, record
├── recorder.py     # AudioRecorder — sounddevice InputStream → numpy → WAV
├── monitor.py      # TrackMonitor — polls Music.app via JXA (osascript)
├── orchestrator.py # RecordingSession — wires monitor + recorder + encoder + tagger
├── encoder.py      # WAV → MP3 via pydub/ffmpeg
└── tagger.py       # ID3 tagging (mutagen) + iTunes Search API artwork
```

## Architecture

- **TrackMonitor** runs in a daemon thread, polling Music.app every ~1s via `osascript -l JavaScript`. Emits `TrackEvent` objects onto a `queue.Queue`.
- **AudioRecorder** runs a `sounddevice.InputStream` callback on a PortAudio thread, pushing numpy chunks to a queue. Never blocks in the callback.
- **Orchestrator** (main thread) consumes events from TrackMonitor. On track change: flushes recorder → writes WAV → encodes MP3 → tags → resets recorder.
- WAV is the intermediate format. MP3 encoding happens after recording, not in real-time.

### Threading model

```
Main Thread          Monitor Thread         Recorder Thread
    │                     │                      │
    │ start()             │                      │
    ├────────────────────►│ poll Music.app       │
    ├─────────────────────┼─────────────────────►│ sd.InputStream
    │                     │                      │ callback → queue
    │                     │ track changed!        │
    │                     │──► event_queue.put()  │
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
uv run radiotape setup      # check prerequisites
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
- The JXA scripting bridge takes ~37ms per call. Polling at 1s intervals means ~3.7% overhead.
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
