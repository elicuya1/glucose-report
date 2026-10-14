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
from stats import DISCLAIMER, daily_insulin, graph_notes, summary

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


def prepare(glucose, basal, bolus, days):
    """Keep only the last `days` days of each table (used by the report and the app)."""
    return last_n_days(glucose, days), last_n_days(basal, days + 1), last_n_days(bolus, days)


def build_report(glucose, basal, bolus, days, unit) -> str:
    units = Units(unit)
    glucose, basal, bolus = prepare(glucose, basal, bolus, days)
    s = summary(glucose)
    ins = daily_insulin(basal, bolus, s["start"], s["end"])
    notes = graph_notes(glucose, basal, bolus, unit)

    def fmt(mgdl):
        return f"{units(mgdl):.1f}" if units.mmol else f"{mgdl:.0f}"

    def stat(label, value, color):
        return (f'<div class="stat"><div class="label"><i style="background:{color}"></i>{label}</div>'
                f'<div class="value">{value}</div></div>')

    stats = [
        stat("Time in range", f"{s['tir']['In range']:.0f}%", COLORS["In range"]),
        stat(f"Average · {units.label}", fmt(s["mean_mgdl"]), COLORS["line"]),
        stat("GMI", f"{s['gmi_pct']}%", COLORS["basal"]),
        stat("Variability", f"{s['cv_pct']:.0f}%", COLORS["High"]),
    ]
    if ins:
        total = ins.get("basal_per_day", 0) + ins.get("bolus_per_day", 0)
        stats.append(stat("Insulin / day", f"{total:.1f} U", COLORS["bolus"]))

    tir_legend = "".join(
        f'<span><i style="background:{COLORS[name]}"></i>{name}<b>{pct}%</b></span>'
        for name, pct in s["tir"].items()
    )

    def section(title, how, body_html, key):
        text = "".join(f"<p>{t}</p>" for t in notes[key])
        return (f'<section class="card"><h2>{title}</h2>{body_html}'
                f'<div class="notes">{text}</div><p class="how">{how}</p></section>')

    lo, hi = fmt(70), fmt(180)
    return f"""<!doctype html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Glucose report</title>
<style>
  * {{ box-sizing: border-box; }}
  body {{ margin: 0; font-family: "Segoe UI", system-ui, sans-serif; color: #e8eaf2; min-height: 100vh;
          background: radial-gradient(1000px 600px at 90% -15%, rgba(124,92,246,0.30), transparent 65%), #0b0d16;
          background-attachment: fixed; }}
  main {{ max-width: 960px; margin: 0 auto; padding: 48px 20px 64px; }}
  h1 {{ margin: 0; font-size: 30px; font-weight: 600; letter-spacing: -0.01em; }}
  h1 span {{ color: #a78bfa; }}
  h2 {{ font-size: 16px; font-weight: 600; margin: 0 0 14px; }}
  .sub {{ color: #8b93ab; margin: 6px 0 0; font-size: 14px; }}
  .stats {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 12px; margin: 32px 0; }}
  .stat, .card {{ background: rgba(255,255,255,0.04); border: 1px solid rgba(255,255,255,0.08); border-radius: 16px;
                  backdrop-filter: blur(16px); -webkit-backdrop-filter: blur(16px); }}
  .stat {{ padding: 14px 16px; }}
  .label {{ color: #8b93ab; font-size: 13px; }}
  .value {{ font-size: 26px; font-weight: 600; margin-top: 4px; }}
  i {{ display: inline-block; width: 8px; height: 8px; border-radius: 50%; margin-right: 8px; vertical-align: 1px; }}
  .card {{ padding: 22px 24px; margin-bottom: 16px; }}
  .notes {{ margin-top: 14px; }}
  .notes p {{ margin: 0 0 8px; line-height: 1.6; color: #c9cfe0; font-size: 15px; }}
  .how {{ margin: 12px 0 0; padding-top: 12px; border-top: 1px solid rgba(255,255,255,0.07);
          color: #8b93ab; font-size: 13px; line-height: 1.5; }}
  .legend {{ display: flex; flex-wrap: wrap; gap: 8px 22px; margin-top: 12px; font-size: 14px; color: #c9cfe0; }}
  .legend b {{ color: #e8eaf2; font-weight: 600; margin-left: 4px; }}
  img {{ max-width: 100%; display: block; }}
  .disclaimer {{ color: #8b93ab; font-size: 13px; line-height: 1.5; margin-top: 28px; text-align: center; }}
</style></head>
<body><main>
  <h1>Glucose <span>Report</span></h1>
  <p class="sub">{s['start']:%d %b} – {s['end']:%d %b %Y} · {s['days']} days · {s['readings']} readings</p>

  <div class="stats">{"".join(stats)}</div>

  {section("Glucose overview",
           f"Every reading in this period, left to right. The green band is {lo}–{hi} {units.label}.",
           fig_to_html(plot_overview(glucose, units)), "overview")}

  {section("Time in range",
           "The bar adds up to 100% of readings, split into five ranges from very low (left) to very high (right).",
           fig_to_html(plot_time_in_range(glucose, units)) + f'<div class="legend">{tir_legend}</div>',
           "tir")}

  {section("Typical day",
           "All days stacked by time of day. The bright line is the median; the purple band holds half of all "
           "readings and the blue band holds 90%.",
           fig_to_html(plot_agp(glucose, units)), "agp")}

  {section("Day by day",
           "Blue line: glucose. Purple steps: basal rate (units per hour). Pink bars: boluses, labelled in units.",
           fig_to_html(plot_daily(glucose, basal, bolus, days=min(days, 7), units=units)), "daily")}

  <p class="disclaimer">{DISCLAIMER}</p>
</main></body></html>"""


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
