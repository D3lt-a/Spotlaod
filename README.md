
# Spotload — Simple Spotify Playlist Downloader

A small, personal GUI app for downloading audio from your Spotify playlists (for personal use). The project is organized into a small package so each part is easy to read and debug.

Quick highlights
- Downloads audio using `yt-dlp` (searches YouTube) and converts to MP3 (requires `ffmpeg`).
- Adds ID3 tags and album art if `mutagen` is installed.
- Uses `spotipy` to list your playlists and tracks.
- Simple UI using `customtkinter` (optional) or plain `tkinter`.

Requirements
- Python 3.9+
- ffmpeg on PATH
- Install Python deps:
  ```
  pip install -r requirements.txt
  ```
  (mutagen and customtkinter are optional but recommended for tagging and nicer UI)

Project layout (what each file/folder does)
- `main.py`
  - App entry point. Starts the GUI (`spotload.ui.SpotloadApp`).

- `spotload/`
  - `__init__.py` — package marker.
  - `utils.py` — config & history helpers, filename sanitiser, simple logging and network-error helper.
    - Config and history are stored in `~/.spotload/config.json` and `~/.spotload/download_history.json`.
  - `tagging.py` — ID3 tagging helpers (uses `mutagen` if installed).
  - `spotify_client.py` — Wraps spotipy authentication and resilient playlist/track fetching with retries.
  - `downloader.py` — Worker pool and yt-dlp wrapper that performs downloads and posts events back to the UI.
  - `ui.py` — GUI (album-art caching, loading modal, download progress, playlist/track UI). Uses `customtkinter` when available and falls back to plain `tkinter`.

How to use
1. Install dependencies:
   ```
   pip install -r requirements.txt
   ```
2. Ensure `ffmpeg` is installed and reachable from your PATH.
3. Run the app:
   ```
   python main.py
   ```
4. Click "Connect Spotify" and provide `client_id` and `client_secret` (or set them in `~/.spotload/config.json`).
5. Click "Load Playlists", select a playlist and either:
   - Download selected tracks, or
   - Click "Download Playlist (Audio)" to enqueue all tracks (shows progress).

Notes & tips
- Tagging: Install `mutagen` to enable ID3 tags/album art. If absent, downloads still work but files won’t be tagged.
- UI: `customtkinter` gives a nicer look and enables high-DPI image scaling; otherwise the app uses `tkinter`.
- History: Download history is stored at `~/.spotload/download_history.json`.
- Legal: This tool downloads audio from third-party sources. Make sure you comply with Spotify's Terms of Service and copyright law. Use only for content you are allowed to download.

If you want the UI split further, tests, or a CLI-only mode, tell me which and I’ll add it.
