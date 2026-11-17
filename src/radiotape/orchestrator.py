"""Orchestrator — wires TrackMonitor + AudioRecorder together.

Track boundaries
----------------
Audio is recorded on one continuous timeline (see AudioRecorder). Each track
boundary is a frame index on that timeline; audio before it goes to the old
track, audio after it stays buffered for the new one.

split_mode="position" (default):
    Music.app reports playerPosition (seconds into the current track). At poll
    time we know which audio frame is being captured, so
        track_start = frame_now - playerPosition * samplerate
    pins the boundary independent of polling latency. We take the median over
    the first few polls of the new track, then snap to the nearest silence
    within a small window (the pattern also used by Spytify and striputary).

split_mode="poll" (legacy fallback):
    Cut where the track change was observed. Up to ~1s of the next track can
    end up in the previous file.
"""

import os
import statistics
import tempfile
import time
from dataclasses import dataclass, field
from queue import Empty, Queue

import numpy as np
import sounddevice as sd
import soundfile as sf

from .encoder import encode_mp3
from .monitor import TrackEvent, TrackInfo, TrackMonitor
from .recorder import AudioRecorder
from .tagger import embed_artwork, fetch_artwork, sanitize_filename, tag_mp3

# Number of playerPosition readings of the new track to collect before cutting.
SETTLE_READINGS = 3
# Search window (each side) for snapping a cut to silence.
SNAP_WINDOW_S = 0.15
# Block size and threshold for silence detection while snapping.
SNAP_BLOCK_S = 0.01
SNAP_SILENCE_RMS = 10 ** (-50 / 20)  # -50 dBFS
# Where the BlackHole / Multi-Output Device setup is documented.
SETUP_DOCS = "README.md → 'One-time audio setup' (https://github.com/themerius/radiotape#one-time-audio-setup)"
# While idle (nothing playing), keep only this much audio buffered.
IDLE_KEEP_S = 30


def _log(msg: str):
    """Print a message, clearing the status line first."""
    print(f"\r\033[K{msg}")


@dataclass
class PendingCut:
    """A detected track change whose exact boundary is not yet decided."""
    old_track: TrackInfo | None
    new_track: TrackInfo
    detect_frame: int
    anchors: list[int] = field(default_factory=list)


class RecordingSession:
    def __init__(
        self,
        output_dir: str,
        device: str,
        bitrate: str = "320k",
        artwork: bool = True,
        split_mode: str = "position",
        cut_offset_ms: float = 0.0,
        snap: bool = True,
    ):
        self.output_dir = output_dir
        self.bitrate = bitrate
        self.artwork = artwork
        self.split_mode = split_mode
        self.snap = snap
        self._event_queue: Queue[TrackEvent] = Queue()
        self._recorder = AudioRecorder(device=device)
        self._cut_offset = int(round(cut_offset_ms / 1000 * self._recorder.samplerate))
        self._monitor = TrackMonitor(
            self._event_queue,
            frame_at=self._recorder.frame_at,
            samplerate=self._recorder.samplerate,
        )
        self._current_track: TrackInfo | None = None
        self._track_start_time: float = 0
        self._pending: PendingCut | None = None
        self._warned_no_position = False
        self._recorded_tracks: list[dict] = []
        self._tmpdir = tempfile.mkdtemp(prefix="radiotape_")
        self._artwork_cache: dict[str, bytes | None] = {}

    def run(self):
        """Main recording loop. Blocks until Ctrl+C."""
        # Verify device exists
        device_idx = self._recorder.find_device()
        if device_idx is None:
            raise RuntimeError(
                f"Audio device '{self._recorder.device}' not found. "
                f"Run 'radiotape setup' to check prerequisites."
            )
        self._recorder.device = device_idx

        self._warn_if_output_not_routed()
        self._recorder.start()
        self._monitor.start()

        print(f"Output directory: {self.output_dir}")
        print(f"Split mode:       {self.split_mode}")
        print("Waiting for Music.app to play...")
        print("Press Ctrl+C to stop recording.\n")

        try:
            self._event_loop()
        except KeyboardInterrupt:
            print("\n\nStopping...")
            self._resolve_pending()
            self._finalize_current_track(self._recorder.current_frame())
        finally:
            self._monitor.stop()
            self._recorder.stop()
            self._cleanup_tmp()
            self._print_summary()

    def _warn_if_output_not_routed(self):
        """Warn if the system output doesn't look like it feeds BlackHole."""
        try:
            name = sd.query_devices(kind="output")["name"]
        except Exception:
            return
        if not any(k in name.lower() for k in ("multi", "blackhole", "aggregate")):
            print(f"Warning: system output is '{name}', which doesn't look like a "
                  f"Multi-Output Device.\n"
                  f"         Recordings will be silent unless audio is routed to BlackHole.\n"
                  f"         Setup guide: {SETUP_DOCS}\n"
                  f"         Check with:  radiotape setup\n")

    # --- event handling -------------------------------------------------------

    def _event_loop(self):
        while True:
            try:
                event = self._event_queue.get(timeout=1)
            except Empty:
                self._trim_idle_buffer()
                self._print_status()
                continue

            self._handle_event(event)
            self._print_status()

    def _handle_event(self, event: TrackEvent):
        if event.type in ("started", "changed"):
            # A previous change still settling (fast skipping): decide it now.
            self._resolve_pending()
            detect = event.detect_frame if event.detect_frame is not None else self._recorder.current_frame()
            old = self._current_track if event.type == "changed" else None

            self._current_track = event.track
            self._track_start_time = time.time()
            _log(f"  Recording: {event.track.artist} - {event.track.name}")

            if self.split_mode == "poll":
                self._cut(old, detect, snap=False)
            else:
                self._pending = PendingCut(old_track=old, new_track=event.track, detect_frame=detect)
                self._add_anchor(event)

        elif event.type == "position":
            self._add_anchor(event)

        elif event.type == "paused":
            # Position readings after a pause no longer map to the track start.
            self._resolve_pending()
            _log(f"  Paused: {event.track.name}")

        elif event.type == "resumed":
            _log(f"  Resumed: {event.track.name}")

        elif event.type == "stopped":
            self._resolve_pending()
            end = event.detect_frame if event.detect_frame is not None else self._recorder.current_frame()
            self._finalize_current_track(end)
            _log("  Music stopped. Waiting...")

        elif event.type == "error":
            _log(f"  Warning: {event.message}")

    def _add_anchor(self, event: TrackEvent):
        p = self._pending
        if p is None or event.anchor_frame is None or event.track.key != p.new_track.key:
            return
        p.anchors.append(event.anchor_frame)
        if len(p.anchors) >= SETTLE_READINGS:
            self._resolve_pending()

    def _resolve_pending(self):
        """Decide the boundary for a pending track change and cut there."""
        p = self._pending
        if p is None:
            return
        self._pending = None

        if p.anchors:
            boundary = int(statistics.median(p.anchors)) + self._cut_offset
            # The new track can't have started after we saw it playing.
            boundary = min(boundary, p.detect_frame)
            self._cut(p.old_track, boundary, snap=self.snap)
        else:
            if not self._warned_no_position:
                _log("  Warning: Music.app did not report playerPosition; "
                      "falling back to poll-based splitting.")
                self._warned_no_position = True
            self._cut(p.old_track, p.detect_frame, snap=False)

    def _cut(self, old_track: TrackInfo | None, boundary: int, snap: bool):
        """Split the timeline at `boundary`: save audio before it as `old_track`
        (or discard it if there is no old track)."""
        boundary = max(boundary, self._recorder.buffer_start)
        if snap:
            boundary = self._snap_to_silence(boundary)
        if old_track is None:
            self._recorder.discard_until(boundary)
        else:
            self._save_track(old_track, self._recorder.take(boundary))

    def _snap_to_silence(self, boundary: int) -> int:
        """Move `boundary` to the nearest silent block within ±SNAP_WINDOW_S.
        Keeps it unchanged if it is already silent or there is no silence."""
        sr = self._recorder.samplerate
        win = int(SNAP_WINDOW_S * sr)
        block = int(SNAP_BLOCK_S * sr)
        start = max(boundary - win, self._recorder.buffer_start)
        audio = self._recorder.peek(start, boundary + win)
        n_blocks = len(audio) // block
        if n_blocks == 0:
            return boundary

        blocks = audio[: n_blocks * block].reshape(n_blocks, block, -1)
        rms = np.sqrt(np.mean(blocks.astype(np.float64) ** 2, axis=(1, 2)))
        silent = np.flatnonzero(rms < SNAP_SILENCE_RMS)
        if len(silent) == 0:
            return boundary

        centers = start + silent * block + block // 2
        here = (boundary - start) // block
        if here in silent:
            return boundary
        return int(centers[np.argmin(np.abs(centers - boundary))])

    def _trim_idle_buffer(self):
        """While nothing is playing, don't let the buffer grow unbounded."""
        if self._current_track is None and self._pending is None:
            keep = IDLE_KEEP_S * self._recorder.samplerate
            self._recorder.discard_until(self._recorder.buffer_end() - keep)

    # --- output -----------------------------------------------------------------

    def _finalize_current_track(self, end_frame: int):
        """Save the current track's audio up to `end_frame`."""
        if self._current_track is None:
            return
        track = self._current_track
        self._current_track = None
        self._save_track(track, self._recorder.take(end_frame))

    def _save_track(self, track: TrackInfo, audio: np.ndarray):
        """Encode, tag and save one track's audio."""
        if len(audio) == 0:
            return
        # Skip if effectively silent (all below -60 dBFS)
        if np.max(np.abs(audio)) < 0.001:
            _log(f"  Skipped: {track.name} (no audio captured — is System Settings > Sound > "
                 f"Output set to the Multi-Output Device?)\n"
                 f"           Setup guide: {SETUP_DOCS}")
            return

        wav_path = os.path.join(self._tmpdir, "current.wav")
        sf.write(wav_path, audio, self._recorder.samplerate)

        # Build output path
        artist_dir = sanitize_filename(track.artist) or "Unknown Artist"
        album_dir = sanitize_filename(track.album) or "Unknown Album"
        track_num = f"{track.track_number:02d}" if track.track_number > 0 else "00"
        track_name = sanitize_filename(track.name) or "Unknown Track"
        filename = f"{track_num} - {track_name}.mp3"

        out_dir = os.path.join(self.output_dir, f"{artist_dir} - {album_dir}")
        mp3_path = os.path.join(out_dir, filename)

        # Encode WAV → MP3
        encode_mp3(wav_path, mp3_path, self.bitrate)

        # Tag
        tag_mp3(mp3_path, track.name, track.artist, track.album, track.track_number)

        # Artwork
        if self.artwork:
            cache_key = f"{track.artist}|{track.album}"
            if cache_key not in self._artwork_cache:
                self._artwork_cache[cache_key] = fetch_artwork(track.name, track.artist)
            art = self._artwork_cache[cache_key]
            if art:
                embed_artwork(mp3_path, art)

        duration = len(audio) / self._recorder.samplerate
        self._recorded_tracks.append({
            "name": track.name,
            "artist": track.artist,
            "album": track.album,
            "duration": duration,
            "path": mp3_path,
        })

        # Clean up temp WAV
        if os.path.exists(wav_path):
            os.remove(wav_path)

        _log(f"  Saved: {filename} ({duration:.1f}s)")

    def _print_status(self):
        if self._current_track:
            elapsed = time.time() - self._track_start_time
            mins, secs = divmod(int(elapsed), 60)
            try:
                cols = os.get_terminal_size().columns
            except OSError:
                cols = 80
            line = f"  Recording: {self._current_track.artist} - {self._current_track.name} [{mins}:{secs:02d}]"
            if len(line) > cols:
                line = line[: cols - 1]
            print(f"\r\033[K{line}", end="", flush=True)

    def _print_summary(self):
        print(f"\n{'='*50}")
        print(f"Recording session complete")
        print(f"{'='*50}")
        if not self._recorded_tracks:
            print("No tracks recorded.")
            return

        total_duration = sum(t["duration"] for t in self._recorded_tracks)
        mins, secs = divmod(int(total_duration), 60)
        print(f"Tracks recorded: {len(self._recorded_tracks)}")
        print(f"Total duration:  {mins}:{secs:02d}")
        print(f"Output:          {self.output_dir}")
        print()
        for i, t in enumerate(self._recorded_tracks, 1):
            d = int(t["duration"])
            print(f"  {i}. {t['artist']} - {t['name']} ({d // 60}:{d % 60:02d})")

    def _cleanup_tmp(self):
        try:
            for f in os.listdir(self._tmpdir):
                os.remove(os.path.join(self._tmpdir, f))
            os.rmdir(self._tmpdir)
        except OSError:
            pass
