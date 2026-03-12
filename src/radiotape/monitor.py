"""TrackMonitor — polls Music.app for current track metadata via JXA."""

import json
import subprocess
import threading
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
            JSON.stringify({
                state: "playing",
                name: t.name(),
                artist: t.artist(),
                album: t.album(),
                trackNumber: t.trackNumber(),
                duration: t.duration()
            });
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
    type: str  # "started", "changed", "paused", "resumed", "stopped", "error"
    track: TrackInfo = field(default_factory=TrackInfo)
    message: str = ""


class TrackMonitor:
    def __init__(self, event_queue: Queue, poll_interval: float = 1.0):
        self.event_queue = event_queue
        self.poll_interval = poll_interval
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

        if result.returncode != 0:
            return

        try:
            data = json.loads(result.stdout.strip())
        except (json.JSONDecodeError, ValueError):
            return

        state = data.get("state", "unknown")

        if state == "not_running" or state == "stopped":
            if self._last_state == "playing":
                self.event_queue.put(TrackEvent(type="stopped"))
            self._last_state = state
            return

        if state == "paused":
            if self._last_state == "playing":
                self.event_queue.put(TrackEvent(type="paused", track=self._last_track or TrackInfo()))
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

            if self._last_state == "paused" and self._last_track and track.key == self._last_track.key:
                self.event_queue.put(TrackEvent(type="resumed", track=track))
            elif self._last_track is None or track.key != self._last_track.key:
                event_type = "started" if self._last_track is None else "changed"
                self.event_queue.put(TrackEvent(type=event_type, track=track))

            self._last_track = track
            self._last_state = state
