"""Orchestrator — wires TrackMonitor + AudioRecorder together."""

import os
import tempfile
import time
from queue import Empty, Queue

from .encoder import encode_mp3
from .monitor import TrackEvent, TrackInfo, TrackMonitor
from .recorder import AudioRecorder
from .tagger import embed_artwork, fetch_artwork, sanitize_filename, tag_mp3


class RecordingSession:
    def __init__(self, output_dir: str, device: str, bitrate: str = "320k", artwork: bool = True):
        self.output_dir = output_dir
        self.bitrate = bitrate
        self.artwork = artwork
        self._event_queue: Queue[TrackEvent] = Queue()
        self._monitor = TrackMonitor(self._event_queue)
        self._recorder = AudioRecorder(device=device)
        self._current_track: TrackInfo | None = None
        self._track_start_time: float = 0
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

        self._recorder.start()
        self._monitor.start()

        print(f"Output directory: {self.output_dir}")
        print("Waiting for Music.app to play...")
        print("Press Ctrl+C to stop recording.\n")

        try:
            self._event_loop()
        except KeyboardInterrupt:
            print("\n\nStopping...")
            self._finalize_current_track()
        finally:
            self._monitor.stop()
            self._recorder.stop()
            self._cleanup_tmp()
            self._print_summary()

    def _event_loop(self):
        while True:
            try:
                event = self._event_queue.get(timeout=1)
            except Empty:
                self._print_status()
                continue

            if event.type == "started" or event.type == "changed":
                if event.type == "changed":
                    self._finalize_current_track()

                self._current_track = event.track
                self._track_start_time = time.time()
                self._recorder.reset()
                print(f"  Recording: {event.track.artist} - {event.track.name}")

            elif event.type == "paused":
                print(f"  Paused: {event.track.name}")

            elif event.type == "resumed":
                print(f"  Resumed: {event.track.name}")

            elif event.type == "stopped":
                self._finalize_current_track()
                print("  Music stopped. Waiting...")

            elif event.type == "error":
                print(f"  Warning: {event.message}")

    def _finalize_current_track(self):
        """Flush the current recording to an MP3 file."""
        if self._current_track is None:
            return

        track = self._current_track
        self._current_track = None

        # Flush audio to temporary WAV
        wav_path = os.path.join(self._tmpdir, "current.wav")
        has_audio = self._recorder.flush(wav_path)

        if not has_audio:
            return

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

        duration = time.time() - self._track_start_time
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

        print(f"  Saved: {filename} ({duration:.0f}s)")

    def _print_status(self):
        if self._current_track:
            elapsed = time.time() - self._track_start_time
            mins, secs = divmod(int(elapsed), 60)
            print(f"\r  Recording: {self._current_track.artist} - {self._current_track.name} [{mins}:{secs:02d}]", end="", flush=True)

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
