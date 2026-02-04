"""
DownloadController: separates download orchestration from UI.

- Wraps the existing Downloader (which posts events to an event_queue).
- Runs a small listener thread that translates downloader events into AppState updates.
- Exposes safe APIs: enqueue(track_task), enqueue_batch, cancel_all.
"""
from typing import Dict, Any, List
import threading
import queue
import time

from .downloader import Downloader
from .app_state import AppState
from .modal_manager import ModalManager

class DownloadController:
    def __init__(self, cfg: Dict, state: AppState, modal: ModalManager):
        self.cfg = cfg
        self.state = state
        self.modal = modal

        # downloader posts events into this queue; Downloader expects an event_queue arg
        self._event_queue: "queue.Queue[Dict]" = queue.Queue()
        self._downloader = Downloader(self.cfg, self._event_queue)
        self._listener = threading.Thread(target=self._listen, daemon=True)
        self._stop = threading.Event()
        self._listener.start()
        self._current_progress_key = None

    def _listen(self):
        while not self._stop.is_set():
            try:
                ev = self._event_queue.get(timeout=0.5)
            except Exception:
                continue
            try:
                self._handle_event(ev)
            except Exception:
                # swallow to keep listener running
                pass
            finally:
                try:
                    self._event_queue.task_done()
                except Exception:
                    pass

    def _handle_event(self, ev: Dict):
        ttype = ev.get("type")
        idx = ev.get("idx")
        meta = ev.get("meta", {})
        track_id = str(meta.get("id") or idx or meta.get("uri") or meta.get("track_id") or f"track-{idx}")

        if ttype == "progress":
            perc = ev.get("progress", 0.0)
            self.state.update_track_status(track_id, status="downloading", progress=perc)
            # update modal if present
            if self._current_progress_key:
                self.modal.update(self._current_progress_key, value=int(perc * 100))
        elif ttype in ("completed",):
            path = ev.get("path")
            self.state.update_track_status(track_id, status="completed", progress=1.0, path=path)
            self.state.dequeue(track_id)
        elif ttype in ("download_error", "failed", "video_unavailable", "private_video", "ffmpeg_missing"):
            err = ev.get("error") or ev.get("reason") or ttype
            self.state.update_track_status(track_id, status="failed", error=err)
            self.state.dequeue(track_id)
        # add other mapping rules as needed

    def enqueue(self, task: Dict):
        """
        Task should be the dict Downloader expects (idx, meta, total).
        Also attempts to set track status to queued via AppState when possible.
        """
        meta = task.get("meta", {})
        track_id = str(meta.get("id") or task.get("idx"))
        self.state.enqueue(track_id)
        self._downloader.enqueue(task)

    def enqueue_batch(self, tasks: List[Dict]):
        for t in tasks:
            self.enqueue(t)

    def cancel_all(self):
        """
        Attempt to stop workers and clear queues.
        Note: ongoing yt-dlp calls may not abort immediately; this attempts a clean stop.
        """
        # stop listeners
        self._stop.set()
        try:
            # set downloader internal stop flag (best-effort)
            self._downloader._stop.set()
        except Exception:
            pass
        # flush pending tasks in downloader.task_queue
        try:
            while True:
                self._downloader.task_queue.get_nowait()
                self._downloader.task_queue.task_done()
        except Exception:
            pass
        # mark queued tracks as idle/failed
        with threading.RLock():
            for tid in list(self.state.queue):
                self.state.update_track_status(tid, status="failed", error="cancelled")
            self.state.clear_queue()

    def shutdown(self):
        self.cancel_all()