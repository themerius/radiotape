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
    track_number: int = 0
    duration: float = 0.0

    @property
    def key(self) -> tuple:
        return (self.name, self.artist, self.album)


@dataclass
class TrackEvent:
    type: str  # "started", "changed", "position", "paused", "resumed", "stopped", "error"
    track: TrackInfo = field(default_factory=TrackInfo)
    message: str = ""
    # Audio frame at which this event was observed (poll-based, up to ~1s late).
    detect_frame: int | None = None
    # Estimated audio frame where the current track started, derived from
    # Music.app's playerPosition. None if unavailable.
    anchor_frame: int | None = None


# Ignore position readings whose Apple Event round trip took longer than this.
MAX_POSITION_SPAN = 0.15


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

    def _poll_once(self):
        result = subprocess.run(
            ["osascript", "-l", "JavaScript", "-e", JXA_SCRIPT],
            capture_output=True,
            text=True,
            timeout=5,
        )

        detect_frame = self.frame_at(time.time()) if self.frame_at else None

        if result.returncode != 0:
            return

        try:
            data = json.loads(result.stdout.strip())
        except (json.JSONDecodeError, ValueError):
            return

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
