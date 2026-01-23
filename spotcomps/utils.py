"""
Utilities: config, history, helpers and logging setup.
"""
from __future__ import annotations
import json
import logging
import re
import socket
from pathlib import Path
from typing import Dict

# App directories and files
APP_DIR = Path.home() / ".spotload"
APP_DIR.mkdir(parents=True, exist_ok=True)
CONFIG_FILE = APP_DIR / "config.json"
HISTORY_FILE = APP_DIR / "download_history.json"

DEFAULTS = {
    "output_dir": str(Path.home() / "Music" / "SpotifyMusic"),
    "concurrency": 3,
    "cache_path": str(APP_DIR / ".spotify_cache"),
    "client_id": "",
    "client_secret": "",
    "redirect_uri": "http://127.0.0.1:8888/callback",
    "audio_quality": "320",
    "add_metadata": True,
    "organize_by_artist": False,
    "skip_existing": True
}

_illegal_filename_re = re.compile(r'[\\/*?:"<>|]')

def sanitize_filename(name: str) -> str:
    if not name:
        return ""
    name = name.strip()
    name = _illegal_filename_re.sub("", name)
    return name[:240]

def ensure_dir(path: Path):
    path.mkdir(parents=True, exist_ok=True)

# Config / history helpers
def load_config() -> Dict:
    try:
        if CONFIG_FILE.exists():
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                cfg = json.load(f)
        else:
            cfg = DEFAULTS.copy()
            save_config(cfg)
        for k, v in DEFAULTS.items():
            cfg.setdefault(k, v)
        return cfg
    except Exception:
        return DEFAULTS.copy()

def save_config(cfg: Dict):
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
    except Exception:
        pass

def load_history() -> Dict:
    if HISTORY_FILE.exists():
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {"downloads": [], "failed": []}
    return {"downloads": [], "failed": []}

def save_history(history: Dict):
    try:
        if len(history.get("downloads", [])) > 1000:
            history["downloads"] = history["downloads"][-1000:]
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(history, f, indent=2)
    except Exception:
        pass

# Logger (one place to configure)
logger = logging.getLogger("spotload")
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))
    logger.addHandler(handler)
logger.setLevel(logging.INFO)

# Transient network error detection helper
def is_transient_network_error(exc: Exception) -> bool:
    import requests
    try:
        import urllib3
        URLLIB3_AVAILABLE = True
    except Exception:
        URLLIB3_AVAILABLE = False

    if isinstance(exc, (requests.exceptions.ConnectionError, requests.exceptions.Timeout)):
        return True
    if URLLIB3_AVAILABLE and isinstance(exc, urllib3.exceptions.ProtocolError):
        return True
    if isinstance(exc, (ConnectionResetError, BrokenPipeError, socket.error, OSError)):
        return True
    msg = str(exc).lower()
    if "connection reset" in msg or "connection aborted" in msg or "timeout" in msg:
        return True
    return False