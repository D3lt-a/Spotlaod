"""
Centralized application state with simple subscription hooks.

This is intentionally lightweight (no Qt signals) and safe to call from worker threads.
UI subscribers that need to update tkinter widgets should schedule via `root.after(...)`.
"""
from typing import Dict, Callable, List, Optional
from dataclasses import dataclass, field
import threading

@dataclass
class TrackInfo:
    id: str
    title: str
    artist: str = ""
    album: str = ""
    status: str = "idle"       # idle | queued | downloading | completed | failed
    progress: float = 0.0
    path: Optional[str] = None
    error: Optional[str] = None

class AppState:
    def __init__(self):
        self._lock = threading.RLock()
        self.playlists: List[Dict] = []
        self.tracks: Dict[str, TrackInfo] = {}
        self.queue: List[str] = []
        self.loading: bool = False

        # subscribers
        self._on_playlists: List[Callable[[], None]] = []
        self._on_tracks: List[Callable[[], None]] = []
        self._on_queue: List[Callable[[], None]] = []
        self._on_track_updated: List[Callable[[str], None]] = []

    # Subscription API
    def subscribe_playlists(self, cb: Callable[[], None]):
        with self._lock:
            self._on_playlists.append(cb)

    def subscribe_tracks(self, cb: Callable[[], None]):
        with self._lock:
            self._on_tracks.append(cb)

    def subscribe_queue(self, cb: Callable[[], None]):
        with self._lock:
            self._on_queue.append(cb)

    def subscribe_track_updated(self, cb: Callable[[str], None]):
        with self._lock:
            self._on_track_updated.append(cb)

    # Mutators
    def set_playlists(self, playlists: List[Dict]):
        with self._lock:
            self.playlists = playlists
        for cb in list(self._on_playlists):
            try:
                cb()
            except Exception:
                pass

    def set_tracks(self, tracks: Dict[str, TrackInfo]):
        with self._lock:
            self.tracks = tracks
        for cb in list(self._on_tracks):
            try:
                cb()
            except Exception:
                pass

    def add_track(self, t: TrackInfo):
        with self._lock:
            self.tracks[t.id] = t
        for cb in list(self._on_tracks):
            try:
                cb()
            except Exception:
                pass

    def update_track_status(self, track_id: str, status: Optional[str] = None, progress: Optional[float] = None, path: Optional[str] = None, error: Optional[str] = None):
        with self._lock:
            t = self.tracks.get(track_id)
            if not t:
                return
            if status is not None:
                t.status = status
            if progress is not None:
                t.progress = progress
            if path is not None:
                t.path = path
            if error is not None:
                t.error = error
        for cb in list(self._on_track_updated):
            try:
                cb(track_id)
            except Exception:
                pass
        for cb in list(self._on_tracks):
            try:
                cb()
            except Exception:
                pass

    def enqueue(self, track_id: str):
        with self._lock:
            if track_id not in self.queue:
                self.queue.append(track_id)
                # set queued status if track exists
                if track_id in self.tracks:
                    self.tracks[track_id].status = "queued"
        for cb in list(self._on_queue):
            try:
                cb()
            except Exception:
                pass

    def dequeue(self, track_id: str):
        with self._lock:
            if track_id in self.queue:
                self.queue.remove(track_id)
        for cb in list(self._on_queue):
            try:
                cb()
            except Exception:
                pass

    def clear_queue(self):
        with self._lock:
            self.queue = []
        for cb in list(self._on_queue):
            try:
                cb()
            except Exception:
                pass