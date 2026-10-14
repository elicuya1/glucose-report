# glucose-report

Turn glucose (CGM) and insulin pump exports into a clear weekly report with graphs.
Built for my Tandem t:slim X2 setup, but works with any CSV that has timestamps and glucose values.

> **For personal insight only. Not medical advice.**
> Don't make insulin or dosing decisions based on this tool. Talk to your diabetes care team.

## What it makes

- **Glucose overview** – every reading over the period, with the 70–180 mg/dL target band
- **Time in Range** – % of time very low / low / in range / high / very high
- **AGP ("typical day")** – all days stacked by time of day: median + percentile bands
- **Daily detail** – glucose with basal and boluses underneath, one panel per day
- A one-page **HTML report** with the key numbers (average, GMI, variability, time in range)

## Quick start (with fake data, no real data needed)

```bash
pip install -r requirements.txt
python src/make_fake_data.py          # creates data/fake_glucose.csv, fake_basal.csv, fake_bolus.csv
python src/report.py                  # builds reports/report.html from the fake data
```

Open `reports/report.html` in your browser.

## Using your own data

1. Export a CSV from your CGM / pump software (e.g. Dexcom Clarity, Tandem Source, Glooko).
2. Put it in the `data/` folder.
3. Run:

```bash
python src/report.py --glucose data/my_export.csv
python src/report.py --glucose data/my_export.csv --days 14 --units mmol
```

`src/load.py` auto-detects common column names. If your file isn't recognised,
it prints the column names it found so you can add them to the lists at the top of `load.py`.

## Privacy

The `data/` and `reports/` folders are in `.gitignore`, so **your health data is never uploaded to GitHub**.
Only the code is public.

## Project structure

```
src/
  make_fake_data.py   # generates realistic fake CGM + insulin data
  load.py             # reads and cleans CSV exports
  stats.py            # average, GMI, CV, time in range
  plots.py            # all the graphs
  report.py           # puts everything into one HTML report
```
