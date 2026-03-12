"""Encoder — WAV to MP3 conversion via pydub/ffmpeg."""

import os

from pydub import AudioSegment


def encode_mp3(wav_path: str, mp3_path: str, bitrate: str = "320k") -> str:
    """Convert a WAV file to MP3. Returns the MP3 path."""
    os.makedirs(os.path.dirname(mp3_path), exist_ok=True)
    audio = AudioSegment.from_wav(wav_path)
    audio.export(mp3_path, format="mp3", bitrate=bitrate)
    return mp3_path
