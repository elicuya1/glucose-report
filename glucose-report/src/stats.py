"""
STEP 5a — The numbers behind the graphs, plus a plain-language summary.

Standard CGM summary metrics:
  - average glucose
  - GMI  (Glucose Management Indicator — an estimate of A1c from CGM data)
  - CV   (coefficient of variation — how much glucose swings around the average)
  - Time in Range buckets

The plain-language notes only DESCRIBE the data. It never gives advice
or recommendations — those belong with your diabetes care team.
"""

import pandas as pd

# Standard ranges in mg/dL
RANGES = [
    ("Very low", 0, 54),
    ("Low", 54, 70),
    ("In range", 70, 181),
    ("High", 181, 251),
    ("Very high", 251, 10_000),
]


def time_in_ranges(glucose: pd.DataFrame) -> dict[str, float]:
    """Percent of readings in each range."""
    g = glucose["glucose_mgdl"]
    return {name: round(100 * ((g >= lo) & (g < hi)).mean(), 1) for name, lo, hi in RANGES}


def summary(glucose: pd.DataFrame) -> dict:
    g = glucose["glucose_mgdl"]
    days = (glucose.timestamp.max() - glucose.timestamp.min()).total_seconds() / 86400
    expected = max(days * 288, 1)          # a CGM gives 288 readings/day (every 5 min)
    mean = g.mean()
    return {
        "start": glucose.timestamp.min(),
        "end": glucose.timestamp.max(),
        "days": round(days, 1),
        "readings": len(g),
        "sensor_active_pct": round(min(100, 100 * len(g) / expected), 1),
        "mean_mgdl": round(mean),
        "gmi_pct": round(3.31 + 0.02392 * mean, 1),
        "cv_pct": round(100 * g.std() / mean, 1),
        "tir": time_in_ranges(glucose),
    }


# ---------------------------------------------------------------------------
# Plain-language summary
# ---------------------------------------------------------------------------
def _hours(pct: float) -> str:
    """Turn a % of the day into 'about 3 h 20 min a day'."""
    minutes = round(pct / 100 * 24 * 60)
    h, m = divmod(minutes, 60)
    if h and m:
        return f"about {h} h {m} min a day"
    if h:
        return f"about {h} h a day"
    return f"about {m} min a day"


def _fmt(mgdl: float, mmol: bool) -> str:
    return f"{mgdl / 18:.1f} mmol/L" if mmol else f"{mgdl:.0f} mg/dL"


def _hour_range(hour: int) -> str:
    return f"{hour:02d}:00 and {(hour + 1) % 24:02d}:00"


def daily_insulin(basal: pd.DataFrame | None, bolus: pd.DataFrame | None, start, end) -> dict:
    """Average basal and bolus units per day over the period (if data is available)."""
    out = {}
    days = max((end - start).total_seconds() / 86400, 1e-9)
    if bolus is not None and len(bolus):
        b = bolus[(bolus.timestamp >= start) & (bolus.timestamp <= end)]
        if len(b):
            out["bolus_per_day"] = b.bolus_units.sum() / days
            out["boluses_per_day"] = len(b) / days
    if basal is not None and len(basal):
        # Basal is a rate that stays the same until it changes: fill every 5 min, then add up
        rate = basal.set_index("timestamp")["basal_rate_u_per_hr"].sort_index()
        rate = rate[~rate.index.duplicated(keep="last")]
        grid = pd.date_range(start, end, freq="5min")
        filled = rate.reindex(rate.index.union(grid)).ffill().reindex(grid).dropna()
        if len(filled):
            out["basal_per_day"] = (filled * 5 / 60).sum() / days
    return out


def graph_notes(glucose, basal=None, bolus=None, unit: str = "mgdl") -> dict[str, list[str]]:
    """
    Plain-language descriptions to show UNDER each graph, keyed by graph:
    "overview", "tir", "agp", "daily". Descriptive only — no advice.
    """
    mmol = unit == "mmol"
    s = summary(glucose)
    tir = s["tir"]
    df = glucose.copy()
    df["hour"] = df.timestamp.dt.hour
    df["day"] = df.timestamp.dt.normalize()
    notes = {"overview": [], "tir": [], "agp": [], "daily": []}

    # --- Overview: average, GMI, data coverage -----------------------------
    notes["overview"].append(
        f"Average glucose was {_fmt(s['mean_mgdl'], mmol)} across {s['days']} days ({s['readings']} readings). "
        f"The sensor recorded data {s['sensor_active_pct']:.0f}% of the time; gaps show as breaks in the line "
        "and aren't counted in any of the numbers."
    )
    notes["overview"].append(
        f"GMI was {s['gmi_pct']}%. GMI estimates what an A1c lab test might show, using only the average glucose, "
        "so it can be different from a real lab A1c."
    )

    # --- Time in range: in, below, above -----------------------------------
    notes["tir"].append(
        f"{tir['In range']:.0f}% of readings were between {_fmt(70, mmol)} and {_fmt(180, mmol)}, "
        f"which is {_hours(tir['In range'])}."
    )
    below = tir["Very low"] + tir["Low"]
    lows = df[df.glucose_mgdl < 70]
    if len(lows):
        notes["tir"].append(
            f"{below:.1f}% were below {_fmt(70, mmol)} ({_hours(below)}), and {tir['Very low']:.1f}% were below "
            f"{_fmt(54, mmol)}. These readings showed up on {lows.day.nunique()} of {df.day.nunique()} days, "
            f"most often between {_hour_range(int(lows.hour.mode().iloc[0]))}."
        )
    else:
        notes["tir"].append(f"No readings were below {_fmt(70, mmol)}.")
    above = tir["High"] + tir["Very high"]
    highs = df[df.glucose_mgdl > 180]
    if len(highs):
        notes["tir"].append(
            f"{above:.0f}% were above {_fmt(180, mmol)} ({_hours(above)}), including {tir['Very high']:.0f}% above "
            f"{_fmt(250, mmol)}. These were most common between {_hour_range(int(highs.hour.mode().iloc[0]))}."
        )
    else:
        notes["tir"].append(f"No readings were above {_fmt(180, mmol)}.")

    # --- Typical day: time-of-day pattern + variability --------------------
    hourly = df.groupby("hour").glucose_mgdl
    median, spread = hourly.median(), hourly.quantile(0.75) - hourly.quantile(0.25)
    notes["agp"].append(
        f"The typical (median) value was highest between {_hour_range(int(median.idxmax()))} "
        f"and lowest between {_hour_range(int(median.idxmin()))}. Readings differed the most from day to day "
        f"between {_hour_range(int(spread.idxmax()))}, where the band is widest."
    )
    notes["agp"].append(
        f"Variability (CV) was {s['cv_pct']}%. CV measures how much glucose swung up and down compared with "
        "the average: a higher number means bigger swings, a lower number means steadier readings."
    )

    # --- Day by day: best / hardest day + insulin --------------------------
    per_day = df.groupby("day").agg(
        n=("glucose_mgdl", "size"),
        in_range=("glucose_mgdl", lambda g: 100 * ((g >= 70) & (g <= 180)).mean()),
    )
    per_day = per_day[per_day.n >= 144]          # skip days with less than half the readings
    if len(per_day) >= 2:
        best, worst = per_day.in_range.idxmax(), per_day.in_range.idxmin()
        notes["daily"].append(
            f"{best:%A %d %b} had the most time in range ({per_day.in_range[best]:.0f}%) and "
            f"{worst:%A %d %b} had the least ({per_day.in_range[worst]:.0f}%)."
        )
    ins = daily_insulin(basal, bolus, s["start"], s["end"])
    if ins:
        parts = []
        if "basal_per_day" in ins:
            parts.append(f"about {ins['basal_per_day']:.1f} units of basal")
        if "bolus_per_day" in ins:
            parts.append(f"about {ins['bolus_per_day']:.1f} units of bolus "
                         f"(around {ins['boluses_per_day']:.1f} boluses)")
        text = "On an average day the pump delivered " + " and ".join(parts) + "."
        if len(parts) == 2:
            text += f" That's about {ins['basal_per_day'] + ins['bolus_per_day']:.1f} units in total."
        notes["daily"].append(text)
    else:
        notes["daily"].append("No pump files were added, so insulin isn't shown.")
    return notes


DISCLAIMER = (
    "These notes only describe your data. They are not medical advice and do not "
    "suggest any changes. Talk to your diabetes care team before making decisions about your treatment."
)
