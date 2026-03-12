"""AudioRecorder — records from a virtual audio device via sounddevice."""

import threading
from queue import Empty, Queue

import numpy as np
import sounddevice as sd
import soundfile as sf


class AudioRecorder:
    def __init__(self, device: str | int = "BlackHole 2ch", samplerate: int = 48000, channels: int = 2):
        self.device = device
        self.samplerate = samplerate
        self.channels = channels
        self._chunks: Queue[np.ndarray] = Queue()
        self._stream: sd.InputStream | None = None
        self._recording = False
        self._lock = threading.Lock()

    def start(self):
        self._recording = True
        self._stream = sd.InputStream(
            device=self.device,
            samplerate=self.samplerate,
            channels=self.channels,
            dtype="float32",
            callback=self._callback,
            blocksize=4096,
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

    def flush(self, filepath: str):
        """Drain all buffered chunks and write to a WAV file."""
        chunks = []
        while True:
            try:
                chunks.append(self._chunks.get_nowait())
            except Empty:
                break

        if not chunks:
            return False

        audio = np.concatenate(chunks, axis=0)

        # Skip if effectively silent (all below -60 dBFS)
        peak = np.max(np.abs(audio))
        if peak < 0.001:  # ~-60 dBFS
            return False

        sf.write(filepath, audio, self.samplerate)
        return True

    def reset(self):
        """Clear the chunk buffer for the next track."""
        while not self._chunks.empty():
            try:
                self._chunks.get_nowait()
            except Empty:
                break

    def find_device(self) -> int | None:
        """Find the BlackHole device index. Returns None if not found."""
        devices = sd.query_devices()
        for i, d in enumerate(devices):
            if isinstance(self.device, str) and self.device.lower() in d["name"].lower():
                if d["max_input_channels"] >= self.channels:
                    return i
        return None
