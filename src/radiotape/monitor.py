"""TrackMonitor — polls Music.app for current track metadata via JXA."""

import json
import subprocess
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from queue import Queue

JXA_SCRIPT = """
var Music = Application("Music");
if (!Music.running()) {
    JSON.stringify({state: "not_running"});
} else {
    var state = String(Music.playerState());
    if (state === "playing") {
        try {
            var t = Music.currentTrack();
            var info = {
                state: "playing",
                name: t.name(),
                artist: t.artist(),
                albumArtist: t.albumArtist(),
                album: t.album(),
                trackNumber: t.trackNumber(),
                duration: t.duration()
            };
            // Bracket the position query with wall-clock timestamps so the
            // caller can map it onto the audio timeline independent of
            // osascript startup time.
            try {
                var t0 = Date.now();
                var pos = Music.playerPosition();
                var t1 = Date.now();
                info.position = pos;
                info.positionTime = (t0 + t1) / 2000.0;
                info.positionSpan = (t1 - t0) / 1000.0;
            } catch (e2) {}
            JSON.stringify(info);
        } catch(e) {
            JSON.stringify({state: "playing", error: String(e)});
        }
    } else {
        JSON.stringify({state: state});
    }
}
"""


@dataclass
class TrackInfo:
    name: str = ""
    artist: str = ""
    album: str = ""
    album_artist: str = ""
    track_number: int = 0
    duration: float = 0.0

    @property
    def key(self) -> tuple:
        return (self.name, self.artist, self.album)

    @property
    def folder_artist(self) -> str:
        """Album artist if set (keeps albums with featured artists together),
        otherwise the track artist."""
        return self.album_artist.strip() or self.artist


@dataclass
class TrackEvent:
    type: str  # "started", "changed", "position", "paused", "resumed", "stopped", "error", "info"
    track: TrackInfo = field(default_factory=TrackInfo)
    message: str = ""
    # Audio frame at which this event was observed (poll-based, up to ~1s late).
    detect_frame: int | None = None
    # Estimated audio frame where the current track started, derived from
    # Music.app's playerPosition. None if unavailable.
    anchor_frame: int | None = None


# Ignore position readings whose Apple Event round trip took longer than this.
MAX_POSITION_SPAN = 0.15

# How long a single Music.app query may take before it is abandoned.
QUERY_TIMEOUT = 5

AUTOMATION_HINT = (
    "macOS needs permission for your terminal to control Music: answer the "
    "'… wants to control Music' dialog, or enable it under System Settings → "
    "Privacy & Security → Automation."
)


class MusicQueryError(Exception):
    """Music.app could not be queried (timeout, permission denied, …)."""


def query_music() -> dict:
    """Run the JXA query once and return the parsed result.

    Raises MusicQueryError with a short, human-readable reason on failure.
    """
    try:
        result = subprocess.run(
            ["osascript", "-l", "JavaScript", "-e", JXA_SCRIPT],
            capture_output=True,
            text=True,
            timeout=QUERY_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        raise MusicQueryError(
            f"Music.app did not respond within {QUERY_TIMEOUT}s. If this is the first run "
            f"on this Mac, {AUTOMATION_HINT}"
        ) from None

    if result.returncode != 0:
        err = result.stderr.strip().splitlines()[-1] if result.stderr.strip() else f"exit code {result.returncode}"
        if "-1743" in err or "not authorized" in err.lower():
            raise MusicQueryError(f"Not allowed to control Music.app ({err}). {AUTOMATION_HINT}")
        raise MusicQueryError(f"Music.app query failed: {err}")

    try:
        return json.loads(result.stdout.strip())
    except (json.JSONDecodeError, ValueError):
        raise MusicQueryError(f"Unexpected reply from Music.app: {result.stdout.strip()[:200]!r}") from None


class TrackMonitor:
    def __init__(
        self,
        event_queue: Queue,
        poll_interval: float = 1.0,
        frame_at: Callable[[float], int] | None = None,
        samplerate: int = 48000,
    ):
        self.event_queue = event_queue
        self.poll_interval = poll_interval
        self.frame_at = frame_at
        self.samplerate = samplerate
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_track: TrackInfo | None = None
        self._last_state: str = ""
        self._failed_polls = 0
        self._last_error = ""

    def start(self):
        self._thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=3)

    def _poll_loop(self):
        while not self._stop_event.is_set():
            try:
                self._poll_once()
            except Exception as e:
                self.event_queue.put(TrackEvent(type="error", message=str(e)))
            self._stop_event.wait(self.poll_interval)

    def _report_failure(self, message: str):
        """Report a failed query once per distinct reason, not on every poll."""
        self._failed_polls += 1
        if message != self._last_error:
            self._last_error = message
            self.event_queue.put(TrackEvent(type="error", message=f"{message} Retrying…"))

    def _report_recovery(self):
        if self._failed_polls:
            self.event_queue.put(TrackEvent(
                type="info",
                message=f"Music.app is responding again (after {self._failed_polls} failed queries).",
            ))
        self._failed_polls = 0
        self._last_error = ""

    def _poll_once(self):
        try:
            data = query_music()
        except MusicQueryError as e:
            self._report_failure(str(e))
            return
        self._report_recovery()

        detect_frame = self.frame_at(time.time()) if self.frame_at else None

        state = data.get("state", "unknown")

        if state == "not_running" or state == "stopped":
            if self._last_state == "playing":
                self.event_queue.put(TrackEvent(type="stopped", detect_frame=detect_frame))
            self._last_state = state
            return

        if state == "paused":
            if self._last_state == "playing":
                self.event_queue.put(TrackEvent(
                    type="paused", track=self._last_track or TrackInfo(), detect_frame=detect_frame,
                ))
            self._last_state = state
            return

        if state == "playing":
            if "error" in data:
                # Can't read track info (streaming-only track not in library)
                if self._last_state != "playing":
                    self.event_queue.put(TrackEvent(
                        type="error",
                        message=f"Can't read track info: {data['error']}. Try adding the album to your library first.",
                    ))
                self._last_state = state
                return

            track = TrackInfo(
                name=data.get("name", ""),
                artist=data.get("artist", ""),
                album=data.get("album", ""),
                album_artist=data.get("albumArtist", "") or "",
                track_number=data.get("trackNumber", 0),
                duration=data.get("duration", 0.0),
            )

            anchor_frame = self._anchor_frame(data)

            if self._last_state == "paused" and self._last_track and track.key == self._last_track.key:
                event_type = "resumed"
            elif self._last_track is None or track.key != self._last_track.key:
                event_type = "started" if self._last_track is None else "changed"
            else:
                event_type = "position"

            if event_type != "position" or anchor_frame is not None:
                self.event_queue.put(TrackEvent(
                    type=event_type, track=track, detect_frame=detect_frame, anchor_frame=anchor_frame,
                ))

            self._last_track = track
            self._last_state = state

    def _anchor_frame(self, data: dict) -> int | None:
        """Estimate the audio frame at which the current track started:
        frame(at query time) - playerPosition * samplerate."""
        if self.frame_at is None:
            return None
        pos = data.get("position")
        pos_time = data.get("positionTime")
        span = data.get("positionSpan", 0.0)
        if not isinstance(pos, (int, float)) or not isinstance(pos_time, (int, float)):
            return None
        if span > MAX_POSITION_SPAN:
            return None
        return self.frame_at(pos_time) - int(round(pos * self.samplerate))
