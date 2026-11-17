"""Tagger — ID3 metadata tagging for MP3 files via mutagen."""

import json
import re
import time
import urllib.parse
import urllib.request

from mutagen.id3 import APIC, ID3, TALB, TIT2, TPE1, TPE2, TRCK
from mutagen.mp3 import MP3


def tag_mp3(
    mp3_path: str, name: str, artist: str, album: str, track_number: int = 0, album_artist: str = "",
):
    """Write ID3 tags to an MP3 file."""
    audio = MP3(mp3_path, ID3=ID3)

    try:
        audio.add_tags()
    except Exception:
        pass  # tags already exist

    audio.tags.add(TIT2(encoding=3, text=name))
    audio.tags.add(TPE1(encoding=3, text=artist))
    audio.tags.add(TALB(encoding=3, text=album))
    if album_artist:
        audio.tags.add(TPE2(encoding=3, text=album_artist))
    if track_number > 0:
        audio.tags.add(TRCK(encoding=3, text=str(track_number)))

    audio.save()


class ArtworkError(Exception):
    """Artwork lookup failed for a transient reason (network, timeout, HTTP error)."""


def fetch_artwork(name: str, artist: str, attempts: int = 2) -> bytes | None:
    """Fetch album artwork from iTunes Search API.

    Returns JPEG bytes, or None if the API has no artwork for this track.
    Raises ArtworkError if the lookup failed (after retrying), so callers can
    report it and try again later instead of treating it as "no artwork".
    """
    last_error: Exception | None = None
    for attempt in range(attempts):
        if attempt:
            time.sleep(1)
        try:
            query = urllib.parse.quote(f"{artist} {name}")
            url = f"https://itunes.apple.com/search?term={query}&media=music&limit=1"
            with urllib.request.urlopen(url, timeout=10) as resp:
                data = json.loads(resp.read())

            if data.get("resultCount", 0) == 0:
                return None

            artwork_url = data["results"][0].get("artworkUrl100", "")
            if not artwork_url:
                return None
            # Get higher resolution
            artwork_url = artwork_url.replace("100x100", "600x600")

            with urllib.request.urlopen(artwork_url, timeout=10) as resp:
                return resp.read()
        except Exception as e:
            last_error = e
    raise ArtworkError(f"{type(last_error).__name__}: {last_error}")


def embed_artwork(mp3_path: str, artwork_data: bytes):
    """Embed JPEG artwork into an MP3 file."""
    audio = MP3(mp3_path, ID3=ID3)
    audio.tags.add(APIC(
        encoding=3,
        mime="image/jpeg",
        type=3,  # front cover
        desc="Cover",
        data=artwork_data,
    ))
    audio.save()


def sanitize_filename(name: str) -> str:
    """Remove characters not safe for filenames."""
    name = re.sub(r'[<>:"/\\|?*]', "", name)
    name = name.strip(". ")
    return name or "Unknown"
