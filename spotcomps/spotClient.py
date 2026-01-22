"""
Spotify client helper with resilient fetch and retries.
"""
from __future__ import annotations
from typing import Optional, Dict, Any
from .utils import logger, DEFAULTS, is_transient_network_error
import spotipy
from spotipy.oauth2 import SpotifyOAuth
import time

class SpotifyClient:
    def __init__(self, cfg: Dict):
        self.cfg = cfg
        self.sp: Optional[spotipy.Spotify] = None

    def ensure_client(self) -> bool:
        """Initialize spotipy.Spotify client from cfg. Returns True if created."""
        client_id = self.cfg.get("client_id", "")
        client_secret = self.cfg.get("client_secret", "")
        redirect_uri = self.cfg.get("redirect_uri", DEFAULTS["redirect_uri"])
        if not client_id or not client_secret:
            return False
        try:
            auth = SpotifyOAuth(client_id=client_id,
                                client_secret=client_secret,
                                redirect_uri=redirect_uri,
                                scope="playlist-read-private playlist-read-collaborative",
                                cache_path=self.cfg.get("cache_path"))
            self.sp = spotipy.Spotify(auth_manager=auth)
            return True
        except Exception as e:
            logger.exception("Failed to create Spotify client: %s", e)
            self.sp = None
            return False

    def fetch_user_playlists(self, limit: int = 50, max_retries: int = 4) -> list[Dict[str, Any]]:
        """Return list of playlist objects (may be empty). Raises on unrecoverable error."""
        if self.sp is None and not self.ensure_client():
            raise RuntimeError("Spotify client not available (configure credentials)")

        attempt = 0
        results = None
        while attempt < max_retries:
            try:
                results = self.sp.current_user_playlists(limit=limit)
                break
            except Exception as e:
                logger.warning("Error fetching playlists (attempt %d/%d): %s", attempt + 1, max_retries, e)
                if is_transient_network_error(e) and attempt + 1 < max_retries:
                    backoff = 1 + 2 ** attempt
                    time.sleep(backoff)
                    self.ensure_client()
                    attempt += 1
                    continue
                raise
        if results is None:
            raise RuntimeError("Failed to fetch playlists after retries")

        # Accumulate pages
        playlists = []
        while results:
            playlists.extend(results.get("items", []) or [])
            if results.get("next"):
                results = self.sp.next(results)
            else:
                break
        return playlists

    def fetch_playlist_items(self, playlist_id: str, max_retries: int = 4) -> list[Dict]:
        """Return track metadata dicts for a playlist with retries. Each entry is Spotify track object."""
        if self.sp is None and not self.ensure_client():
            raise RuntimeError("Spotify client not available (configure credentials)")

        attempt = 0
        results = None
        while attempt < max_retries:
            try:
                results = self.sp.playlist_items(playlist_id, fields="items.track,next", additional_types=["track"])
                break
            except Exception as e:
                logger.warning("Error fetching playlist items (attempt %d/%d): %s", attempt + 1, max_retries, e)
                if is_transient_network_error(e) and attempt + 1 < max_retries:
                    time.sleep(1 + 2 ** attempt)
                    self.ensure_client()
                    attempt += 1
                    continue
                raise
        if results is None:
            raise RuntimeError("Failed to fetch playlist items after retries")

        tracks = []
        while results:
            for it in results.get("items", []):
                t = it.get("track")
                if t:
                    tracks.append(t)
            if results.get("next"):
                results = self.sp.next(results)
            else:
                break
        return tracks