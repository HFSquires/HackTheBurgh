"""Official market data (task T14): CPI uprating factors by COICOP division and retail-sales seasonality.

Reads the ONS series CSVs in data/ and writes:
    Analysis/market/cpi_uprating_factors.csv        latest CPI index / mean index over April 2024 to March 2025
    Figures/market/retail_sales_seasonality.{pdf,svg,md}

    python -X utf8 market_data.py           # write everything
    python -X utf8 market_data.py --check   # verify the written outputs against the data
"""
import argparse, csv, hashlib, math, re, statistics as st, subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATA, ANALYSIS, FIGURES = HERE / "data", HERE / "Analysis" / "market", HERE / "Figures" / "market"
FACTORS, FIG = ANALYSIS / "cpi_uprating_factors.csv", "retail_sales_seasonality"
CPI = {"D7BT": "00 All items", "D7BU": "01 Food and non-alcoholic beverages",
       "D7BV": "02 Alcoholic beverages, tobacco and narcotics", "D7BW": "03 Clothing and footwear",
       "D7BX": "04 Housing, water and fuels", "D7BY": "05 Furniture, household equipment and routine repair",
       "D7BZ": "06 Health", "D7C2": "07 Transport", "D7C3": "08 Communication", "D7C4": "09 Recreation and culture",
       "D7C5": "10 Education", "D7C6": "11 Hotels, cafes and restaurants", "D7C7": "12 Miscellaneous goods and services"}
RETAIL = "J5AH"
MONTHS = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]
REF = [(2024, m) for m in range(4, 13)] + [(2025, m) for m in range(1, 4)]  # Family Spending FYE 2025
YEARS = list(range(2021, 2026))  # complete calendar years; 2026 is partial
RETAIL_FILE = DATA / f"ons_drsi_retail_sales_value_nsa_{RETAIL}.csv"


def cpi_file(c):
    return DATA / f"ons_mm23_cpi_index_{c}.csv"


def read_series(path, cdid):
    """Return ({(year, month): value}, header dict). Asserts the CDID, then reads the monthly rows only."""
    rows = list(csv.reader(path.open(encoding="utf-8-sig")))
    head = {r[0]: r[1] for r in rows if len(r) == 2 and r[0] in ("Title", "CDID", "Source dataset ID", "Release date")}
    assert head["CDID"] == cdid, (path.name, head["CDID"])
    out = {}
    for r in rows:
        m = re.fullmatch(r"(\d{4}) ([A-Z]{3})", r[0])
        if m and m[2] in MONTHS:
            out[(int(m[1]), MONTHS.index(m[2]) + 1)] = float(r[1])
    return out, head


def factors():
    """One row per CPI series: reference-period mean, latest month, latest index and ratio."""
    data = {c: read_series(cpi_file(c), c) for c in CPI}
    latest = min(max(s) for s, _ in data.values())
    assert all(latest in s for s, _ in data.values()), "latest month missing in some series"
    rows = []
    for c, (s, head) in data.items():
        assert all(k in s for k in REF), c
        assert c == "D7BT" or f"CPI INDEX {CPI[c][:2]}" in head["Title"], (c, head["Title"])
        ref = st.mean(s[k] for k in REF)
        rows.append({"cdid": c, "division": CPI[c], "ref_mean_apr2024_mar2025": ref,
                     "latest_month": f"{latest[0]}-{latest[1]:02d}", "latest_index": s[latest],
                     "factor": s[latest] / ref, "release_date": head["Release date"]})
    return rows


def write_factors(rows):
    ANALYSIS.mkdir(parents=True, exist_ok=True)
    with FACTORS.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, list(rows[0]), lineterminator="\n")
        w.writeheader()
        for r in rows:
            w.writerow({k: f"{v:.4f}" if isinstance(v, float) else v for k, v in r.items()})


def seasonality():
    """Monthly values scaled per year so the calendar-year mean is 100. Returns (scaled, raw, header)."""
    s, head = read_series(RETAIL_FILE, RETAIL)
    raw = {y: [s[(y, m)] for m in range(1, 13)] for y in YEARS}
    return {y: [100 * v / st.mean(r) for v in r] for y, r in raw.items()}, raw, head


def mean_se(xs):
    return st.mean(xs), st.stdev(xs) / math.sqrt(len(xs))


def uplift(rel, years):
    """November and December uplift over the annual mean, per cent: {month index: (mean, SE)} across years."""
    return {m: mean_se([rel[y][m] - 100 for y in years]) for m in (10, 11)}


def md_table(head, body):
    return "\n".join(["| " + " | ".join(head) + " |", "|" + "---|" * len(head)] +
                     ["| " + " | ".join(map(str, r)) + " |" for r in body])


def git(*a):
    return subprocess.run(["git", *a], cwd=HERE, capture_output=True, text=True).stdout.strip() or "unknown"


def tables(rel):
    t1 = md_table(["Year"] + [m.title() for m in MONTHS], [[y] + [f"{v:.2f}" for v in rel[y]] for y in YEARS])
    t2 = md_table(["Month", "n (years)", "Mean", "SE"],
                  [[MONTHS[m].title(), len(YEARS), *[f"{x:.2f}" for x in mean_se([rel[y][m] for y in YEARS])]]
                   for m in range(12)])
    return t1, t2


def fmt(est):
    return f"({est[0]:.1f} ± {est[1]:.1f})%"


def figure(rel, head):
    import matplotlib.pyplot as plt
    import TeXFormat as tf
    plt.rcParams["svg.hashsalt"] = "t14"  # stable SVG ids
    ms = [mean_se([rel[y][m] for y in YEARS]) for m in range(12)]
    fig, ax = plt.subplots(figsize=(10, 6))
    for m in range(12):
        peak = m in (10, 11)
        tf.bar(ax, [m], [ms[m][0]], tf.CYCLE[1] if peak else tf.CYCLE[0], width=0.7, yerr=[ms[m][1]], capsize=3,
               label={0: "Other months", 10: "November and December"}.get(m))
    for y in YEARS:
        ax.scatter(range(12), rel[y], s=14, color="black", zorder=3,
                   label=f"Single years ({YEARS[0]} to {YEARS[-1]})" if y == YEARS[0] else None)
    ax.set_xticks(range(12), [x.title() for x in MONTHS])
    ax.set_ylim(80, max(max(v) for v in rel.values()) + 6)
    ax.set_xlabel("Month")
    ax.set_ylabel("Retail sales index [annual mean = 100]")
    ax.legend(frameon=True, fancybox=False, fontsize=tf.fontsizeSmall, loc="upper left")
    FIGURES.mkdir(parents=True, exist_ok=True)
    for ext in ("pdf", "svg"):
        fig.savefig(FIGURES / f"{FIG}.{ext}", bbox_inches="tight",
                    metadata={"pdf": {"CreationDate": None}, "svg": {"Date": None}}[ext])
    plt.close(fig)
    tfx = hashlib.sha256(Path(tf.__file__).read_bytes()).hexdigest()[:12]

    t1, t2 = tables(rel)
    up, up22 = uplift(rel, YEARS), uplift(rel, [y for y in YEARS if y >= 2022])
    (FIGURES / f"{FIG}.md").write_text(f"""# UK retail sales seasonality (non-seasonally adjusted)

Files: `{FIG}.pdf`, `{FIG}.svg` (this file: `{FIG}.md`), written by `market_data.py` (commit `{git('log', '-1', '--format=%h', '--', 'market_data.py')}` or later).

## Source data

[`data/{RETAIL_FILE.name}`](../../data/{RETAIL_FILE.name}): ONS Retail Sales Index (dataset {head['Source dataset ID']}), series `{RETAIL}`, "{head['Title']}",
Great Britain, value of sales (current prices), not seasonally adjusted, all retailers including automotive fuel, all
businesses. Release date shown: {head['Release date']}. The file's unit field is blank and the index base year is not
stated in it. Open Government Licence v3.0. Plot style: `TeXFormat.py` sha256 `{tfx}`.
Store-type breakdowns of the non-seasonally-adjusted value index are not published as index levels in DRSI (only as
percentage changes), so only the total is used.

## Filters, transformations and units

Monthly values for the complete calendar years {YEARS[0]} to {YEARS[-1]} (n = {len(YEARS)} years; 2026 is partial and
excluded). Within each year the 12 monthly values are divided by that year's mean and multiplied by 100, so every year
has mean 100 (this removes year-to-year growth in the level); the raw index values are in the data file. Bars: mean over
years of the scaled value; error bars: standard error of the mean over years (sample standard deviation divided by
sqrt(n)). Black points: single years. The {YEARS[0]} data include the early-2021 lockdown closures, which depress
January to April and so raise the other months relative to that year's mean.

## Plotted data

Scaled values (calendar-year mean = 100):

{t1}

Mean and SE across years:

{t2}

## n

{len(YEARS)} years for every month. The replicate is the calendar year (one published value per month and year).

## Descriptive statistics

Uplift of each month over its year's mean, in per cent (estimate ± SE across years):

| Period | November | December |
|---|---|---|
| {YEARS[0]} to {YEARS[-1]} (n = {len(YEARS)}) | {fmt(up[10])} | {fmt(up[11])} |
| 2022 to {YEARS[-1]} (n = {len(YEARS) - 1}, excludes 2021) | {fmt(up22[10])} | {fmt(up22[11])} |

## Fits and tests

Not applicable.

## Random seed

None.

## Interpretation

November sales exceed the annual monthly mean by {fmt(up[10])} and December sales by {fmt(up[11])} (years
{YEARS[0]} to {YEARS[-1]}). The figures describe retail sales as a whole, not any single category, and say nothing
about households' ability to pay.
""", encoding="utf-8")
    return up, up22


def check():
    rows = list(csv.DictReader(FACTORS.open(encoding="utf-8")))
    assert len(rows) == 13 and {r["cdid"] for r in rows} == set(CPI), "need 12 divisions plus all items"
    fresh = {r["cdid"]: r for r in factors()}
    for r in rows:
        f = float(r["factor"])
        assert 0.9 < f < 1.3, r
        assert abs(f - fresh[r["cdid"]]["factor"]) < 5e-5, r
    rel, raw, _ = seasonality()
    md = (FIGURES / f"{FIG}.md").read_text(encoding="utf-8")
    t1, t2 = tables(rel)
    assert t1 in md and t2 in md
    up = uplift(rel, YEARS)
    assert fmt(up[10]) in md and fmt(up[11]) in md
    for y in YEARS:
        assert abs(st.mean(rel[y]) - 100) < 1e-9 and all(v > 0 for v in raw[y])
    assert all((FIGURES / f"{FIG}.{e}").stat().st_size > 0 for e in ("pdf", "svg"))
    print(f"Check passed: 13 factors in (0.9, 1.3) and equal to a fresh calculation; .md tables match; "
          f"Nov {fmt(up[10])}, Dec {fmt(up[11])}.")


def main():
    import matplotlib.pyplot as plt
    import TeXFormat as tf
    plt.style.use(Path(tf.__file__).with_name("TeXFormat.mplstyle"))
    rows = factors()
    write_factors(rows)
    print(f"Latest CPI month {rows[0]['latest_month']}; reference April 2024 to March 2025")
    for r in rows:
        print(f"{r['cdid']} {r['division']:<52} {r['factor']:.4f}")
    rel, raw, head = seasonality()
    up, up22 = figure(rel, head)
    print("Uplift Nov", fmt(up[10]), "Dec", fmt(up[11]), "| 2022-25 Nov", fmt(up22[10]), "Dec", fmt(up22[11]))


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true")
    (check if ap.parse_args().check else main)()
