"""
STEP 4 — Load and clean exports.

Reads a CSV from your CGM or pump software and turns it into a tidy table
with standard column names, whatever the original file called them.

Test it on its own:
    python src/load.py data/fake_glucose.csv
    python src/load.py data/my_export.csv
"""

import sys
from pathlib import Path

import pandas as pd

# ---------------------------------------------------------------------------
# Column names different apps use. If your export isn't recognised,
# add its column name to the right list (lowercase).
# ---------------------------------------------------------------------------
TIME_COLUMNS = [
    "timestamp",
    "timestamp (yyyy-mm-ddthh:mm:ss)",     # Dexcom Clarity
    "eventdatetime",                        # older Tandem t:connect exports
    "device timestamp",                     # Libre
    "date time", "datetime", "time", "date",
]
GLUCOSE_COLUMNS = [
    "glucose_mgdl",
    "glucose value (mg/dl)",                # Dexcom Clarity (mg/dL)
    "glucose value (mmol/l)",               # Dexcom Clarity (mmol/L)
    "readings (cgm / bgm)",                 # older Tandem t:connect exports
    "historic glucose mg/dl",               # Libre
    "historic glucose mmol/l",              # Libre
    "glucose", "bg", "sgv", "value",
]
BASAL_COLUMNS = ["basal_rate_u_per_hr", "basal rate (u/h)", "basal rate", "rate", "basal"]
BOLUS_COLUMNS = ["bolus_units", "insulin delivered", "bolus volume delivered (u)", "bolus", "units", "insulin"]
# Optional bolus details — used to tell meal boluses from corrections
BOLUS_TYPE_COLUMNS = ["type", "bolus type", "bolustype", "bolus_type"]
CARB_COLUMNS = ["carbs", "carbs (g)", "carb size", "carbsize", "carbohydrates", "carbs_g"]

# Text values CGMs write instead of numbers when out of range
TEXT_VALUES = {"low": 39, "high": 401, "lo": 39, "hi": 401}


def _find_column(df: pd.DataFrame, candidates: list[str], what: str, path: Path) -> str:
    lookup = {c.strip().lower(): c for c in df.columns}
    for name in candidates:
        if name in lookup:
            return lookup[name]
    raise ValueError(
        f"Couldn't find a {what} column in {path.name}.\n"
        f"Columns in the file: {list(df.columns)}\n"
        f"Add the right one to the {what.upper()}_COLUMNS list at the top of src/load.py."
    )


def _read_csv(path: Path) -> pd.DataFrame:
    """Some exports have a few lines of header text before the real table.
    Try skipping 0, 1, 2... lines until we find a recognisable time column."""
    for skip in range(0, 15):
        try:
            df = pd.read_csv(path, skiprows=skip, sep=None, engine="python")
        except Exception:
            continue
        cols = [str(c).strip().lower() for c in df.columns]
        if any(c in cols for c in TIME_COLUMNS):
            return df
    return pd.read_csv(path)  # fall back; the column check will explain what's wrong


def _clean_times(series: pd.Series) -> pd.Series:
    times = pd.to_datetime(series, errors="coerce", format="mixed")
    if times.dt.tz is not None:
        times = times.dt.tz_localize(None)
    return times


def load_glucose(path: str | Path) -> pd.DataFrame:
    """Returns a table with columns: timestamp, glucose_mgdl (sorted, no duplicates)."""
    path = Path(path)
    df = _read_csv(path)

    # Dexcom Clarity mixes in other events (alerts, calibrations) — keep only sensor readings
    event_col = next((c for c in df.columns if c.strip().lower() == "event type"), None)
    if event_col:
        df = df[df[event_col].astype(str).str.upper() == "EGV"]

    time_col = _find_column(df, TIME_COLUMNS, "time", path)
    gluc_col = _find_column(df, GLUCOSE_COLUMNS, "glucose", path)

    raw = df[gluc_col].astype(str).str.strip().str.lower()
    values = pd.to_numeric(raw, errors="coerce")

    # If the file is in mmol/L, convert to mg/dL (everything inside the app uses mg/dL)
    if "mmol" in gluc_col.lower() or values.median() < 30:
        values = values * 18.0

    # Swap "Low"/"High" text for numbers AFTER converting units (they're already in mg/dL)
    values = values.fillna(raw.map(TEXT_VALUES))

    out = pd.DataFrame({"timestamp": _clean_times(df[time_col]), "glucose_mgdl": values})
    out = out.dropna().drop_duplicates("timestamp").sort_values("timestamp").reset_index(drop=True)

    if out.empty:
        raise ValueError(f"No usable glucose readings found in {path.name}.")
    return out


def load_basal(path: str | Path) -> pd.DataFrame:
    """Returns: timestamp, basal_rate_u_per_hr."""
    path = Path(path)
    df = _read_csv(path)
    time_col = _find_column(df, TIME_COLUMNS, "time", path)
    rate_col = _find_column(df, BASAL_COLUMNS, "basal", path)
    out = pd.DataFrame({
        "timestamp": _clean_times(df[time_col]),
        "basal_rate_u_per_hr": pd.to_numeric(df[rate_col], errors="coerce"),
    })
    return out.dropna().sort_values("timestamp").reset_index(drop=True)


def _optional_column(df: pd.DataFrame, candidates: list[str]):
    lookup = {c.strip().lower(): c for c in df.columns}
    return next((lookup[n] for n in candidates if n in lookup), None)


def load_bolus(path: str | Path) -> pd.DataFrame:
    """
    Returns: timestamp, bolus_units, kind.
    kind is "meal", "correction", or None if the file doesn't say.
    """
    path = Path(path)
    df = _read_csv(path)
    time_col = _find_column(df, TIME_COLUMNS, "time", path)
    units_col = _find_column(df, BOLUS_COLUMNS, "bolus", path)
    out = pd.DataFrame({
        "timestamp": _clean_times(df[time_col]),
        "bolus_units": pd.to_numeric(df[units_col], errors="coerce"),
    })

    # Work out meal vs correction from carbs (best) or a bolus-type column
    carb_col = _optional_column(df, CARB_COLUMNS)
    type_col = _optional_column(df, BOLUS_TYPE_COLUMNS)
    kind = pd.Series([None] * len(df), index=df.index, dtype=object)
    if carb_col:
        carbs = pd.to_numeric(df[carb_col], errors="coerce").fillna(0)
        kind[:] = ["meal" if c > 0 else "correction" for c in carbs]
    elif type_col:
        text = df[type_col].astype(str).str.lower()
        kind[text.str.contains("meal|carb|food")] = "meal"
        kind[kind.isna() & text.str.contains("correct")] = "correction"
    out["kind"] = kind

    out = out.dropna(subset=["timestamp", "bolus_units"])
    return out[out["bolus_units"] > 0].sort_values("timestamp").reset_index(drop=True)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python src/load.py data/your_file.csv")
        sys.exit(1)
    data = load_glucose(sys.argv[1])
    print(data.head(10))
    print(f"\n{len(data)} readings from {data.timestamp.min()} to {data.timestamp.max()}")
