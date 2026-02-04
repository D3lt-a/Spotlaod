"""
Centralized modal & progress manager for tkinter.

Provides simple progress dialog creation and updates so UI code
doesn't intermix modal window logic.
"""
from typing import Dict, Optional
import tkinter as tk
from tkinter import ttk

class ProgressDialog(tk.Toplevel):
    def __init__(self, parent, title="Working..."):
        super().__init__(parent)
        self.title(title)
        self.transient(parent)
        self.resizable(False, False)
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self._closed = False

        self.label = ttk.Label(self, text=title)
        self.label.pack(padx=12, pady=(12, 6), anchor="w")
        self.progress = ttk.Progressbar(self, orient="horizontal", length=360, mode="determinate")
        self.progress.pack(padx=12, pady=(0, 12), fill="x")
        self.cancel_btn = ttk.Button(self, text="Cancel", command=self._on_cancel)
        self.cancel_btn.pack(padx=12, pady=(0, 12), anchor="e")

        # center
        self.update_idletasks()
        w = self.winfo_width(); h = self.winfo_height()
        x = (self.winfo_screenwidth() - w)//2
        y = (self.winfo_screenheight() - h)//2
        self.geometry(f"+{x}+{y}")

        self._cancel_handler = None

    def _on_cancel(self):
        if self._cancel_handler:
            try:
                self._cancel_handler()
            except Exception:
                pass

    def _on_close(self):
        # treat as cancel
        self._on_cancel()
        self._closed = True
        self.destroy()

    def set_cancel_handler(self, cb):
        self._cancel_handler = cb

class ModalManager:
    def __init__(self, root: tk.Tk):
        self.root = root
        self._active: Dict[str, ProgressDialog] = {}

    def show_progress(self, key: str, title="Working...", determinate=True, maxval: int = 100):
        dlg = ProgressDialog(self.root, title=title)
        if determinate:
            dlg.progress.config(mode="determinate", maximum=maxval, value=0)
        else:
            dlg.progress.config(mode="indeterminate")
            dlg.progress.start(10)
        self._active[key] = dlg
        return dlg

    def update(self, key: str, label: Optional[str] = None, value: Optional[int] = None, maxval: Optional[int] = None):
        dlg = self._active.get(key)
        if not dlg:
            return
        if label is not None:
            dlg.label.config(text=label)
        if maxval is not None:
            dlg.progress.config(maximum=maxval)
        if value is not None:
            dlg.progress.config(value=value)

    def close(self, key: str):
        dlg = self._active.pop(key, None)
        if dlg:
            try:
                dlg.destroy()
            except Exception:
                pass