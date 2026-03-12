# RadioTape — Backlog

Future improvements beyond the MVP. Ordered roughly by value.

## High priority

- [ ] **Silence trimming** — Trim leading/trailing silence from each track after recording. Use numpy threshold detection (~-50 dBFS). Add `--no-trim` flag. Addresses the ~0.5s track boundary overlap from polling latency.

- [ ] **Pause handling** — When Music.app pauses, stop buffering silence. When it resumes, continue recording seamlessly. Currently pause periods are included in the recording as silence.

- [ ] **Album artwork via AppleScript** — Try `raw data of artwork 1 of current track` from Music.app before falling back to iTunes Search API. Higher resolution and always matches the correct album version.

- [ ] **Rich terminal UI** — Replace print statements with `rich` live display. Show current track, elapsed time, waveform/level meter, tracks recorded count. Show final summary as a table.

## Medium priority

- [ ] **Duplicate skip** — Skip recording if `{artist} - {title}.mp3` already exists in the output directory. Useful when re-recording an album after a failed session.

- [ ] **Format options** — `--format mp3|wav|flac` flag. WAV and FLAC for lossless output. Requires `soundfile` for FLAC (already a dependency).

- [ ] **Playlist generation** — Generate `.m3u` playlist file alongside MP3s for easy import into car stereo or media player.

- [ ] **Configurable sample rate** — `--sample-rate` flag. Currently hardcoded to 48000 Hz (matching BlackHole default). Some users may want 44100 Hz.

- [ ] **Normalize audio levels** — Optional `--normalize` flag to normalize track loudness (e.g. ReplayGain or simple peak normalization). Useful when recording tracks from different albums in one session.

## macOS App

- [ ] **Native macOS app** — Wrap RadioTape in a native macOS GUI (SwiftUI or PyQt). Goal: make it dead simple — no terminal, no BlackHole setup, no Audio MIDI Setup. One-click record.
  - **Tech options:**
    - **SwiftUI + Swift rewrite** — Native feel, App Store distribution possible, but full rewrite
    - **PyQt/PySide6** — Reuse existing Python code, bundle with py2app or PyInstaller
    - **Electron** — Web-based UI wrapping the Python CLI (heavier but fastest to build)
  - **Key UX improvements over CLI:**
    - Built-in virtual audio routing (no manual Multi-Output Device setup)
    - Use macOS 14.2+ `AudioHardwareCreateProcessTap` API for per-app capture (no BlackHole needed)
    - Show current track with artwork, waveform, recording status
    - Drag-and-drop output files to Finder/iTunes
    - Menu bar mode (record in background)
    - Auto-detect Music.app playback, start/stop recording automatically
  - **Distribution:** Direct download (DMG) or Mac App Store. Notarized with Apple Developer ID.


## Low priority

- [ ] **Genre tagging** — Fetch genre from iTunes Search API and add TCON ID3 frame.

- [ ] **Year tagging** — Fetch release year and add TDRC ID3 frame.

- [ ] **Lyrics embedding** — Fetch synced lyrics from Music.app or a lyrics API and embed as USLT/SYLT ID3 frames.

- [ ] **Auto-setup** — `radiotape setup --auto` that programmatically creates the Multi-Output Device via Core Audio APIs instead of requiring manual Audio MIDI Setup steps.

- [ ] **Watch mode** — `radiotape watch` that runs continuously in the background, recording any music that plays. Saves to a library structure. Daemon mode with launchd integration.

- [ ] **Per-app audio capture** — Use macOS 14.2+ `AudioHardwareCreateProcessTap` API for per-process audio capture instead of BlackHole. Would eliminate the need for a virtual audio device and Multi-Output Device setup. Requires PyObjC bindings.

- [ ] **Test suite** — Unit tests for monitor, recorder, encoder, tagger. Integration test that records a test tone and verifies the full pipeline.

- [ ] **Cross-fade detection** — Detect when Apple Music crossfades between tracks and handle the overlap gracefully instead of hard-cutting at the polling boundary.

## Won't do (by design)

- **DRM circumvention** — RadioTape must never decrypt, descramble, or bypass any protection measure. This is a fundamental design constraint, not a missing feature.
- **Downloading without playback** — The tool records what plays through the speakers. Downloading streams directly would require DRM interaction.
- **Windows/Linux support** — Depends on Music.app (macOS only) and Core Audio. Different tools exist for other platforms.
