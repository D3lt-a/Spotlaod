"""
Entry point: start the Spotload GUI app.
"""
from spotcomps.ui import SpotloadApp

def main():
    app = SpotloadApp()
    # optional: add extra controls at bottom
    try:
        import customtkinter as ctk
        from spotcomps.utils import sanitize_filename
        btn_frame = ctk.CTkFrame(app)
        btn_frame.pack(side="bottom", fill="x", padx=8, pady=8)
        ctk.CTkButton(btn_frame, text="Download Selected", command=app.queue_download_selected).pack(side="left", padx=6)
        def open_output():
            out = app.cfg.get("output_dir")
            if not out:
                return
            import os
            try:
                if os.name == "nt":
                    os.startfile(out)
                elif os.name == "posix":
                    os.system(f'xdg-open "{out}"')
            except Exception:
                pass
        ctk.CTkButton(btn_frame, text="Open Output Folder", command=open_output).pack(side="left", padx=6)
    except Exception:
        try:
            import tkinter as tk
            tk.Button(app, text="Download Selected", command=app.queue_download_selected).pack()
        except Exception:
            pass

    app.mainloop()

if __name__ == "__main__":
    main()