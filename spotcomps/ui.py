"""
GUI: SpotloadApp. Depends on utils, spotify_client and downloader modules.
Contains album-art caching, loading modal and bulk download UI.

Updates:
- Adds a generic `run_in_background` helper to show a loading modal for any
  background action, report exceptions to the user, and run an optional callback
  when the job completes. Replaces ad-hoc threading calls for playlist / track
  loading with this helper.
- Improves visible error reporting for download-related events (ffmpeg missing,
  download errors, unavailable/private videos) so the UI notifies the user.
"""
from __future__ import annotations
import threading
import queue
import time
from typing import Optional, Callable, Any
from pathlib import Path
from io import BytesIO

import tkinter as tk
from tkinter import messagebox, filedialog, ttk

try:
    import customtkinter as ctk
except Exception:
    ctk = None

from PIL import Image, ImageTk
from .utils import logger, load_config, save_config, load_history, save_history, sanitize_filename
from .spotClient import SpotifyClient
from .downloader import Downloader

class SpotloadApp(ctk.CTk if ctk else tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Spotload")
        self.geometry("980x640")

        self.cfg = load_config()
        self.history = load_history()

        self.sp_client = SpotifyClient(self.cfg)

        self.playlists = []
        self.current_playlist = None
        self.track_items = {}

        self.album_art_cache = {}
        self.album_art_img = None

        self.quality_var = tk.StringVar(value=self.cfg.get("audio_quality", "320"))
        self.metadata_var = tk.BooleanVar(value=self.cfg.get("add_metadata", True))
        self.organize_var = tk.BooleanVar(value=self.cfg.get("organize_by_artist", False))
        self.skip_existing_var = tk.BooleanVar(value=self.cfg.get("skip_existing", True))

        # event queue from downloader
        self.event_queue: "queue.Queue[dict]" = queue.Queue()
        self.downloader = Downloader(self.cfg, self.event_queue)

        # UI progress state
        self._dl_total = 0
        self._dl_done = 0
        self._download_progress_top: Optional[tk.Toplevel] = None
        self._loading_top: Optional[tk.Toplevel] = None
        self._loading_anim_handle = None
        self._loading_dots = 0
        self._loading_message_base = ""

        self._build_ui()
        self.after(200, self._poll_event_queue)

    # ---------------- UI construction -----------------
    def _build_ui(self):
        if ctk:
            self._build_ctk_ui()
        else:
            self._build_tk_ui()

    def _build_ctk_ui(self):
        nb = ctk.CTkTabview(self, width=960, height=600)
        nb.pack(padx=12, pady=12, fill="both", expand=True)

        main_frame = nb.add("Main")
        main_frame.grid_columnconfigure(0, weight=1)
        main_frame.grid_columnconfigure(1, weight=0)

        left = ctk.CTkFrame(main_frame)
        left.grid(row=0, column=0, sticky="nsew", padx=6, pady=6)
        right = ctk.CTkFrame(main_frame, width=320)
        right.grid(row=0, column=1, sticky="nsew", padx=6, pady=6)

        self.playlist_listbox = tk.Listbox(left, height=12)
        self.playlist_listbox.pack(fill="x", padx=6, pady=6)
        self.playlist_listbox.bind("<<ListboxSelect>>", lambda e: self._on_playlist_select())

        btn_frame = ctk.CTkFrame(left)
        btn_frame.pack(fill="x", padx=6, pady=6)
        ctk.CTkButton(btn_frame, text="Connect Spotify", command=self.connect_spotify).pack(side="left", padx=4)
        ctk.CTkButton(btn_frame, text="Load Playlists", command=lambda: self.run_in_background(self._load_playlists_task, message="Loading playlists...")).pack(side="left", padx=4)
        ctk.CTkButton(btn_frame, text="Download Playlist (Audio)", command=self.download_playlist_audio).pack(side="left", padx=4)
        ctk.CTkButton(btn_frame, text="Export M3U", command=self._export_playlist_m3u).pack(side="left", padx=4)

        self.track_listbox = tk.Listbox(left)
        self.track_listbox.pack(fill="both", expand=True, padx=6, pady=6)

        self.album_art_label = ctk.CTkLabel(right, text="No cover", width=250, height=250)
        self.album_art_label.pack(padx=6, pady=6)

        settings_frame = ctk.CTkFrame(right)
        settings_frame.pack(fill="x", padx=6, pady=6)
        ctk.CTkLabel(settings_frame, text="Audio Quality (kbps):").grid(row=0, column=0, sticky="w", pady=6, padx=6)
        quality_menu = ctk.CTkOptionMenu(settings_frame, variable=self.quality_var,
                                         values=["128", "192", "256", "320"])
        quality_menu.grid(row=0, column=1, sticky="w", pady=6, padx=6)

        ctk.CTkCheckBox(settings_frame, text="Add metadata tags", variable=self.metadata_var).grid(row=1, column=0, columnspan=2, sticky="w", padx=6, pady=4)
        ctk.CTkCheckBox(settings_frame, text="Organize by Artist/Playlist", variable=self.organize_var).grid(row=2, column=0, columnspan=2, sticky="w", padx=6, pady=4)
        ctk.CTkCheckBox(settings_frame, text="Skip existing files", variable=self.skip_existing_var).grid(row=3, column=0, columnspan=2, sticky="w", padx=6, pady=4)

        ctk.CTkButton(settings_frame, text="Save Settings", command=self._save_settings).grid(row=4, column=0, columnspan=2, pady=8)

        self.log_text = tk.Text(self, height=6)
        self.log_text.pack(fill="x", padx=12, pady=6)

    def _build_tk_ui(self):
        frame = tk.Frame(self)
        frame.pack(fill="both", expand=True)
        tk.Label(frame, text="Spotload (minimal UI)").pack()
        self.playlist_listbox = tk.Listbox(frame)
        self.playlist_listbox.pack(fill="x")
        tk.Button(frame, text="Connect Spotify", command=self.connect_spotify).pack()
        tk.Button(frame, text="Load Playlists", command=lambda: self.run_in_background(self._load_playlists_task, message="Loading playlists...")).pack()
        tk.Button(frame, text="Download Playlist (Audio)", command=self.download_playlist_audio).pack()
        tk.Button(frame, text="Export M3U", command=self._export_playlist_m3u).pack()
        self.track_listbox = tk.Listbox(frame)
        self.track_listbox.pack(fill="both", expand=True)
        self.album_art_label = tk.Label(frame, text="No cover")
        self.album_art_label.pack()
        self.log_text = tk.Text(self, height=6)
        self.log_text.pack(fill="x")

    # ---------------- Runnable background helper ------------------
    def run_in_background(
        self,
        func: Callable[..., Any],
        args: tuple = (),
        kwargs: Optional[dict] = None,
        message: str = "Working...",
        on_done: Optional[Callable[[Any], None]] = None,
        show_error: bool = True
    ):
        """
        Run `func(*args, **(kwargs or {}))` in a thread while showing the loading modal.
        If the function returns a result and `on_done` is provided, `on_done(result)` is
        called in the main thread. Exceptions are logged and optionally shown to the user.
        """
        self.show_loading(message)
        def worker():
            try:
                res = func(*args, **(kwargs or {}))
                if on_done:
                    self.after(0, lambda r=res: on_done(r))
            except Exception as e:
                logger.exception("Background task failed: %s", e)
                if show_error:
                    # Show the error in the UI thread
                    self.after(0, lambda: messagebox.showerror("Error", str(e)))
            finally:
                # always hide loading in UI thread
                self.after(0, self.hide_loading)
        threading.Thread(target=worker, daemon=True).start()

    # ---------------- Config & spotify -----------------
    def _save_settings(self):
        self.cfg["audio_quality"] = self.quality_var.get()
        self.cfg["add_metadata"] = self.metadata_var.get()
        self.cfg["organize_by_artist"] = self.organize_var.get()
        self.cfg["skip_existing"] = self.skip_existing_var.get()
        save_config(self.cfg)
        self.log("Settings saved")

    def connect_spotify(self):
        # connect is light-weight; show a quick loading while ensuring client
        def do_connect():
            if not self.sp_client.ensure_client():
                raise RuntimeError("Failed to initialize Spotify client. Set client_id/client_secret in settings.")
            return True
        def on_done(_):
            self.log("Connected to Spotify")
        self.run_in_background(do_connect, message="Connecting to Spotify...", on_done=on_done)

    # -------------- Playlists loading (UI friendly) ------------
    def _load_playlists_task(self):
        playlists = self.sp_client.fetch_user_playlists()
        self.playlists = playlists
        # update UI after fetch
        self.after(0, lambda: self._update_playlist_ui(len(playlists)))

    def _update_playlist_ui(self, count: int):
        self.playlist_listbox.delete(0, "end")
        for p in self.playlists:
            display = f"{p.get('name')} ({p.get('tracks', {}).get('total', 0)})"
            self.playlist_listbox.insert("end", display)
        self.log(f"Loaded {count} playlists")

    def _on_playlist_select(self):
        sel = self.playlist_listbox.curselection()
        if not sel:
            return
        idx = sel[0]
        self.current_playlist = self.playlists[idx]
        # fetch tracks via run_in_background so errors are shown and loading displayed
        self.run_in_background(self._populate_tracks_task, args=(self.current_playlist,), message="Loading tracks...")

    def _populate_tracks_task(self, playlist):
        tracks = self.sp_client.fetch_playlist_items(playlist.get("id"))
        items = []
        for t in tracks:
            album_art_url = None
            if t.get("album", {}).get("images"):
                album_art_url = t["album"]["images"][0].get("url")
            year = None
            release_date = t.get("album", {}).get("release_date", "")
            if release_date:
                year = release_date.split("-")[0]
            items.append({
                "title": t.get("name", ""),
                "artists": [a.get("name", "") for a in t.get("artists", [])],
                "album": t.get("album", {}).get("name", ""),
                "duration_ms": t.get("duration_ms", 0),
                "album_art_url": album_art_url,
                "year": year
            })
        # update UI
        self.track_items.clear()
        self.after(0, lambda: self.track_listbox.delete(0, "end"))
        for i, meta in enumerate(items):
            self.track_items[i] = {"meta": meta, "state": "idle"}
            display = f"{i+1}. {meta['title']} — {', '.join(meta['artists'])}"
            self.after(0, lambda d=display: self.track_listbox.insert("end", d))
        self.log(f"Loaded {len(items)} tracks")
        if items and items[0].get("album_art_url"):
            self._load_and_set_album_art(items[0]["album_art_url"])
        else:
            self._clear_album_art()

    # ---------------- Album art handling -----------------
    def _clear_album_art(self):
        try:
            if ctk:
                self.album_art_label.configure(image=None, text="No cover")
            else:
                self.album_art_label.config(image=None, text="No cover")
            self.album_art_img = None
        except Exception:
            pass

    def _load_and_set_album_art(self, url: Optional[str]):
        if not url:
            self._clear_album_art()
            return
        if url in self.album_art_cache:
            imgobj = self.album_art_cache[url]
            try:
                self.album_art_label.configure(image=imgobj, text="")
            except Exception:
                try:
                    self.album_art_label.config(image=imgobj, text="")
                except Exception:
                    pass
            self.album_art_img = imgobj
            return

        def worker():
            try:
                import requests
                from PIL import Image
                r = requests.get(url, stream=True, timeout=10)
                r.raise_for_status()
                img = Image.open(BytesIO(r.content)).convert("RGBA")
                img = img.resize((250, 250), Image.LANCZOS)
                if ctk:
                    try:
                        ctk_img = ctk.CTkImage(light_image=img, dark_image=img, size=(250, 250))
                        self.album_art_cache[url] = ctk_img
                        self.after(0, lambda: self.album_art_label.configure(image=ctk_img, text=""))
                        self.album_art_img = ctk_img
                        return
                    except Exception:
                        pass
                photo = ImageTk.PhotoImage(img)
                self.album_art_cache[url] = photo
                self.after(0, lambda: self.album_art_label.configure(image=photo, text=""))
                self.album_art_img = photo
            except Exception:
                self.after(0, self._clear_album_art)

        threading.Thread(target=worker, daemon=True).start()

    # ---------------- Loading modal and bulk download UI -------------
    def show_loading(self, message: str):
        """Show a small modal loading Toplevel with animated dots (fallback-friendly)."""
        if self._loading_top:
            # update base message
            self._loading_message_base = message
            try:
                self._loading_label.config(text=message)
            except Exception:
                pass
            return

        top = tk.Toplevel(self)
        top.transient(self)
        top.grab_set()
        top.title("")
        top.geometry("300x80")
        top.resizable(False, False)
        # Center
        try:
            self.update_idletasks()
            x = self.winfo_rootx() + (self.winfo_width() // 2) - 150
            y = self.winfo_rooty() + (self.winfo_height() // 2) - 40
            top.geometry(f"+{x}+{y}")
        except Exception:
            pass

        lbl = tk.Label(top, text=message, font=("TkDefaultFont", 11))
        lbl.pack(pady=(18, 6))
        self._loading_top = top
        self._loading_label = lbl
        self._loading_dots = 0
        self._loading_message_base = message
        self._animate_loading()

    def _animate_loading(self):
        if not self._loading_top:
            return
        dots = "." * (self._loading_dots % 4)
        try:
            base = self._loading_message_base
            self._loading_label.config(text=base + dots)
        except Exception:
            pass
        self._loading_dots += 1
        self._loading_anim_handle = self.after(400, self._animate_loading)

    def hide_loading(self):
        if getattr(self, "_loading_anim_handle", None):
            try:
                self.after_cancel(self._loading_anim_handle)
            except Exception:
                pass
            self._loading_anim_handle = None
        if self._loading_top:
            try:
                self._loading_top.grab_release()
                self._loading_top.destroy()
            except Exception:
                pass
            self._loading_top = None

    def show_download_progress(self, total: int):
        """Show a progress window for bulk downloads."""
        if self._download_progress_top:
            return
        top = tk.Toplevel(self)
        top.transient(self)
        top.title("Downloading Playlist")
        top.geometry("420x120")
        top.resizable(False, False)
        try:
            self.update_idletasks()
            x = self.winfo_rootx() + (self.winfo_width() // 2) - 210
            y = self.winfo_rooty() + (self.winfo_height() // 2) - 60
            top.geometry(f"+{x}+{y}")
        except Exception:
            pass

        tk.Label(top, text="Downloading playlist...", font=("TkDefaultFont", 11)).pack(pady=(12, 6))
        if ctk:
            try:
                pb = ctk.CTkProgressBar(top, orientation="horizontal", width=380)
                pb.set(0.0)
                pb.pack(pady=(4, 8))
            except Exception:
                pb = ttk.Progressbar(top, orient="horizontal", length=380, mode="determinate")
                pb["maximum"] = total
                pb["value"] = 0
                pb.pack(pady=(4, 8))
        else:
            pb = ttk.Progressbar(top, orient="horizontal", length=380, mode="determinate")
            pb["maximum"] = total
            pb["value"] = 0
            pb.pack(pady=(4, 8))

        status_lbl = tk.Label(top, text=f"0 / {total}")
        status_lbl.pack()

        self._download_progress_top = top
        self._download_progress_bar = pb
        self._download_progress_label = status_lbl
        self._dl_total = total
        self._dl_done = 0

    def hide_download_progress(self):
        if self._download_progress_top:
            try:
                self._download_progress_top.destroy()
            except Exception:
                pass
            self._download_progress_top = None
        self._dl_total = 0
        self._dl_done = 0

    # ---------------- Download controls -----------------
    def queue_download_selected(self):
        sel = self.track_listbox.curselection()
        if not sel:
            messagebox.showwarning("No selection", "Select one or more tracks to download.")
            return
        for i in sel:
            info = self.track_items.get(i)
            if info:
                task = {"idx": i, "meta": info["meta"], "total": len(self.track_items)}
                self.downloader.enqueue(task)
                info["state"] = "queued"
        self.log("Added selected tracks to download queue")

    def download_playlist_audio(self):
        if not self.current_playlist:
            messagebox.showwarning("No playlist", "Select a playlist first.")
            return
        if not self.track_items:
            messagebox.showwarning("No tracks", "No tracks loaded for the selected playlist.")
            return
        total = len(self.track_items)
        self.show_download_progress(total)
        for idx, info in list(self.track_items.items()):
            task = {"idx": idx, "meta": info["meta"], "total": total}
            self.downloader.enqueue(task)
            info["state"] = "queued"
        self.log(f"Queued {total} tracks for download")

    # ---------------- Event polling from downloader -------------------
    def _poll_event_queue(self):
        while not self.event_queue.empty():
            ev = self.event_queue.get()
            etype = ev.get("type")
            meta = ev.get("meta", {})
            if etype == "completed":
                path = ev.get("path")
                self.log(f"Downloaded: {meta.get('title')} -> {path}")
                self.history.setdefault("downloads", []).append({
                    "title": meta.get("title", ""),
                    "artist": ", ".join(meta.get("artists", [])),
                    "status": "Downloaded",
                    "date": time.strftime("%Y-%m-%dT%H:%M:%S")
                })
                save_history(self.history)
                if self._dl_total > 0:
                    self._dl_done += 1
                    try:
                        if ctk and isinstance(self._download_progress_bar, ctk.CTkProgressBar):
                            val = min(1.0, self._dl_done / self._dl_total)
                            self._download_progress_bar.set(val)
                        else:
                            self._download_progress_bar["value"] = self._dl_done
                        self._download_progress_label.config(text=f"{self._dl_done} / {self._dl_total}")
                    except Exception:
                        pass
                    if self._dl_done >= self._dl_total:
                        self.log("Playlist download complete")
                        self.after(200, self.hide_download_progress)

            elif etype == "ffmpeg_missing":
                # critical: let the user know immediately and suggest action
                self.log("FFmpeg missing - please install ffmpeg.")
                messagebox.showerror("FFmpeg missing", "FFmpeg is required to convert audio. Please install ffmpeg and ensure it's on your PATH.")
            elif etype in ("video_unavailable", "private_video", "download_error", "failed"):
                # Informative user-visible message for individual download problems
                if etype == "video_unavailable":
                    title = "Video unavailable"
                    body = f"Track unavailable: {meta.get('title')}"
                elif etype == "private_video":
                    title = "Private or deleted video"
                    body = f"Track private/deleted: {meta.get('title')}"
                else:
                    title = "Download error"
                    body = f"Failed to download '{meta.get('title')}': {ev.get('error', 'Unknown error')}"
                # Log and show a non-blocking warning to the user
                self.log(f"{title}: {body}")
                try:
                    messagebox.showwarning(title, body)
                except Exception:
                    # fallback to logging if messagebox cannot be shown
                    logger.warning(body)

                # record in history
                status_map = {
                    "video_unavailable": "Unavailable",
                    "private_video": "Private/Deleted",
                    "download_error": "DownloadError",
                    "failed": "Failed"
                }
                status = status_map.get(etype, "Failed")
                self.history.setdefault("failed", []).append({
                    "title": meta.get("title", ""),
                    "artist": ", ".join(meta.get("artists", [])),
                    "status": status,
                    "date": time.strftime("%Y-%m-%dT%H:%M:%S"),
                    "error": ev.get("error")
                })
                save_history(self.history)

                # update bulk progress if active
                if self._dl_total > 0:
                    self._dl_done += 1
                    try:
                        if ctk and isinstance(self._download_progress_bar, ctk.CTkProgressBar):
                            val = min(1.0, self._dl_done / self._dl_total)
                            self._download_progress_bar.set(val)
                        else:
                            self._download_progress_bar["value"] = self._dl_done
                        self._download_progress_label.config(text=f"{self._dl_done} / {self._dl_total}")
                    except Exception:
                        pass
                    if self._dl_done >= self._dl_total:
                        self.after(200, self.hide_download_progress)
            else:
                self.log(f"Event: {ev}")
        self.after(200, self._poll_event_queue)

    # --------------- Export M3U ---------------
    def _export_playlist_m3u(self):
        if not self.current_playlist:
            messagebox.showwarning("No playlist", "Select a playlist first.")
            return
        filename = filedialog.asksaveasfilename(
            defaultextension=".m3u",
            filetypes=[("M3U Playlist", "*.m3u")],
            initialfile=sanitize_filename(self.current_playlist.get("name", "playlist")) + ".m3u"
        )
        if not filename:
            return
        try:
            with open(filename, "w", encoding="utf-8") as f:
                f.write("#EXTM3U\n")
                for info in self.track_items.values():
                    meta = info["meta"]
                    artist = ", ".join(meta.get("artists", []))
                    title = meta.get("title", "Unknown")
                    duration = int(meta.get("duration_ms", 0) / 1000)
                    f.write(f"#EXTINF:{duration},{artist} - {title}\n")
                    f.write(f"{sanitize_filename(f'{artist} - {title}')}.mp3\n")
            messagebox.showinfo("Exported", f"Playlist exported to:\n{filename}")
        except Exception as e:
            messagebox.showerror("Error", str(e))

    # ---------------- Logging -----------------
    def log(self, msg: str):
        ts = time.strftime("%H:%M:%S")
        try:
            self.log_text.insert("end", f"[{ts}] {msg}\n")
            self.log_text.see("end")
        except Exception:
            logger.info(msg)