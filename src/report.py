"""
STEP 6 — The weekly report.

Puts the numbers and all the graphs into one HTML file you can open in any browser.

With fake data:
    python src/report.py

With your own exports:
    python src/report.py --glucose data/my_cgm.csv
    python src/report.py --glucose data/my_cgm.csv --basal data/basal.csv --bolus data/bolus.csv
    python src/report.py --glucose data/my_cgm.csv --days 14 --units mmol
"""

import argparse
import base64
import io
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

from load import load_basal, load_bolus, load_glucose
from plots import COLORS, Units, plot_agp, plot_daily, plot_overview, plot_time_in_range
from stats import summary

ROOT = Path(__file__).resolve().parent.parent


def fig_to_html(fig) -> str:
    """Turn a matplotlib figure into an <img> tag (embedded, so the report is one file)."""
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=110, bbox_inches="tight")
    plt.close(fig)
    data = base64.b64encode(buf.getvalue()).decode()
    return f'<img src="data:image/png;base64,{data}">'


def last_n_days(df, days):
    if df is None or df.empty:
        return df
    cutoff = df.timestamp.max() - pd.Timedelta(days=days)
    return df[df.timestamp > cutoff].reset_index(drop=True)


def build_report(glucose, basal, bolus, days, unit) -> str:
    units = Units(unit)
    glucose = last_n_days(glucose, days)
    basal = last_n_days(basal, days + 1)
    bolus = last_n_days(bolus, days)
    s = summary(glucose)

    def fmt(mgdl):
        return f"{units(mgdl):.1f}" if units.mmol else f"{mgdl:.0f}"

    tir_rows = "".join(
        f'<tr><td><span class="dot" style="background:{COLORS[name]}"></span>{name}</td><td>{pct}%</td></tr>'
        for name, pct in s["tir"].items()
    )
    insulin_line = ""
    if bolus is not None and len(bolus):
        per_day = bolus.bolus_units.sum() / max(s["days"], 1)
        insulin_line = f'<div class="card"><div class="big">{per_day:.1f} U</div><div>bolus per day</div></div>'

    return f"""<!doctype html>
<html><head><meta charset="utf-8"><title>Glucose report</title>
<style>
  body {{ font-family: system-ui, sans-serif; max-width: 1100px; margin: 32px auto; padding: 0 16px; color: #222; }}
  h1 {{ margin-bottom: 0; }}
  .sub {{ color: #666; margin-top: 4px; }}
  .cards {{ display: flex; gap: 12px; flex-wrap: wrap; margin: 24px 0; }}
  .card {{ background: #f4f6f9; border-radius: 10px; padding: 14px 18px; min-width: 130px; }}
  .big {{ font-size: 26px; font-weight: 700; }}
  .row {{ display: flex; gap: 24px; align-items: flex-start; flex-wrap: wrap; }}
  table {{ border-collapse: collapse; margin-top: 40px; }}
  td {{ padding: 6px 16px 6px 0; }}
  .dot {{ display: inline-block; width: 10px; height: 10px; border-radius: 50%; margin-right: 8px; }}
  img {{ max-width: 100%; margin: 12px 0; }}
  .note {{ color: #888; font-size: 13px; margin-top: 40px; border-top: 1px solid #ddd; padding-top: 12px; }}
</style></head>
<body>
  <h1>Glucose report</h1>
  <p class="sub">{s['start']:%d %b %Y} – {s['end']:%d %b %Y} · {s['days']} days · {s['readings']} readings · sensor active {s['sensor_active_pct']}%</p>

  <div class="cards">
    <div class="card"><div class="big">{s['tir']['In range']}%</div><div>time in range</div></div>
    <div class="card"><div class="big">{fmt(s['mean_mgdl'])}</div><div>average ({units.label})</div></div>
    <div class="card"><div class="big">{s['gmi_pct']}%</div><div>GMI (est. A1c)</div></div>
    <div class="card"><div class="big">{s['cv_pct']}%</div><div>variability (CV)</div></div>
    {insulin_line}
  </div>

  {fig_to_html(plot_overview(glucose, units))}
  <div class="row">
    {fig_to_html(plot_time_in_range(glucose, units))}
    <table>{tir_rows}</table>
  </div>
  {fig_to_html(plot_agp(glucose, units))}
  {fig_to_html(plot_daily(glucose, basal, bolus, days=min(days, 7), units=units))}

  <p class="note">For personal insight only — not medical advice. Don't make dosing decisions from this report; talk to your diabetes care team.</p>
</body></html>"""


def main():
    p = argparse.ArgumentParser(description="Build a glucose report from CSV exports.")
    p.add_argument("--glucose", default=ROOT / "data/fake_glucose.csv", help="CGM CSV export")
    p.add_argument("--basal", default=None, help="basal CSV (optional)")
    p.add_argument("--bolus", default=None, help="bolus CSV (optional)")
    p.add_argument("--days", type=int, default=7, help="how many recent days to include")
    p.add_argument("--units", choices=["mgdl", "mmol"], default="mgdl")
    p.add_argument("--out", default=ROOT / "reports/report.html")
    args = p.parse_args()

    # If you're using the fake data, pick up the fake insulin files automatically
    if Path(args.glucose).name == "fake_glucose.csv":
        args.basal = args.basal or ROOT / "data/fake_basal.csv"
        args.bolus = args.bolus or ROOT / "data/fake_bolus.csv"

    glucose = load_glucose(args.glucose)
    basal = load_basal(args.basal) if args.basal else None
    bolus = load_bolus(args.bolus) if args.bolus else None

    out = Path(args.out)
    out.parent.mkdir(exist_ok=True)
    out.write_text(build_report(glucose, basal, bolus, args.days, args.units), encoding="utf-8")
    print(f"Report saved to {out} — open it in your browser.")


if __name__ == "__main__":
    main()
