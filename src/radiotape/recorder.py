"""AudioRecorder — records from a virtual audio device via sounddevice.

Audio is kept on a continuous timeline: every captured frame has an absolute
index (0 = first frame since start()). Callers cut tracks by frame index with
take()/discard_until(), so nothing recorded between two cuts is ever lost.
"""

import time
from queue import Empty, Queue

import numpy as np
import sounddevice as sd


class AudioRecorder:
    def __init__(
        self,
        device: str | int = "BlackHole 2ch",
        samplerate: int = 48000,
        channels: int = 2,
        blocksize: int = 4096,
    ):
        self.device = device
        self.samplerate = samplerate
        self.channels = channels
        self.blocksize = blocksize
        self._chunks: Queue[np.ndarray] = Queue()
        self._stream: sd.InputStream | None = None
        self._recording = False
        # (total frames captured, wall-clock time of that callback).
        # Assigned as one tuple so readers on other threads see a consistent pair.
        self._clock: tuple[int, float] = (0, 0.0)
        # Drained audio not yet taken: list of chunks starting at _buf_start.
        self._buf: list[np.ndarray] = []
        self._buf_start = 0
        self._buf_len = 0

    def start(self):
        self._recording = True
        self._stream = sd.InputStream(
            device=self.device,
            samplerate=self.samplerate,
            channels=self.channels,
            dtype="float32",
            callback=self._callback,
            blocksize=self.blocksize,
        )
        self._stream.start()

    def stop(self):
        self._recording = False
        if self._stream:
            self._stream.stop()
            self._stream.close()
            self._stream = None

    def _callback(self, indata: np.ndarray, frames: int, time_info, status):
        if status:
            pass  # occasional over/underflows are OK
        if self._recording:
            self._chunks.put(indata.copy())
            self._clock = (self._clock[0] + frames, time.time())

    # --- timeline -----------------------------------------------------------

    def frame_at(self, t: float) -> int:
        """Map a wall-clock time (time.time()) to an absolute frame index.

        Extrapolates from the most recent callback. Accurate to a few ms as
        long as no input overflow happened in between.
        """
        frames, t_cb = self._clock
        if t_cb == 0.0:
            return frames
        return frames + int(round((t - t_cb) * self.samplerate))

    def current_frame(self) -> int:
        return self.frame_at(time.time())

    @property
    def buffer_start(self) -> int:
        return self._buf_start

    def buffer_end(self) -> int:
        self._drain()
        return self._buf_start + self._buf_len

    def _drain(self, until_frame: int | None = None, timeout: float = 0.5):
        """Move queued chunks into the buffer, optionally waiting until
        `until_frame` has been captured (bounded by `timeout`)."""
        deadline = time.monotonic() + timeout
        while True:
            try:
                chunk = self._chunks.get_nowait()
                self._buf.append(chunk)
                self._buf_len += len(chunk)
                continue
            except Empty:
                pass
            if until_frame is None or self._buf_start + self._buf_len >= until_frame:
                return
            if not self._recording or time.monotonic() >= deadline:
                return
            time.sleep(0.01)

    def _consolidate(self) -> np.ndarray:
        if not self._buf:
            return np.zeros((0, self.channels), dtype=np.float32)
        if len(self._buf) > 1:
            self._buf = [np.concatenate(self._buf, axis=0)]
        return self._buf[0]

    def peek(self, start_frame: int, end_frame: int) -> np.ndarray:
        """Return a copy of audio in [start_frame, end_frame) (clamped)."""
        self._drain(until_frame=end_frame)
        audio = self._consolidate()
        lo = max(0, start_frame - self._buf_start)
        hi = max(lo, min(len(audio), end_frame - self._buf_start))
        return audio[lo:hi].copy()

    def take(self, end_frame: int) -> np.ndarray:
        """Remove and return all buffered audio before `end_frame`."""
        self._drain(until_frame=end_frame)
        audio = self._consolidate()
        cut = max(0, min(len(audio), end_frame - self._buf_start))
        head, rest = audio[:cut], audio[cut:]
        self._buf = [rest] if len(rest) else []
        self._buf_len = len(rest)
        self._buf_start += cut
        return head

    def discard_until(self, frame: int):
        """Drop buffered audio before `frame`."""
        self.take(frame)

    # --- devices ------------------------------------------------------------

    def find_device(self) -> int | None:
        """Find the BlackHole device index. Returns None if not found."""
        devices = sd.query_devices()
        for i, d in enumerate(devices):
            if isinstance(self.device, str) and self.device.lower() in d["name"].lower():
                if d["max_input_channels"] >= self.channels:
                    return i
        return None
