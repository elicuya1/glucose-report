"""
STEP 5 — The graphs.

Each function takes the clean tables from load.py and returns a matplotlib figure.

Try them one at a time:
    python src/plots.py            # uses the fake data, saves PNGs to reports/
"""

from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # draw to files, no window needed
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd

from stats import time_in_ranges

TARGET_LOW, TARGET_HIGH = 70, 180

COLORS = {
    "Very low": "#b3261e",
    "Low": "#e8705f",
    "In range": "#2e9e5b",
    "High": "#f2b33d",
    "Very high": "#e07b1a",
    "line": "#2f5d9e",
    "band": "#2e9e5b",
    "basal": "#7a5cc4",
    "bolus": "#c4458a",
}


class Units:
    """Lets every graph show mg/dL or mmol/L."""

    def __init__(self, unit: str = "mgdl"):
        self.mmol = unit == "mmol"
        self.label = "mmol/L" if self.mmol else "mg/dL"

    def __call__(self, value):
        return value / 18.0 if self.mmol else value


def _style(ax):
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(axis="y", alpha=0.25)


# ---------------------------------------------------------------------------
# 1. Overview: every reading with the target band
# ---------------------------------------------------------------------------
def plot_overview(glucose: pd.DataFrame, units: Units = Units()):
    fig, ax = plt.subplots(figsize=(12, 4))
    ax.axhspan(units(TARGET_LOW), units(TARGET_HIGH), color=COLORS["band"], alpha=0.12, label="Target 70–180 mg/dL")
    # Break the line where the sensor had gaps longer than 15 min
    g = glucose.set_index("timestamp")["glucose_mgdl"].resample("5min").mean()
    ax.plot(g.index, units(g.values), color=COLORS["line"], linewidth=0.9)
    ax.set_title("Glucose overview", loc="left", fontweight="bold")
    ax.set_ylabel(units.label)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%a %d %b"))
    ax.legend(loc="upper right", frameon=False)
    _style(ax)
    fig.tight_layout()
    return fig


# ---------------------------------------------------------------------------
# 2. Time in Range: one stacked bar
# ---------------------------------------------------------------------------
def plot_time_in_range(glucose: pd.DataFrame, units: Units = Units()):
    tir = time_in_ranges(glucose)
    fig, ax = plt.subplots(figsize=(5, 5))
    bottom = 0
    for name, pct in tir.items():
        ax.bar(0, pct, bottom=bottom, color=COLORS[name], width=0.5)
        if pct >= 1.5:
            ax.text(0.35, bottom + pct / 2, f"{name}  {pct:.0f}%", va="center", fontsize=10)
        bottom += pct
    ax.set_xlim(-0.4, 1.4)
    ax.set_ylim(0, 100)
    ax.set_xticks([])
    ax.set_ylabel("% of time")
    ax.set_title("Time in Range", loc="left", fontweight="bold")
    ax.spines[["top", "right", "bottom"]].set_visible(False)
    fig.tight_layout()
    return fig


# ---------------------------------------------------------------------------
# 3. AGP — the "typical day": all days stacked by time of day
# ---------------------------------------------------------------------------
def plot_agp(glucose: pd.DataFrame, units: Units = Units()):
    df = glucose.copy()
    # Group readings into 15-minute slots of the day
    df["slot"] = (df.timestamp.dt.hour * 60 + df.timestamp.dt.minute) // 15 * 15
    q = df.groupby("slot")["glucose_mgdl"].quantile([0.05, 0.25, 0.5, 0.75, 0.95]).unstack()
    q = q.rolling(3, center=True, min_periods=1).mean()   # light smoothing
    x = q.index / 60  # hours

    fig, ax = plt.subplots(figsize=(12, 4.5))
    ax.axhspan(units(TARGET_LOW), units(TARGET_HIGH), color=COLORS["band"], alpha=0.10)
    ax.fill_between(x, units(q[0.05]), units(q[0.95]), color=COLORS["line"], alpha=0.12, label="5–95%")
    ax.fill_between(x, units(q[0.25]), units(q[0.75]), color=COLORS["line"], alpha=0.30, label="25–75%")
    ax.plot(x, units(q[0.5]), color=COLORS["line"], linewidth=2, label="Median")
    ax.set_xlim(0, 24)
    ax.set_xticks(range(0, 25, 3))
    ax.set_xticklabels([f"{h:02d}:00" for h in range(0, 25, 3)])
    ax.set_ylabel(units.label)
    ax.set_title("Typical day (AGP)", loc="left", fontweight="bold")
    ax.legend(loc="upper right", frameon=False)
    _style(ax)
    fig.tight_layout()
    return fig


# ---------------------------------------------------------------------------
# 4. Daily detail: glucose on top, basal + boluses below, one row per day
# ---------------------------------------------------------------------------
def plot_daily(glucose, basal=None, bolus=None, days: int = 7, units: Units = Units()):
    last_day = glucose.timestamp.max().normalize()
    day_list = [last_day - pd.Timedelta(days=i) for i in range(days)][::-1]

    fig, axes = plt.subplots(days, 1, figsize=(12, 2.6 * days), sharex=False)
    if days == 1:
        axes = [axes]

    for ax, day in zip(axes, day_list):
        end = day + pd.Timedelta(days=1)
        g = glucose[(glucose.timestamp >= day) & (glucose.timestamp < end)]
        ax.axhspan(units(TARGET_LOW), units(TARGET_HIGH), color=COLORS["band"], alpha=0.12)
        # Resample to 5 min so sensor gaps show as breaks, not fake straight lines
        line = g.set_index("timestamp")["glucose_mgdl"].resample("5min").mean()
        ax.plot(line.index, units(line.values), color=COLORS["line"], linewidth=1.2)
        ax.set_xlim(day, end)
        ax.set_ylim(units(40), units(max(300, g.glucose_mgdl.max() + 10 if len(g) else 300)))
        ax.set_ylabel(units.label)
        ax.set_title(day.strftime("%A %d %B"), loc="left", fontsize=10, fontweight="bold")
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
        _style(ax)

        # Insulin on a second axis underneath the glucose line
        if basal is not None or bolus is not None:
            ins = ax.twinx()
            ins.set_ylim(0, 12)
            ins.set_ylabel("insulin", color="grey", fontsize=8)
            ins.tick_params(axis="y", labelsize=7, colors="grey")
            ins.spines[["top"]].set_visible(False)
            if basal is not None and len(basal):
                b = basal[(basal.timestamp >= day - pd.Timedelta(days=1)) & (basal.timestamp < end)]
                if len(b):
                    # Carry the last rate through to midnight so the line doesn't stop early
                    b = pd.concat([b, pd.DataFrame({"timestamp": [end],
                                                    "basal_rate_u_per_hr": [b.basal_rate_u_per_hr.iloc[-1]]})])
                    ins.step(b.timestamp, b.basal_rate_u_per_hr, where="post",
                             color=COLORS["basal"], linewidth=1.2, label="Basal (U/h)")
            if bolus is not None and len(bolus):
                bo = bolus[(bolus.timestamp >= day) & (bolus.timestamp < end)]
                ins.vlines(bo.timestamp, 0, bo.bolus_units, color=COLORS["bolus"], linewidth=2.5, label="Bolus (U)")
                for t, u in zip(bo.timestamp, bo.bolus_units):
                    ins.text(t, u + 0.3, f"{u:g}", ha="center", fontsize=7, color=COLORS["bolus"])
            ins.set_xlim(day, end)

    handles = [
        plt.Line2D([], [], color=COLORS["line"], label="Glucose"),
        plt.Line2D([], [], color=COLORS["basal"], label="Basal (U/h)"),
        plt.Line2D([], [], color=COLORS["bolus"], linewidth=2.5, label="Bolus (U)"),
    ]
    fig.legend(handles=handles, loc="upper right", ncol=3, frameon=False)
    fig.tight_layout(rect=(0, 0, 1, 0.98))
    return fig


if __name__ == "__main__":
    from load import load_basal, load_bolus, load_glucose

    root = Path(__file__).resolve().parent.parent
    out = root / "reports"
    out.mkdir(exist_ok=True)

    glucose = load_glucose(root / "data/fake_glucose.csv")
    basal = load_basal(root / "data/fake_basal.csv")
    bolus = load_bolus(root / "data/fake_bolus.csv")

    plot_overview(glucose).savefig(out / "overview.png", dpi=120)
    plot_time_in_range(glucose).savefig(out / "time_in_range.png", dpi=120)
    plot_agp(glucose).savefig(out / "agp.png", dpi=120)
    plot_daily(glucose, basal, bolus, days=3).savefig(out / "daily.png", dpi=120)
    print(f"Saved 4 graphs to {out}")
