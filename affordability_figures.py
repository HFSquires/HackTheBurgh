"""Pitch figures from the affordability engine over the 100 mock statements (task T07b).

Calls affordability.py (parse, assess, personas) for every persona in Analysis/mock_statements/ with the default
`today` (the day after each statement's last transaction) and writes:
    Analysis/affordability/households.csv                 one row per persona
    Figures/affordability/affordability_by_price.{pdf,svg,md}
    Figures/affordability/safe_to_spend_vs_income.{pdf,svg,md}
    Analysis/value/savings_comparison.csv, Figures/value/savings_comparison.{pdf,svg,md}   (catalogue products; task T15)

    python -X utf8 affordability_figures.py           # write everything
    python -X utf8 affordability_figures.py --check   # verify the written outputs against fresh engine calls
"""
import argparse, datetime as dt, hashlib, io, math, re, subprocess
from pathlib import Path

import pandas as pd

import affordability as af

HERE = Path(__file__).resolve().parent
ANALYSIS, FIGURES = HERE / "Analysis" / "affordability", HERE / "Figures" / "affordability"
CSV = ANALYSIS / "households.csv"
PRICES = [50, 100, 200, 300, 500, 750, 1000, 1500]
CATS = ["payNow", "bnplPlainOnly", "neither"]
CAT_LABEL = {"payNow": "Can pay now (or with the BNPL pot)", "bnplPlainOnly": "Only with plain pay-in-3",
             "neither": "Neither"}
TENURES = ["Owned outright", "Social rented", "Private rented"]
F1, F2 = "affordability_by_price", "safe_to_spend_vs_income"
VALUE_A, VALUE_F, F3 = HERE / "Analysis" / "value", HERE / "Figures" / "value", "savings_comparison"
SAVE_DAY = dt.date(2026, 11, 7)  # the day the catalogue prices were collected; Bank Rate in force that day
CASHBACK = 0.01  # assumed cashback rate of a cashback credit card; not from any product in data/
SAVINGS = {"cheapest_saving": "Buying at the cheapest mainstream price", "cashback": r"1\% cashback card (assumed rate)",
           "pot": "Pay-in-3 float interest (pot)", "card": "Credit-card float interest"}


def outcome(a):
    o = {x["kind"]: x for x in a["options"]}
    return "payNow" if o["payNow"]["affordable"] else "bnplPlainOnly" if o["bnplPlain"]["affordable"] else "neither"


def build():
    """Run the engine for every persona and price; return (DataFrame, one sample engine output)."""
    rows, sample, asofs = [], None, set()
    for p in af.personas():
        tx = af.parse(af.load_persona(p["id"]))
        asofs.add(tx[-1]["date"].isoformat())
        out = {pr: af.assess(tx, pr) for pr in PRICES}
        a = out[PRICES[0]]
        assert a["income"], f"{p['id']}: no salary detected"
        sample = sample or a
        rows.append({"id": p["id"], "tenure": p["tenure"], "region": p["region"], "household": p["household"],
                     "income": a["income"]["monthly"], "nextPayday": a["income"]["nextPayday"],
                     "balance": a["balance"], "safeToSpendBeforeEverydaySpending": a["safeToSpendBeforeEverydaySpending"],
                     "predictedSpendingMean": a["predictedSpendingUntilPayday"]["mean"], "safeToSpend": a["safeToSpend"],
                     "monthly.leftOver": a["monthly"]["leftOver"],
                     **{f"outcome_{pr}": outcome(out[pr]) for pr in PRICES}})
    sample["asOfRange"] = f"`{min(asofs)}` to `{max(asofs)}`; `today` is the day after each"
    return pd.DataFrame(rows), sample


def counts(df):
    return {pr: [int((df[f"outcome_{pr}"] == c).sum()) for c in CATS] for pr in PRICES}


def spearman(x, y):
    """Spearman rho (average ranks for ties) and a two-sided p-value.
    ponytail: p from the large-sample normal approximation z = rho * sqrt(n - 1), adequate at n = 100; use
    scipy.stats.spearmanr (t approximation) or a permutation test for small n."""
    rho = float(x.rank().corr(y.rank()))  # Pearson on average ranks = Spearman
    return rho, math.erfc(abs(rho) * math.sqrt(len(x) - 1) / math.sqrt(2))


def summary(s):
    q1, med, q3 = s.quantile([0.25, 0.5, 0.75])
    return [str(len(s)), f"{med:.2f}", f"{q1:.2f}", f"{q3:.2f}", f"{q3 - q1:.2f}", f"{s.min():.2f}", f"{s.max():.2f}",
            str(int((s < 0).sum()))]


def tenure_table(df, col):
    head = ["Group", "n", "Median", "Q1", "Q3", "IQR", "Min", "Max", "n below 0"]
    body = [["All"] + summary(df[col])] + [[t] + summary(df.loc[df.tenure == t, col]) for t in TENURES]
    return md_table(head, body)


def md_table(head, body):
    return "\n".join(["| " + " | ".join(head) + " |", "|" + "---|" * len(head)] +
                     ["| " + " | ".join(map(str, r)) + " |" for r in body])


def git(*args):
    return subprocess.run(["git", *args], cwd=HERE, capture_output=True, text=True).stdout.strip() or "unknown"


def provenance():
    import TeXFormat as tf
    dirty = " (with uncommitted changes)" if git("status", "--porcelain", "affordability.py") != "unknown" else ""
    tfx = hashlib.sha256(Path(tf.__file__).read_bytes()).hexdigest()[:12]
    return (f"The 100 statement CSVs in [`Analysis/mock_statements/`](../../Analysis/mock_statements/) (last changed "
            f"in commit `{git('log', '-1', '--format=%h', '--', 'Analysis/mock_statements')}`), read by "
            f"`affordability.py` at commit `{git('log', '-1', '--format=%h', '--', 'affordability.py')}`{dirty} (with "
            f"`bayes.py` at commit `{git('log', '-1', '--format=%h', '--', 'bayes.py')}` for everyday spending), "
            f"called by `affordability_figures.py` (commit `{git('log', '-1', '--format=%h', '--', 'affordability_figures.py')}`"
            f" or later). Tenure, region and household type from `Analysis/mock_statements/personas.md` via "
            f"`affordability.personas()`. Plot style: `TeXFormat.py` sha256 `{tfx}`.")


def rules(sample):
    note = next(n for n in next(o for o in sample["options"] if o["kind"] == "bnplPot")["notes"] if "same money" in n)
    return f"""`safeToSpendDefinition`, copied from the engine output: "{sample['safeToSpendDefinition']}"

`predictedSpendingUntilPayday.definition`: "{sample['predictedSpendingUntilPayday']['definition']}"

Since task T15, safe-to-spend deducts the predicted everyday spending until payday (Bayesian posterior predictive mean);
before T15 it did not, and the earlier counts were correspondingly generous.

`affordableDefinition`, copied from the engine output: "{sample['affordableDefinition']}"

`monthly.definition`, copied from the engine output: "{sample['monthly']['definition']}"

Option rules in `assess()` for a price P (instalments are P/3, rounded to the penny, the first due on `today` and the
others one and two months later). `payNow` is affordable when `safeToSpend - P >= 0`. `bnplPot` and `cardPaidInFull`
are affordable under the same condition; the engine's note on the pot reads: "{note}" `bnplPlain` is affordable when
`safeToSpend` minus the instalments due before `nextPayday` is at least 0 and `monthly.leftOver - P/3 >= 0` (T15; before
T15 the second test used `monthly.afterCommitted`, which does not deduct everyday spending). The `card0` option has no
data and is not used here. `today` is the engine default, the day after each statement's last transaction (asOf)."""


def write_csv(df):
    ANALYSIS.mkdir(parents=True, exist_ok=True)
    df.to_csv(CSV, index=False, float_format="%.2f", lineterminator="\n")


def fig_price(df, sample):
    import matplotlib.pyplot as plt
    import TeXFormat as tf
    c, x = counts(df), range(len(PRICES))
    fig, ax = plt.subplots(figsize=(10, 7))
    bottom = [0] * len(PRICES)
    for k, cat in enumerate(CATS):
        h = [c[pr][k] for pr in PRICES]
        tf.bar(ax, x, h, tf.CYCLE[k], width=0.8, bottom=bottom, label=CAT_LABEL[cat])
        for i, (b, v) in enumerate(zip(bottom, h)):
            if v >= 4:
                ax.text(i, b + v / 2, str(v), ha="center", va="center", fontsize=tf.fontsizeTiny)
        bottom = [b + v for b, v in zip(bottom, h)]
    ax.set_xticks(list(x), [f"{pr:,}" for pr in PRICES])
    ax.set_xlabel("Purchase price [GBP]")
    ax.set_ylabel("Households [count]")
    ax.set_ylim(0, 100)
    ax.legend(frameon=True, fancybox=False, fontsize=tf.fontsizeSmall, loc="lower center", bbox_to_anchor=(0.5, 1.02),
              ncol=1)
    save(fig, F1)

    tab = md_table(["Price [GBP]"] + [f"{CAT_LABEL[k]} (`{k}`)" for k in CATS] + ["Total"],
                   [[f"{pr:,}"] + c[pr] + [sum(c[pr])] for pr in PRICES])
    lo, hi = PRICES[0], PRICES[-1]
    (FIGURES / f"{F1}.md").write_text(f"""# Affordability by purchase price

Files: `{F1}.pdf`, `{F1}.svg` (this file: `{F1}.md`), written by `affordability_figures.py`.

## Source data

{provenance()}

## Filters, transformations and units

No persona is excluded (n = {len(df)}). For each persona, `assess(parse(csv), P)` is called once per test price
P in GBP ({', '.join(f'{p:,}' for p in PRICES)}). Each persona is put in one category per price: `payNow` if the
`payNow` option is affordable (equivalently `bnplPot`, which the engine marks affordable exactly when `payNow` is);
`bnplPlainOnly` if `bnplPlain` is affordable but `payNow` is not; otherwise `neither`. Bars are stacked counts of
households out of {len(df)}. Counts of 4 or more are printed on the bars. asOf ranges from {sample['asOfRange']}.

## Definitions

{rules(sample)}

## Plotted data

{tab}

Per-persona categories: [`Analysis/affordability/households.csv`](../../Analysis/affordability/households.csv)
(columns `outcome_<price>`).

## n

{len(df)} households at every price; the n of each stacked segment is the count in the table.

## Descriptive statistics

Counts only, as tabulated. Error bars: not applicable.

## Fits and tests

Not applicable.

## Random seed

None (the engine is deterministic; the mock statements were generated with the seed recorded in
`Analysis/mock_statements/personas.md`).

## Interpretation

At GBP {lo:,}, {c[lo][0]} of {len(df)} households can pay now, {c[lo][1]} only with plain pay-in-3 and {c[lo][2]}
neither. At GBP {hi:,}, the counts are {c[hi][0]}, {c[hi][1]} and {c[hi][2]}. Safe-to-spend deducts the predicted
everyday spending until payday, so a household counted under `payNow` is expected to stay at or above zero until payday
on average; `shortfallProbability` in the engine output gives the chance that it does not. The mock statements are
synthetic, so the counts describe the generator's households, not real customers.
""", encoding="utf-8")


def fig_income(df, sample):
    import matplotlib.pyplot as plt
    import TeXFormat as tf
    fig, axes = plt.subplots(1, 2, figsize=(16, 7), sharex=True)
    for ax, col, lab in zip(axes, ["safeToSpend", "monthly.leftOver"],
                            ["Safe to spend [GBP]", "Monthly left over [GBP]"]):
        for k, t in enumerate(TENURES):
            d = df[df.tenure == t]
            ax.scatter(d.income, d[col], s=45, color=tf.CYCLE[k], marker="os^"[k], label=f"{t} ($n = {len(d)}$)")
        ax.axhline(0, color="black", linewidth=1)
        ax.set_xlabel("Monthly net income [GBP]")
        ax.set_ylabel(lab)
    axes[0].legend(frameon=True, fancybox=False, fontsize=tf.fontsizeSmall, loc="upper left")
    fig.tight_layout()
    save(fig, F2)

    stats = {col: spearman(df.income, df[col]) for col in ["safeToSpend", "monthly.leftOver"]}
    s, l = df.safeToSpend, df["monthly.leftOver"]
    ns = " ".join(f"{t}: {int((df.tenure == t).sum())}." for t in TENURES)
    (FIGURES / f"{F2}.md").write_text(f"""# Safe to spend and monthly left over against monthly net income

Files: `{F2}.pdf`, `{F2}.svg` (this file: `{F2}.md`), written by `affordability_figures.py`. Left panel:
`safeToSpend`; right panel: `monthly.leftOver`; both against income, coloured by tenure, with a line at 0.

## Source data

{provenance()}

## Filters, transformations and units

No persona is excluded (n = {len(df)}). x = `income.monthly`, the latest salary credit detected on the statement (net
pay) [GBP]. y = `safeToSpend` [GBP] and `monthly.leftOver` [GBP] from `assess()` (both independent of the price; the
values come from the call at GBP {PRICES[0]}). Tenure is the sampled tenure in `personas.md`. asOf ranges from
{sample['asOfRange']}. Quartiles are linearly interpolated (pandas `quantile`).

## Definitions

{rules(sample)}

## Plotted data

One point per household; all values in
[`Analysis/affordability/households.csv`](../../Analysis/affordability/households.csv) (columns `income`,
`safeToSpend`, `monthly.leftOver`, `tenure`). Income ranges from {df.income.min():.2f} to {df.income.max():.2f} GBP
(median {df.income.median():.2f}).

## n

All: {len(df)}. {ns}

## Descriptive statistics

`safeToSpend` [GBP]:

{tenure_table(df, 'safeToSpend')}

`monthly.leftOver` [GBP]:

{tenure_table(df, 'monthly.leftOver')}

Error bars: not applicable (none drawn).

## Fits and tests

Spearman rank correlation with income (average ranks for ties; two-sided p-value from the normal approximation
z = rho sqrt(n - 1)), n = {len(df)}. At rho this large the normal and Student t approximations give very different
p-values; read p only as far below 0.001.

| y | rho | p |
|---|---|---|
| `safeToSpend` | {stats['safeToSpend'][0]:.3f} | {stats['safeToSpend'][1]:.3g} |
| `monthly.leftOver` | {stats['monthly.leftOver'][0]:.3f} | {stats['monthly.leftOver'][1]:.3g} |

No fit is drawn.

## Random seed

None (the engine is deterministic; the mock statements were generated with the seed recorded in
`Analysis/mock_statements/personas.md`).

## Interpretation

Median `safeToSpend` is {s.median():.2f} GBP (IQR {s.quantile(.75) - s.quantile(.25):.2f}); {int((s < 0).sum())} of
{len(df)} households are below 0. Median `monthly.leftOver` is {l.median():.2f} GBP; {int((l < 0).sum())} are below 0.
The Spearman correlation of `safeToSpend` with income is {stats['safeToSpend'][0]:.3f}. `safeToSpend` deducts the
predicted everyday spending until payday (median {df.predictedSpendingMean.median():.2f} GBP); the mock end balances
are still on the high side because several ONS spending items are excluded (`Analysis/mock_statements/README.md`).
""", encoding="utf-8")
    return stats


def savings():
    """One row per catalogue product, at its dearest mainstream price D: the money saved [GBP] by the cheapest mainstream
    price, a CASHBACK card, the pay-in-3 pot's float interest and a credit card cleared in full, all as the engine
    computes them (af.pay_in_3, af.pot_interest, af.card_interest, af.rate_on) for a purchase on SAVE_DAY."""
    rate_day, rate = af.rate_on(SAVE_DAY)
    rows = []
    for pid in sorted({r["product_id"] for r in af.catalogue()}):
        main = [r for r in af.catalogue() if r["product_id"] == pid and r["retailer"] in af.MAINSTREAM]
        hi, lo = max(r["price"] for r in main), min(r["price"] for r in main)
        rows.append(dict(product_id=pid, product=main[0]["product_name"], n_mainstream_prices=len(main),
                         dearest_retailers="; ".join(r["retailer"] for r in main if r["price"] == hi), dearest=hi,
                         cheapest_retailers="; ".join(r["retailer"] for r in main if r["price"] == lo), cheapest=lo,
                         bank_rate=rate, bank_rate_date=rate_day.isoformat(),
                         cheapest_saving=af.money(hi - lo), cashback=af.money(CASHBACK * hi),
                         pot=af.pot_interest(hi, SAVE_DAY, af.pay_in_3(hi, SAVE_DAY), rate), card=af.card_interest(hi, rate)))
    return pd.DataFrame(rows)


def savings_table(sv):
    return md_table(["Product", "n mainstream prices", "Dearest mainstream [GBP] (retailer)",
                     "Cheapest mainstream [GBP] (retailer)"] + [f"{SAVINGS[k].replace(chr(92), '')} [GBP]" for k in SAVINGS],
                    [[f"{r.product_id} {r.product}", r.n_mainstream_prices, f"{r.dearest:.2f} ({r.dearest_retailers})",
                      f"{r.cheapest:.2f} ({r.cheapest_retailers})"] + [f"{r[k]:.2f}" for k in SAVINGS]
                     for _, r in sv.iterrows()])


def fig_savings(sv):
    import matplotlib.pyplot as plt
    import TeXFormat as tf
    VALUE_A.mkdir(parents=True, exist_ok=True)
    VALUE_F.mkdir(parents=True, exist_ok=True)
    sv.to_csv(VALUE_A / f"{F3}.csv", index=False, float_format="%.2f", lineterminator="\n")
    fig, ax = plt.subplots(figsize=(12, 7))
    w = 0.2
    for k, key in enumerate(SAVINGS):
        x = [i + (k - 1.5) * w for i in range(len(sv))]
        tf.bar(ax, x, sv[key], tf.CYCLE[k], width=w, label=SAVINGS[key])
        for xi, v in zip(x, sv[key]):
            ax.text(xi, v + 2, f"{v:.2f}", ha="center", va="bottom", rotation=90, fontsize=tf.fontsizeTiny)
    ax.set_xticks(range(len(sv)), [f"{r.product_id}\n\\pounds{r.dearest:,.2f}" for _, r in sv.iterrows()])
    ax.set_xlabel("Product and dearest mainstream price")
    ax.set_ylabel("Money saved [GBP]")
    ax.set_ylim(0, sv[list(SAVINGS)].to_numpy().max() * 1.3)
    ax.legend(frameon=True, fancybox=False, fontsize=tf.fontsizeSmall, loc="upper left")
    save(fig, F3, VALUE_F)
    tot = {k: sv[k].sum() for k in SAVINGS}
    rate = sv.bank_rate.iloc[0]
    (VALUE_F / f"{F3}.md").write_text(f"""# Money saved on each catalogue product, by source

Files: `{F3}.pdf`, `{F3}.svg` (this file: `{F3}.md`), written by `affordability_figures.py` (task T15).

## Source data

[`data/{af.CATALOGUE.name}`](../../data/{af.CATALOGUE.name}) (retailer prices collected on {SAVE_DAY:%d %B %Y}; mainstream
retailers: {', '.join(af.MAINSTREAM)}; marketplace and third-party sellers are excluded) and
[`data/{af.BANK_RATE.name}`](../../data/{af.BANK_RATE.name}) (Bank of England Bank Rate, series IUDBEDR), via
`affordability.py` at commit `{git('log', '-1', '--format=%h', '--', 'affordability.py')}` and `affordability_figures.py`
at commit `{git('log', '-1', '--format=%h', '--', 'affordability_figures.py')}` or later. Plotted data:
[`Analysis/value/{F3}.csv`](../../Analysis/value/{F3}.csv).

## Filters, transformations and units

All five catalogue products (n = {len(sv)}), each at its dearest mainstream price D [GBP] for a purchase on
{SAVE_DAY.isoformat()}; Bank Rate in force that day: {rate:.2f}% a year (from {sv.bank_rate_date.iloc[0]}). Definitions,
all in GBP and rounded to pence:

| Bar | Definition |
|---|---|
| {SAVINGS['cheapest_saving'].replace(chr(92), '')} | D minus the cheapest mainstream price for the same product (0 when only one mainstream price is listed or all are equal) |
| {SAVINGS['cashback'].replace(chr(92), '')} | {CASHBACK:.0%} of D. The rate is an assumption for illustration, not taken from any card in `data/` |
| {SAVINGS['pot']} | Interest the pay-in-3 pot would earn: D goes into an easy-access pot on the purchase day and three instalments of D/3 leave it on that day and one and two months later; simple daily interest at Bank Rate on the declining balance, 365-day year (`affordability.pot_interest`) |
| {SAVINGS['card']} | Interest on D left in an easy-access account for an assumed {af.CARD_DAYS}-day average interest-free period before the card is cleared in full, at Bank Rate (`affordability.card_interest`) |

Bank Rate stands in for an easy-access savings rate; real rates vary. No tax on interest is deducted. The four sources
are not mutually exclusive (one could buy at the cheapest price with a cashback card and earn float interest), so the
bars are not to be added within a product unless a buyer could combine them. Bars are grouped by product; the value of
each bar is printed above it.

## Plotted data

{savings_table(sv)}

## n

{len(sv)} products; one value per product and source (no replicates). The number of mainstream prices behind the
dearest and cheapest prices is given per product.

## Descriptive statistics

Totals over the five products [GBP]: {', '.join(f"{SAVINGS[k].replace(chr(92), '')} {tot[k]:.2f}" for k in SAVINGS)}.
Error bars: not applicable (each value is a single calculation from one collected price).

## Fits and tests

Not applicable.

## Random seed

None.

## Interpretation

Over the five products, buying at the cheapest mainstream price instead of the dearest saves {tot['cheapest_saving']:.2f} GBP
in total, an assumed {CASHBACK:.0%} cashback {tot['cashback']:.2f} GBP, the pay-in-3 pot's float interest
{tot['pot']:.2f} GBP and a credit card cleared in full {tot['card']:.2f} GBP, at Bank Rate {rate:.2f}%. For
{', '.join(sv.product_id[sv.cheapest_saving == 0])} the catalogue lists no price difference between mainstream retailers,
so only the other three sources save money. The float interest on a few hundred pounds over one to two months is a
few pounds at most. These are facts about five products on one day, not a recommendation.
""", encoding="utf-8")


def save(fig, name, folder=FIGURES):
    import matplotlib.pyplot as plt
    folder.mkdir(parents=True, exist_ok=True)
    for ext in ("pdf", "svg"):
        fig.savefig(folder / f"{name}.{ext}", bbox_inches="tight",  # no dates: SVG reruns identical
                    metadata={"pdf": {"CreationDate": None}, "svg": {"Date": None}}[ext])
    plt.close(fig)


def check():
    """Verify the written outputs: counts, spot-checked engine flags, and the .md tables against the CSV."""
    df = pd.read_csv(CSV)
    assert len(df) == 100 and df.id.is_unique, len(df)
    c = counts(df)
    assert all(sum(v) == len(df) for v in c.values()), c
    for pid in ("persona001", "persona037", "persona073", "persona100"):  # spot checks against the engine
        tx, row = af.parse(af.load_persona(pid)), df[df.id == pid].iloc[0]
        for pr in PRICES:
            a = af.assess(tx, pr)
            o = {x["kind"]: x["affordable"] for x in a["options"]}
            got = row[f"outcome_{pr}"]
            assert o["payNow"] == o["bnplPot"] == (got == "payNow"), (pid, pr, o, got)
            assert (got == "bnplPlainOnly") == (o["bnplPlain"] and not o["payNow"]), (pid, pr, o, got)
            assert abs(a["safeToSpend"] - row.safeToSpend) < 0.005 and abs(a["income"]["monthly"] - row.income) < 0.005
    m1 = (FIGURES / f"{F1}.md").read_text(encoding="utf-8")
    for pr in PRICES:
        assert f"| {pr:,} | " + " | ".join(map(str, c[pr])) + f" | {len(df)} |" in m1, pr
    m2 = (FIGURES / f"{F2}.md").read_text(encoding="utf-8")
    for col in ("safeToSpend", "monthly.leftOver"):
        assert tenure_table(df, col) in m2, col
        assert f"| `{col}` | {spearman(df.income, df[col])[0]:.3f} |" in m2, col
    assert all((FIGURES / f"{n}.{e}").stat().st_size > 0 for n in (F1, F2) for e in ("pdf", "svg"))
    assert "deducts the predicted everyday spending" in m1 and "predictedSpendingUntilPayday.definition" in m1 + m2
    assert (df.safeToSpend <= df.safeToSpendBeforeEverydaySpending).all()
    sv = pd.read_csv(VALUE_A / f"{F3}.csv")
    pd.testing.assert_frame_equal(sv, pd.read_csv(io.StringIO(savings().to_csv(index=False, float_format="%.2f"))))
    assert savings_table(sv) in (VALUE_F / f"{F3}.md").read_text(encoding="utf-8")
    assert all((VALUE_F / f"{F3}.{e}").stat().st_size > 0 for e in ("pdf", "svg"))
    print(f"Check passed: {len(df)} households, counts sum to {len(df)} at every price, 4 personas spot-checked, "
          f".md tables match the CSV; savings comparison ({len(sv)} products) matches a fresh calculation.")


def main():
    import matplotlib.pyplot as plt
    import TeXFormat as tf
    plt.style.use(Path(tf.__file__).with_name("TeXFormat.mplstyle"))
    plt.rcParams["svg.hashsalt"] = "t07b"  # stable SVG ids
    df, sample = build()
    write_csv(df)
    fig_price(df, sample)
    stats = fig_income(df, sample)
    sv = savings()
    fig_savings(sv)
    print(sv.to_string(index=False))
    print(f"Wrote {CSV.relative_to(HERE)} and Figures/affordability/{F1}.*, {F2}.*")
    print("Price [GBP] | " + " | ".join(CATS))
    for pr, v in counts(df).items():
        print(pr, "|", " | ".join(map(str, v)))
    print("Spearman (rho, p):", {k: (round(r, 3), float(f"{p:.3g}")) for k, (r, p) in stats.items()})


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true", help="verify the written outputs instead of writing them")
    (check if ap.parse_args().check else main)()
