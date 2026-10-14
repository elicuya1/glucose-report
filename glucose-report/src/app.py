"""
glucose-report — desktop app.

One simple screen:
  - pick your CGM / pump CSV files (or use sample data)
  - choose the period and units
  - Build report -> key numbers here, full report with graphs in your browser

How to run:
  - In Spyder: File > Open > src/app.py, then press F5
  - Or from a terminal:  py src/app.py

For personal insight only. It describes your data and never gives advice.
"""

import math
import os
import sys
import traceback
import webbrowser
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox

# ---------------------------------------------------------------------------
# Find the project's src folder (where load.py, plots.py, ... live).
# __file__ only exists when this runs as a saved file (F5 in Spyder).
# ---------------------------------------------------------------------------
PROJECT_FOLDER = Path.home() / "OneDrive" / "Desktop" / "Projects" / "diabetes-report" / "glucose-report"


def find_src() -> Path:
    candidates = []
    try:
        candidates.append(Path(__file__).resolve().parent)
    except NameError:
        pass
    cwd = Path.cwd()
    candidates += [cwd, cwd / "src", PROJECT_FOLDER / "src"]
    for folder in candidates:
        if (folder / "load.py").exists() and (folder / "report.py").exists():
            return folder
    raise FileNotFoundError(
        "Couldn't find the project's src folder.\n"
        "Save this file as src/app.py inside your glucose-report folder and run it with F5,\n"
        f"or change PROJECT_FOLDER near the top of app.py (currently: {PROJECT_FOLDER})."
    )


SRC = find_src()
ROOT = SRC.parent
sys.path.insert(0, str(SRC))

import make_fake_data                                        # noqa: E402
from load import load_basal, load_bolus, load_glucose        # noqa: E402
from report import build_report, prepare                     # noqa: E402
from stats import daily_insulin, summary                     # noqa: E402

DATA = ROOT / "data"
REPORTS = ROOT / "reports"

# ---------------------------------------------------------------------------
# Colours and fonts
# ---------------------------------------------------------------------------
BG = "#0b0d16"
CARD = "#151826"
EDGE = "#252a3d"
SURFACE = "#1e2234"
SURFACE_HOVER = "#282d44"
TEXT = "#e8eaf2"
MUTED = "#8b93ab"
ACCENT = "#7c5cf6"
ACCENT_HOVER = "#9277ff"
ACCENT_LIGHT = "#a78bfa"
DISABLED = "#2c3046"
FONT = "Segoe UI"

DOTS = {"range": "#34d399", "avg": "#38bdf8", "gmi": "#a78bfa", "cv": "#fbbf24", "insulin": "#f472b6"}


def round_rect(canvas, x0, y0, x1, y1, r=12, **kw):
    """A rectangle with rounded corners."""
    r = max(0, min(r, (x1 - x0) / 2, (y1 - y0) / 2))
    pts = []
    for cx, cy, start in [(x1 - r, y0 + r, -90), (x1 - r, y1 - r, 0), (x0 + r, y1 - r, 90), (x0 + r, y0 + r, 180)]:
        for i in range(9):
            a = math.radians(start + i * 90 / 8)
            pts += [cx + r * math.cos(a), cy + r * math.sin(a)]
    return canvas.create_polygon(pts, **kw)


class Button(tk.Canvas):
    """Flat rounded button with hover."""

    def __init__(self, parent, text, command, primary=True, width=130, height=36):
        super().__init__(parent, width=width, height=height, bg=parent["bg"], highlightthickness=0, cursor="hand2")
        self.text, self.command = text, command
        self.base, self.hover = (ACCENT, ACCENT_HOVER) if primary else (SURFACE, SURFACE_HOVER)
        self.fg = "white" if primary else TEXT
        self.font = (FONT, 10, "bold" if primary else "normal")
        self.fill, self.enabled = self.base, True
        self.bind("<Configure>", lambda e: self.draw())
        self.bind("<Enter>", lambda e: self._set(self.hover))
        self.bind("<Leave>", lambda e: self._set(self.base))
        self.bind("<Button-1>", lambda e: self.enabled and self.command())

    def _set(self, fill):
        self.fill = fill
        self.draw()

    def draw(self):
        self.delete("all")
        w, h = self.winfo_width(), self.winfo_height()
        fill = self.fill if self.enabled else DISABLED
        round_rect(self, 0, 0, w, h, r=10, fill=fill, outline=fill)
        self.create_text(w / 2, h / 2, text=self.text, fill=self.fg if self.enabled else MUTED, font=self.font)

    def set_enabled(self, on):
        self.enabled = on
        self.configure(cursor="hand2" if on else "arrow")
        self.draw()


class Toggle(tk.Canvas):
    """Segmented control:  [ 7 days | 14 | 30 | 90 ]"""

    def __init__(self, parent, options, variable, seg=58, height=32):
        super().__init__(parent, width=seg * len(options) + 6, height=height, bg=parent["bg"],
                         highlightthickness=0, cursor="hand2")
        self.options, self.var, self.seg, self.h = options, variable, seg, height
        self.bind("<Button-1>", self._click)
        variable.trace_add("write", lambda *a: self.draw())
        self.draw()

    def draw(self):
        self.delete("all")
        round_rect(self, 0, 0, self.seg * len(self.options) + 6, self.h, r=10, fill=SURFACE, outline=SURFACE)
        for i, (label, value) in enumerate(self.options):
            x0 = 3 + i * self.seg
            on = str(self.var.get()) == str(value)
            if on:
                round_rect(self, x0, 3, x0 + self.seg, self.h - 3, r=8, fill=ACCENT, outline=ACCENT)
            self.create_text(x0 + self.seg / 2, self.h / 2, text=label, fill="white" if on else MUTED,
                             font=(FONT, 9, "bold" if on else "normal"))

    def _click(self, e):
        i = int((e.x - 3) // self.seg)
        if 0 <= i < len(self.options):
            self.var.set(self.options[i][1])


class Stat(tk.Canvas):
    """Small rounded box: coloured dot + label, big number underneath."""

    def __init__(self, parent, label, value, dot):
        super().__init__(parent, height=74, bg=parent["bg"], highlightthickness=0)
        self.label, self.value, self.dot = label, value, dot
        self.bind("<Configure>", lambda e: self.draw())

    def draw(self):
        self.delete("all")
        w, h = self.winfo_width(), self.winfo_height()
        round_rect(self, 0, 0, w, h, r=12, fill=CARD, outline=EDGE)
        self.create_oval(14, 17, 21, 24, fill=self.dot, outline=self.dot)
        self.create_text(28, 20, text=self.label, anchor="w", fill=MUTED, font=(FONT, 9))
        self.create_text(14, 48, text=self.value, anchor="w", fill=TEXT, font=(FONT, 17, "bold"))


class Card(tk.Frame):
    """A rounded card: draws its own rounded background, content goes in .body"""

    def __init__(self, parent, pad=18):
        super().__init__(parent, bg=BG)
        self.bg = tk.Canvas(self, bg=BG, highlightthickness=0)
        self.bg.place(x=0, y=0, relwidth=1, relheight=1)
        self.body = tk.Frame(self, bg=CARD)
        self.body.pack(fill="both", expand=True, padx=pad, pady=pad)
        self.bind("<Configure>", self._draw)

    def _draw(self, e):
        self.bg.delete("all")
        round_rect(self.bg, 1, 1, e.width - 1, e.height - 1, r=16, fill=CARD, outline=EDGE)


# ---------------------------------------------------------------------------
# The app
# ---------------------------------------------------------------------------
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Glucose Report")
        self.geometry("760x560")
        self.minsize(700, 540)
        self.configure(bg=BG)

        self.paths = {"glucose": "", "basal": "", "bolus": ""}
        self.days = tk.IntVar(value=7)
        self.units = tk.StringVar(value="mgdl")
        self.report_path = None

        page = tk.Frame(self, bg=BG)
        page.pack(fill="both", expand=True, padx=28, pady=24)

        # Title
        head = tk.Frame(page, bg=BG)
        head.pack(fill="x")
        tk.Label(head, text="Glucose", bg=BG, fg=TEXT, font=(FONT, 22, "bold")).pack(side="left")
        tk.Label(head, text=" Report", bg=BG, fg=ACCENT_LIGHT, font=(FONT, 22, "bold")).pack(side="left")

        # Files
        files = Card(page)
        files.pack(fill="x", pady=(18, 14))
        self.file_labels = {}
        for i, (key, label) in enumerate([("glucose", "Glucose"), ("basal", "Basal"), ("bolus", "Bolus")]):
            tk.Label(files.body, text=label, bg=CARD, fg=MUTED, font=(FONT, 10), width=9, anchor="w").grid(
                row=i, column=0, sticky="w", pady=3)
            name = tk.Label(files.body, text="optional" if key != "glucose" else "no file", bg=CARD,
                            fg="#4d546b" if key != "glucose" else MUTED, font=(FONT, 10), anchor="w")
            name.grid(row=i, column=1, sticky="w")
            self.file_labels[key] = name
            Button(files.body, "Choose", lambda k=key: self.pick(k), primary=False,
                   width=84, height=30).grid(row=i, column=2, pady=3)
        files.body.columnconfigure(1, weight=1)
        sample = tk.Label(files.body, text="Use sample data", bg=CARD, fg=ACCENT_LIGHT,
                          font=(FONT, 9), cursor="hand2")
        sample.grid(row=3, column=0, columnspan=2, sticky="w", pady=(8, 0))
        sample.bind("<Button-1>", lambda e: self.make_fake())

        # Controls
        controls = tk.Frame(page, bg=BG)
        controls.pack(fill="x")
        Toggle(controls, [("7 days", 7), ("14", 14), ("30", 30), ("90", 90)], self.days).pack(side="left")
        Toggle(controls, [("mg/dL", "mgdl"), ("mmol/L", "mmol")], self.units, seg=66).pack(side="left", padx=12)
        self.build_btn = Button(controls, "Build report", self.build, width=136)
        self.build_btn.pack(side="right")

        # Results
        self.stats = tk.Frame(page, bg=BG)
        self.stats.pack(fill="x", pady=(22, 12))
        self.empty = tk.Label(self.stats, text="Your numbers will show up here.", bg=BG, fg=MUTED, font=(FONT, 10))
        self.empty.pack(anchor="w", pady=20)

        bottom = tk.Frame(page, bg=BG)
        bottom.pack(fill="x")
        self.open_btn = Button(bottom, "Open full report  ↗", self.open_report, width=170)
        self.open_btn.pack(side="left")
        self.open_btn.set_enabled(False)

        # Footer
        self.status = tk.Label(page, text="", bg=BG, fg=MUTED, font=(FONT, 9), anchor="w")
        self.status.pack(side="bottom", fill="x")
        tk.Label(page, text="Describes your data only. Not medical advice.", bg=BG, fg="#5c6378",
                 font=(FONT, 8), anchor="w").pack(side="bottom", fill="x", pady=(0, 2))

        if (DATA / "fake_glucose.csv").exists():
            self._use_sample_paths()
            self.say("Sample data loaded.")

    # -------------------------------------------------------------- helpers
    def say(self, msg):
        self.status.configure(text=msg)
        self.update_idletasks()

    def set_file(self, key, path):
        self.paths[key] = str(path) if path else ""
        if path:
            self.file_labels[key].configure(text=Path(path).name, fg=TEXT)

    def pick(self, key):
        path = filedialog.askopenfilename(title="Choose a CSV export",
                                          initialdir=DATA if DATA.exists() else ROOT,
                                          filetypes=[("CSV files", "*.csv"), ("All files", "*.*")])
        if path:
            self.set_file(key, path)

    def _use_sample_paths(self):
        for key in self.paths:
            self.set_file(key, DATA / f"fake_{key}.csv")

    # -------------------------------------------------------------- actions
    def make_fake(self):
        try:
            make_fake_data.main()
            self._use_sample_paths()
            self.say("Sample data ready. Click Build report.")
        except Exception as e:
            self.fail("Couldn't make sample data", e)

    def build(self):
        if not self.paths["glucose"]:
            messagebox.showwarning("No data", "Choose a glucose file first, or use sample data.")
            return
        self.build_btn.set_enabled(False)
        try:
            self.say("Building…")
            glucose = load_glucose(self.paths["glucose"])
            basal = load_basal(self.paths["basal"]) if self.paths["basal"] else None
            bolus = load_bolus(self.paths["bolus"]) if self.paths["bolus"] else None
            days, unit = int(self.days.get()), self.units.get()

            html = build_report(glucose, basal, bolus, days, unit)
            REPORTS.mkdir(exist_ok=True)
            self.report_path = REPORTS / "report.html"
            self.report_path.write_text(html, encoding="utf-8")

            self.show_stats(*prepare(glucose, basal, bolus, days), unit)
            self.open_btn.set_enabled(True)
            self.say("Report ready.")
        except Exception as e:
            self.fail("Couldn't build the report", e)
        finally:
            self.build_btn.set_enabled(True)

    def show_stats(self, glucose, basal, bolus, unit):
        for w in self.stats.winfo_children():
            w.destroy()
        s = summary(glucose)
        mmol = unit == "mmol"
        items = [
            ("In range", f"{s['tir']['In range']:.0f}%", DOTS["range"]),
            ("Average", f"{s['mean_mgdl'] / 18:.1f}" if mmol else f"{s['mean_mgdl']}", DOTS["avg"]),
            ("GMI", f"{s['gmi_pct']}%", DOTS["gmi"]),
            ("Variability", f"{s['cv_pct']:.0f}%", DOTS["cv"]),
        ]
        ins = daily_insulin(basal, bolus, s["start"], s["end"])
        if ins:
            items.append(("Insulin/day", f"{ins.get('basal_per_day', 0) + ins.get('bolus_per_day', 0):.1f} U",
                          DOTS["insulin"]))
        for col, (label, value, dot) in enumerate(items):
            Stat(self.stats, label, value, dot).grid(row=0, column=col, sticky="ew", padx=(0 if col == 0 else 10, 0))
            self.stats.columnconfigure(col, weight=1, uniform="stat")
        tk.Label(self.stats, text=f"{s['start']:%d %b} – {s['end']:%d %b %Y}  ·  {s['readings']} readings",
                 bg=BG, fg=MUTED, font=(FONT, 9)).grid(row=1, column=0, columnspan=len(items), sticky="w",
                                                         pady=(10, 0))

    def open_report(self):
        if self.report_path and self.report_path.exists():
            webbrowser.open(self.report_path.as_uri())

    def fail(self, title, e):
        print(traceback.format_exc())       # full details in Spyder's console
        self.say(f"Error: {e}")
        messagebox.showerror(title, str(e))


if __name__ == "__main__":
    App().mainloop()
