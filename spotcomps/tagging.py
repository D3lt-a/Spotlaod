"""
ID3 tagging utilities using mutagen.
"""
from __future__ import annotations
from pathlib import Path
from typing import Dict, Optional
import requests
from .utils import logger

# Try import mutagen
try:
    from mutagen.mp3 import MP3
    from mutagen.id3 import ID3, TIT2, TPE1, TALB, TDRC, APIC
    MUTAGEN_AVAILABLE = True
except Exception:
    MUTAGEN_AVAILABLE = False

def tag_mp3_file(path: Path, meta: Dict, album_art_url: Optional[str] = None):
    """Add ID3 tags to MP3 file. No-op if mutagen not installed or file missing."""
    if not MUTAGEN_AVAILABLE or not path.exists():
        return

    try:
        audio = MP3(path, ID3=ID3)
        audio.tags = ID3()

        if meta.get("title"):
            audio.tags.add(TIT2(encoding=3, text=meta["title"]))
        if meta.get("artists"):
            audio.tags.add(TPE1(encoding=3, text=", ".join(meta["artists"])))
        if meta.get("album"):
            audio.tags.add(TALB(encoding=3, text=meta["album"]))
        if meta.get("year"):
            audio.tags.add(TDRC(encoding=3, text=str(meta["year"])))

        if album_art_url:
            try:
                resp = requests.get(album_art_url, timeout=10)
                if resp.status_code == 200:
                    audio.tags.add(APIC(
                        encoding=3,
                        mime='image/jpeg',
                        type=3,
                        desc='Cover',
                        data=resp.content
                    ))
            except Exception:
                logger.debug("Failed to download album art for tagging")

        audio.save()
        logger.info(f"Tagged: {path.name}")
    except Exception as e:
        logger.error(f"Failed to tag MP3: {e}")