"""
STEP 2 — Fake data generator.

Creates realistic-looking fake data so you can build and test every graph
without touching your real health data.

Run:  python src/make_fake_data.py
Makes: data/fake_glucose.csv   (a reading every 5 minutes, like a CGM)
       data/fake_basal.csv     (basal rate changes, units/hour)
       data/fake_bolus.csv     (meal and correction boluses, units)
"""

from pathlib import Path

import numpy as np
import pandas as pd

DAYS = 14                 # how many days of fake data
SEED = 42                 # same seed = same fake data every run
DATA_DIR = Path(__file__).resolve().parent.parent / "data"

rng = np.random.default_rng(SEED)


def make_glucose(start: pd.Timestamp) -> pd.DataFrame:
    """A CGM reading every 5 minutes: baseline + meal spikes + dawn rise + noise."""
    times = pd.date_range(start, periods=DAYS * 24 * 12, freq="5min")
    hours = times.hour + times.minute / 60
    glucose = np.full(len(times), 120.0)

    # Dawn phenomenon: gentle rise between 4am and 8am
    glucose += 25 * np.exp(-((hours - 7) ** 2) / 4)

    # Meals: each day gets breakfast, lunch, dinner at slightly random times
    for day in range(DAYS):
        for meal_hour, size in [(8, 70), (13.5, 60), (20, 80)]:
            meal_time = start + pd.Timedelta(days=day, hours=meal_hour + rng.normal(0, 0.5))
            spike = size * rng.uniform(0.5, 1.5)
            minutes_after = (times - meal_time).total_seconds() / 60
            after = minutes_after > 0
            # rises over ~60 min, comes back down over ~2-3 hours
            glucose[after] += spike * (minutes_after[after] / 60) * np.exp(1 - minutes_after[after] / 60)

        # Occasional low in the afternoon or night
        if rng.random() < 0.3:
            low_time = start + pd.Timedelta(days=day, hours=rng.choice([3, 16]))
            minutes_from = np.abs((times - low_time).total_seconds() / 60)
            glucose -= 60 * np.exp(-(minutes_from**2) / (2 * 40**2))

    # Slow random drift + sensor noise
    drift = np.cumsum(rng.normal(0, 1.2, len(times)))
    drift -= pd.Series(drift).rolling(288, min_periods=1).mean().to_numpy()
    glucose += drift + rng.normal(0, 4, len(times))

    glucose = np.clip(glucose, 40, 400).round()

    df = pd.DataFrame({"timestamp": times, "glucose_mgdl": glucose.astype(int)})

    # Real sensors have gaps (warm-up, signal loss) — drop a few chunks
    for _ in range(3):
        gap_start = rng.integers(0, len(df) - 30)
        df = df.drop(df.index[gap_start : gap_start + rng.integers(6, 30)], errors="ignore")
    return df.reset_index(drop=True)


def make_basal(start: pd.Timestamp) -> pd.DataFrame:
    """A basal profile that changes at set times each day (units/hour)."""
    profile = [(0, 0.75), (4, 0.95), (9, 0.8), (16, 0.85), (22, 0.7)]
    rows = []
    for day in range(DAYS):
        for hour, rate in profile:
            rows.append({
                "timestamp": start + pd.Timedelta(days=day, hours=hour),
                "basal_rate_u_per_hr": round(rate * rng.uniform(0.9, 1.1), 2),
            })
    return pd.DataFrame(rows)


def make_bolus(start: pd.Timestamp) -> pd.DataFrame:
    """Meal boluses plus the occasional correction (units)."""
    rows = []
    for day in range(DAYS):
        for meal_hour, units in [(7.9, 5), (13.4, 4.5), (19.9, 6)]:
            rows.append({
                "timestamp": start + pd.Timedelta(days=day, hours=meal_hour + rng.normal(0, 0.3)),
                "bolus_units": round(units * rng.uniform(0.7, 1.3), 1),
                "type": "meal",
            })
        if rng.random() < 0.5:
            rows.append({
                "timestamp": start + pd.Timedelta(days=day, hours=rng.uniform(10, 23)),
                "bolus_units": round(rng.uniform(0.5, 2.0), 1),
                "type": "correction",
            })
    return pd.DataFrame(rows).sort_values("timestamp").reset_index(drop=True)


def main():
    DATA_DIR.mkdir(exist_ok=True)
    start = pd.Timestamp.today().normalize() - pd.Timedelta(days=DAYS)

    glucose = make_glucose(start)
    basal = make_basal(start)
    bolus = make_bolus(start)

    glucose.to_csv(DATA_DIR / "fake_glucose.csv", index=False)
    basal.to_csv(DATA_DIR / "fake_basal.csv", index=False)
    bolus.to_csv(DATA_DIR / "fake_bolus.csv", index=False)

    print(f"Made {len(glucose)} glucose readings, {len(basal)} basal changes, {len(bolus)} boluses")
    print(f"Saved to {DATA_DIR}")


if __name__ == "__main__":
    main()
