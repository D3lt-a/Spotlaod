"""
Per-track widget used in the main track list: shows title, small status badge, and progress bar.
Designed for use with tkinter (ttk).
"""
import tkinter as tk
from tkinter import ttk
from typing import Optional
from ..app_state import TrackInfo

STATUS_COLORS = {
    "idle": "#9aa0a6",
    "queued": "#f0ad4e",
    "downloading": "#17a2b8",
    "completed": "#28a745",
    "failed": "#dc3545",
}

class TrackItemWidget(ttk.Frame):
    def __init__(self, parent, track: TrackInfo, *args, **kwargs):
        super().__init__(parent, *args, **kwargs)
        self.track = track
        self.columnconfigure(0, weight=1)
        self.title_lbl = ttk.Label(self, text=f"{track.title} — {track.artist}")
        self.title_lbl.grid(row=0, column=0, sticky="w")
        self.status_lbl = ttk.Label(self, text=track.status.capitalize(), width=10, anchor="center")
        self.status_lbl.grid(row=0, column=1, padx=(8,0))
        self.progress = ttk.Progressbar(self, orient="horizontal", length=140, mode="determinate")
        self.progress.grid(row=1, column=0, columnspan=2, sticky="we", pady=(4,0))
        self.refresh(track)

    def refresh(self, track: Optional[TrackInfo] = None):
        if track:
            self.track = track
        # status badge
        status = (self.track.status or "idle")
        color = STATUS_COLORS.get(status, "#9aa0a6")
        # note: ttk Label styling per-platform is limited; use style or fallback to background color via tk.Label if needed.
        self.status_lbl.config(text=status.capitalize())
        try:
            self.progress['value'] = int(self.track.progress * 100)
        except Exception:
            self.progress['value'] = 0