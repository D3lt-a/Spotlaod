"""
Downloader: yt-dlp worker queue and helpers.
Sends events to an event_queue (dict messages) about completed/failed downloads.
"""
from __future__ import annotations
from typing import Dict, Optional
from pathlib import Path
import threading
import queue
import yt_dlp
from .utils import logger, sanitize_filename, ensure_dir
from .tagging import tag_mp3_file

class Downloader:
    """
    Downloader manages a thread pool consuming tasks placed on its internal queue.
    Each task is a dict with keys: idx, meta, total.
    Sends events (dict) to event_queue with type: completed, download_error, video_unavailable, private_video, ffmpeg_missing, failed
    """
    def __init__(self, cfg: Dict, event_queue: "queue.Queue[Dict]"):
        self.cfg = cfg
        self.event_queue = event_queue
        self.task_queue: "queue.Queue[Optional[Dict]]" = queue.Queue()
        self.workers = []
        self._stop = threading.Event()
        self._start_workers()

    def _start_workers(self):
        concurrency = max(1, int(self.cfg.get("concurrency", 3)))
        for i in range(concurrency):
            t = threading.Thread(target=self._worker, name=f"dl-{i}", daemon=True)
            t.start()
            self.workers.append(t)

    def enqueue(self, task: Dict):
        self.task_queue.put(task)

    def _worker(self):
        while not self._stop.is_set():
            try:
                task = self.task_queue.get(timeout=0.5)
            except Exception:
                continue
            if task is None:
                break
            try:
                self._do_task(task)
            except Exception as e:
                logger.exception("Unhandled error in download task: %s", e)
                self.event_queue.put({"type": "failed", "meta": task.get("meta", {}), "error": str(e)})
            finally:
                self.task_queue.task_done()

    def _do_task(self, task: Dict):
        idx = task.get("idx")
        meta = task.get("meta", {})
        total = task.get("total", 0)

        artist = ", ".join(meta.get("artists", []))
        title = meta.get("title", "")
        album = meta.get("album", "")
        album_art_url = meta.get("album_art_url")
        year = meta.get("year")

        out_dir = Path(self.cfg.get("output_dir"))
        if self.cfg.get("organize_by_artist") and artist:
            out_dir = out_dir / sanitize_filename(artist)
        if self.cfg.get("organize_by_artist") and album:
            out_dir = out_dir / sanitize_filename(album)
        ensure_dir(out_dir)

        safe_name = sanitize_filename(f"{artist} - {title}")
        mp3_path = out_dir / f"{safe_name}.mp3"

        if mp3_path.exists() and self.cfg.get("skip_existing", True):
            logger.info("Skipping existing: %s", mp3_path)
            self.event_queue.put({"type": "completed", "idx": idx, "total": total, "meta": meta, "path": str(mp3_path)})
            return True

        query = f"{artist} {title} official audio"

        ytdlp_opts = {
            "format": f"bestaudio[abr<={self.cfg.get('audio_quality', '320')}]/bestaudio",
            "outtmpl": str(out_dir / (safe_name + ".%(ext)s")),
            "postprocessors": [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": self.cfg.get("audio_quality", "320")
            }],
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
        }

        # run download
        try:
            with yt_dlp.YoutubeDL(ytdlp_opts) as ydl:
                ydl.extract_info(f"ytsearch1:{query}", download=True)

            # locate mp3
            candidates = list(out_dir.glob(f"{safe_name}.*"))
            mp3_candidates = [p for p in candidates if p.suffix.lower() == ".mp3"]
            mp3_path_final = mp3_candidates[0] if mp3_candidates else (out_dir / f"{safe_name}.mp3")

            if mp3_path_final.exists() and self.cfg.get("add_metadata", True):
                tag_mp3_file(mp3_path_final, meta, album_art_url)

            self.event_queue.put({"type": "completed", "idx": idx, "total": total, "meta": meta, "path": str(mp3_path_final)})
            return True

        except yt_dlp.utils.DownloadError as e:
            error_msg = str(e).lower()
            if 'unavailable' in error_msg or 'not available' in error_msg:
                self.event_queue.put({"type": "video_unavailable", "idx": idx, "total": total, "meta": meta})
            elif 'private' in error_msg or 'deleted' in error_msg:
                self.event_queue.put({"type": "private_video", "idx": idx, "total": total, "meta": meta})
            else:
                self.event_queue.put({"type": "download_error", "idx": idx, "total": total, "meta": meta, "error": str(e)})
            return False
        except Exception as e:
            error_msg = str(e).lower()
            if 'ffmpeg' in error_msg:
                self.event_queue.put({"type": "ffmpeg_missing", "idx": idx, "total": total, "meta": meta, "error": error_msg})
            else:
                self.event_queue.put({"type": "failed", "idx": idx, "total": total, "meta": meta, "error": str(e)})
            return False

    def stop(self):
        self._stop.set()
        # drain queue by putting None per worker
        for _ in self.workers:
            self.task_queue.put(None)
        for w in self.workers:
            w.join(timeout=1)