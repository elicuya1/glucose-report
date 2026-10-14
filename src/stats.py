"""
STEP 5a — The numbers behind the graphs.

Standard CGM summary metrics (the same ones used in clinic reports):
  - average glucose
  - GMI  (Glucose Management Indicator — an estimate of A1c from CGM data)
  - CV   (coefficient of variation — how much glucose swings; under 36% is considered stable)
  - Time in Range buckets
"""

import pandas as pd

# Standard ranges in mg/dL (international consensus targets)
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
