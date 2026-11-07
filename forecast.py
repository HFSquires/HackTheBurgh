"""Spending-forecast backtest (task T12): fit on August and September 2026, predict each persona's October.

Target: October discretionary card spending per persona, i.e. card payments that are neither BNPL instalments nor
committed payments, as affordability.card_spend defines it, with committed payments detected at the forecast origin
(30 September) so that no October row decides what counts. Also scored: total debits, card spending by merchant group,
and cumulative discretionary spending by day of October. October is used only to score, never to fit or tune.

Run:   .venv\\Scripts\\python -X utf8 forecast.py          # writes Analysis/forecast/ and Figures/forecast/
Check: .venv\\Scripts\\python -X utf8 forecast.py --check  # asserts only; writes nothing
"""
import argparse
import calendar
import datetime as dt
import math
import subprocess
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import stats
import TeXFormat as tf

import affordability as af
import mock_statements as ms

HERE = Path(__file__).resolve().parent
ANA, FIG = HERE / "Analysis" / "forecast", HERE / "Figures" / "forecast"
SEED, FOLDS = 20261107, 10
AUG, SEP, OCT = (2026, 8), (2026, 9), (2026, 10)
DAYS = (7, 14, 21, 28)
CATS = [1, 2, 3, 5, 6, 7, 9, 11, 12]          # ONS categories the generator spends by card
HH = ["couple", "lone_parent", "couple_kids"]   # household dummies; "alone" is the reference
TEN = ["Social rented", "Private rented"]        # tenure dummies; "Owned outright" is the reference
TARGETS = ["disc_oct", "bnpl_oct", "debit_oct"]  # October outcomes; forecast() refuses a table that contains them
GROUP = {1: "food and drink", 2: "food and drink", 3: "clothing", 5: "household goods", 6: "health", 7: "transport",
         9: "recreation", 11: "restaurants", 12: "miscellaneous"}
MERCHANT = {m: GROUP[c] for c, (names, _) in ms.MERCH.items() for m in names if m != "@RAIL@"}
MERCHANT |= {r: "transport" for r in ms.RAIL.values()}
MODELS = {"last": "Last month (Sep)", "mean": "Mean Aug-Sep", "mean_bnpl": "Mean + BNPL schedule",
          "regression": "Pooled regression", "shrinkage": "Shrinkage", "generator": "Generator mean (reference)"}
BASELINES, LEARNED, PRIMARY = ["last", "mean"], ["mean_bnpl", "regression", "shrinkage"], "regression"
CURVES = {"curve_mean": "Mean of Aug and Sep curves", "curve_linear": r"Pooled regression $\times\, d/31$",
          "curve_generator": r"Generator mean $\times\, d/31$ (reference)"}
COEF = ["intercept", "couple", "lone parent", "couple with children", "social rented", "private rented",
        "prior card spend incl. BNPL [GBP]", "BNPL due in target month [GBP]", "net monthly pay [GBP]"]

ym = lambda d: (d.year, d.month)
eom = lambda m: dt.date(*m, calendar.monthrange(*m)[1])


def group(desc):
    """Merchant group of a card description '<MERCHANT> <TOWN> GB'; None if unknown."""
    if "TICKETS" in desc:
        return "football tickets"
    hits = [m for m in MERCHANT if desc.startswith(m + " ")]
    return MERCHANT[max(hits, key=len)] if hits else None


def person(tx, origin=SEP):
    """Monthly quantities for one statement. Committed payments are detected on the rows up to `origin`; scheduled
    BNPL (sched_<month>) and net pay (net_<month before>) use only the rows before that month."""
    upto = lambda m: [t for t in tx if ym(t["date"]) <= m]
    fixed = {(c["name"], c["amount"]) for c in af.detect_committed(upto(origin), eom(origin))}
    disc = lambda t: (t["type"] == "DEB" and t["debit"] > 0 and not af.BNPL.search(t["desc"])
                      and (t["desc"], t["debit"]) not in fixed)
    r, cum, cat = {}, {}, {}
    for m, k in ((AUG, "aug"), (SEP, "sep"), (OCT, "oct")):
        rows = [t for t in tx if ym(t["date"]) == m]
        r[f"disc_{k}"] = sum(t["debit"] for t in rows if disc(t))
        r[f"bnpl_{k}"] = sum(t["debit"] for t in rows if t["debit"] > 0 and af.BNPL.search(t["desc"]))
        r[f"debit_{k}"] = sum(t["debit"] for t in rows)
        cum[k] = np.zeros(32)  # cum[d] = discretionary spending on days 1 to d
        cat[k] = {}
        for t in filter(disc, rows):
            cum[k][t["date"].day:] += t["debit"]
            cat[k][group(t["desc"])] = cat[k].get(group(t["desc"]), 0.0) + t["debit"]
    for o, nxt, k in ((AUG, SEP, "sep"), (SEP, OCT, "oct")):
        rows = upto(o)
        r[f"sched_{k}"] = sum(s["amount"] for p in af.detect_bnpl(rows) for s in p["schedule"]
                              if ym(dt.date.fromisoformat(s["due"])) == nxt)
        r[f"net_{o[1]:02d}"] = [t for t in rows if t["credit"] > 0][-1]["credit"]  # latest credit (the salary here)
    r["bnpl_any"] = any(af.BNPL.search(t["desc"]) for t in tx)
    return r, cum, cat


def load():
    """Statements and static attributes (household key, tenure, region, gross pay, modelled spend) from personas.md."""
    info = {}
    for line in (af.STATEMENTS / "personas.md").read_text(encoding="utf-8").splitlines():
        c = [x.strip() for x in line.strip().strip("|").split("|")]
        if len(c) == 12 and c[0].isdigit():
            info[f"persona{int(c[0]):03d}"] = dict(region=c[3], hh=ms.HTYPES[c[4]][0], tenure=c[6], gross=float(c[7]))
        elif len(c) == 17 and c[0].isdigit():
            info[f"persona{int(c[0]):03d}"]["md_cats"] = dict(zip(CATS, map(float, c[1:10])))
    files = sorted(af.STATEMENTS.glob("persona[0-9][0-9][0-9]_*.csv"))
    st = {f.name[:10]: af.parse(f.read_text(encoding="utf-8")) for f in files}
    assert st and set(st) == set(info), "statements and personas.md disagree"
    return st, info


def table(st, info):
    rows, curves, cats = {}, {}, {}
    for pid, tx in st.items():
        rows[pid], curves[pid], cats[pid] = person(tx)
        rows[pid] |= dict(hh=info[pid]["hh"], tenure=info[pid]["tenure"])
    T = pd.DataFrame.from_dict(rows, orient="index")
    C = {k: np.array([curves[p][k] for p in T.index]) for k in ("aug", "sep", "oct")}
    return T, C, cats


def generator_mean(info, T, cats):
    """The generator's expected October discretionary spending: sum over categories of the modelled monthly mean
    (ms.spend_model, called per persona), plus the fixed football-ticket payments, less October's BNPL instalments.
    A reference only: it uses the generator's internals and October's BNPL and ticket rows."""
    ons = ms.load_ons()
    means = {}
    for pid, p in info.items():
        # the decile uses April 2025 pay (see mock_statements.build)
        pool, _ = ms.spend_model(p["hh"], p["tenure"], p["region"], ons, ms.decile(p["gross"] / ons["awe"], ons))
        means[pid] = {c: pool[c] * ms.WK for c in CATS}
    g = pd.Series({pid: sum(m.values()) + cats[pid]["oct"].get("football tickets", 0.0) for pid, m in means.items()})
    return g[T.index] - T.bnpl_oct, means


def forecast(T, seed=SEED):
    """October discretionary forecasts from August and September only. Returns predictions, folds, the regression
    coefficients of each fold and the shrinkage (weight, within variance, between variance) of each fold."""
    assert not set(TARGETS) & set(T.columns), "October outcomes passed to forecast()"
    n = len(T)
    v = lambda c: T[c].to_numpy(float)
    g_aug, g_sep = v("disc_aug") + v("bnpl_aug"), v("disc_sep") + v("bnpl_sep")  # card spend with BNPL added back
    P = pd.DataFrame(index=T.index)
    P["last"] = v("disc_sep")
    P["mean"] = (v("disc_aug") + v("disc_sep")) / 2
    P["mean_bnpl"] = (g_aug + g_sep) / 2 - v("sched_oct")
    static = np.column_stack([np.ones(n)] + [T.hh == h for h in HH] + [T.tenure == t for t in TEN]).astype(float)
    # Pooled regression, fitted on August -> September (the only pair with a label before October), applied with the
    # Aug-Sep mean as the prior spend and the BNPL instalments scheduled for October.
    X_fit = np.column_stack([static, g_aug, v("sched_sep"), v("net_08")])
    y_fit = v("disc_sep")
    X_oct = np.column_stack([static, (g_aug + g_sep) / 2, v("sched_oct"), v("net_09")])
    # Shrinkage on the log scale: the person's mean log spend shrunk towards a pooled prior from static features.
    Z = np.column_stack([static, np.log(v("net_09"))])
    lg = (np.log(g_aug) + np.log(g_sep)) / 2
    fold = np.random.default_rng(seed).permutation(n) % FOLDS
    reg, shr, coef, wts = np.empty(n), np.empty(n), [], []
    for k in range(FOLDS):
        tr, te = fold != k, fold == k
        b = np.linalg.lstsq(X_fit[tr], y_fit[tr], rcond=None)[0]
        reg[te] = X_oct[te] @ b
        s2 = np.mean((np.log(g_sep) - np.log(g_aug))[tr] ** 2) / 2  # within-person variance of one month's log spend
        a = np.linalg.lstsq(Z[tr], lg[tr], rcond=None)[0]
        tau2 = max(0.0, np.sum((lg[tr] - Z[tr] @ a) ** 2) / (tr.sum() - Z.shape[1]) - s2 / 2)
        w = tau2 / (tau2 + s2 / 2)
        shr[te] = np.exp(w * lg[te] + (1 - w) * (Z[te] @ a)) - v("sched_oct")[te]
        coef.append(b)
        wts.append((w, s2, tau2))
    P["regression"], P["shrinkage"] = reg, shr
    return P, fold, np.array(coef), np.array(wts)


def curve_preds(C, P):
    d = np.arange(32) / 31
    return {"curve_mean": (C["aug"] + C["sep"]) / 2, "curve_linear": P["regression"].to_numpy()[:, None] * d}


def metrics(pred, actual):
    """MAE, RMSE and MAPE with standard errors across persons (RMSE SE by the delta method), and the mean error.
    MAPE uses only the persons whose actual value is not zero (n_mape of them)."""
    pred, actual = np.asarray(pred, float), np.asarray(actual, float)
    e, ok = pred - actual, actual != 0
    n, ae, ape = len(e), np.abs(e), 100 * np.abs(e[ok]) / np.abs(actual[ok])
    sem = lambda x: x.std(ddof=1) / math.sqrt(len(x))
    rmse = math.sqrt(np.mean(e ** 2))
    return dict(n=n, n_mape=int(ok.sum()), MAE=ae.mean(), MAE_SE=sem(ae), RMSE=rmse, RMSE_SE=sem(e ** 2) / (2 * rmse) if rmse else 0.0,
                MAPE=ape.mean(), MAPE_SE=sem(ape), bias=e.mean(), bias_SE=sem(e))


def paired(pm, pb, actual):
    am, ab = np.abs(np.asarray(pm) - actual), np.abs(np.asarray(pb) - actual)
    d, t, w = am - ab, stats.ttest_rel(am, ab), stats.wilcoxon(am - ab)
    return dict(diff=d.mean(), diff_SE=d.std(ddof=1) / math.sqrt(len(d)), t=t.statistic, df=len(d) - 1, p_t=t.pvalue,
                W=w.statistic, p_w=w.pvalue, n_w=int((d != 0).sum()))  # Wilcoxon drops zero differences


def holm(p):
    p = np.asarray(p, float)
    o = np.argsort(p)
    adj = np.minimum(1, np.maximum.accumulate((len(p) - np.arange(len(p))) * p[o]))
    out = np.empty(len(p))
    out[o] = adj
    return out


def md_table(head, rows):
    return "\n".join(["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
                     + ["| " + " | ".join(str(x) for x in r) + " |" for r in rows]) + "\n"


def commits(*files):
    """Provenance sentence: the commit that last changed the statements and each named file (T15)."""
    h = lambda *p: subprocess.run(["git", "log", "-1", "--format=%h", "--", *p], cwd=HERE, capture_output=True,
                                  text=True).stdout.strip() or "unknown"
    return (f"Statements last changed in commit `{h('Analysis/mock_statements')}`; "
            + "; ".join(f"`{f}` at commit `{h(f)}`" for f in files) + " (or later, if uncommitted changes were run).")


pm = lambda m, k, f=".2f":f"{m[k]:{f}} ± {m[k + '_SE']:{f}}"
pv = lambda p: f"{p:.2g}" if p >= 1e-4 else f"{p:.1e}"

NOISE = """## What these data can and cannot show

`mock_statements.py` draws each persona's card spending in each of nine ONS categories, each month, as the modelled
monthly mean (ONS Family Spending for the persona's region, household type and income decile) multiplied by an independent
factor drawn uniformly between 0.9 and 1.1, less any BNPL instalment charged to that category that month; transaction days
are uniform over the month and amounts are split by lognormal weights. The factors are independent across months and
categories, so a persona has no habit beyond its deterministic mean, no trend, no seasonality, no irregular large purchase
and no change of income. The best possible forecast of October is therefore the generator mean less the BNPL instalments
due in October (the reference), whose error is October's own noise; a forecast that averages August and September adds
those months' noise (error variance 1.5 times the reference's once the BNPL schedule is accounted for; last month alone,
2 times). The naive baselines are thus close to the best achievable apart from BNPL, and a learned model can gain only by
reading the BNPL schedule and by shrinking a two-month mean towards a pooled estimate. This backtest measures how well the
models recover the generator's process, not how real customers behave.
"""


def run(write=True):
    st, info = load()
    T, C, cats = table(st, info)
    gen, means = generator_mean(info, T, cats)
    P, fold, coef, wts = forecast(T.drop(columns=TARGETS))
    P["generator"] = gen
    actual = T.disc_oct.to_numpy()
    M = {m: metrics(P[m], actual) for m in MODELS}
    comps = [(m, b, paired(P[m], P[b], actual)) for m in LEARNED for b in BASELINES]
    for key in ("p_t", "p_w"):
        for (m, b, c), h in zip(comps, holm([c[key] for _, _, c in comps])):
            c[key + "_holm"] = h
    cp = curve_preds(C, P) | {"curve_generator": gen.to_numpy()[:, None] * np.arange(32) / 31}
    CM = {k: {d: metrics(cp[k][:, d], C["oct"][:, d]) for d in range(1, 32)} for k in CURVES}
    tot = {"last": T.debit_sep, "mean": (T.debit_aug + T.debit_sep) / 2,
           "regression": T.debit_sep - T.disc_sep - T.bnpl_sep + T.sched_oct + P.regression}
    TM = {k: metrics(v, T.debit_oct) for k, v in tot.items()}
    if not write:
        return T, C, cats, P, M, comps, CM, info, means, st
    ANA.mkdir(parents=True, exist_ok=True)
    FIG.mkdir(parents=True, exist_ok=True)
    out = pd.DataFrame({"persona": T.index, "bnpl_plan": np.where(T.bnpl_any, "yes", "no"),
                        "actual_oct": actual, **{f"pred_{m}": P[m] for m in MODELS},
                        **{f"err_{m}": P[m] - actual for m in MODELS},
                        "actual_total_debits_oct": T.debit_oct, **{f"pred_total_{k}": v for k, v in tot.items()}})
    out.round(2).to_csv(ANA / "predictions_october.csv", index=False, lineterminator="\n")
    cur = pd.DataFrame([dict(persona=p, day=d, actual=C["oct"][i, d], **{k: cp[k][i, d] for k in CURVES})
                        for i, p in enumerate(T.index) for d in range(1, 32)])
    cur.round(2).to_csv(ANA / "curves_october.csv", index=False, lineterminator="\n")

    # ---- shared text
    beats = []
    for m, b, c in comps:
        verdict = ("lower absolute error" if c["diff"] < 0 and c["p_w_holm"] < 0.05 else
                   "higher absolute error" if c["diff"] > 0 and c["p_w_holm"] < 0.05 else "no detectable difference")
        beats.append([MODELS[m], MODELS[b], f"{c['diff']:.2f} ± {c['diff_SE']:.2f}", f"{c['t']:.2f}", c["df"],
                      pv(c["p_t"]), pv(c["p_t_holm"]), f"{c['W']:.0f}", c["n_w"], pv(c["p_w"]), pv(c["p_w_holm"]),
                      verdict])
    comp_md = md_table(["Model", "Baseline", "Mean difference in absolute error [GBP] (± SE)", "Paired t", "df", "p (t)",
                        "p (t, Holm)", "Wilcoxon W", "Non-zero pairs", "p (W)", "p (W, Holm)", "Wilcoxon, Holm, 0.05"],
                       beats)
    model_md = md_table(["Model", "n", "MAE [GBP] (± SE)", "RMSE [GBP] (± SE)", "MAPE [%] (± SE)", "Mean error [GBP] (± SE)"],
                        [[MODELS[m], M[m]["n"], pm(M[m], "MAE"), pm(M[m], "RMSE"), pm(M[m], "MAPE"), pm(M[m], "bias")]
                         for m in MODELS])
    ratio = {m: M[m]["RMSE"] / M["generator"]["RMSE"] for m in MODELS}
    n_tix = sum("football tickets" in cats[p]["oct"] for p in T.index)
    moved = (P.mean_bnpl - P["mean"]).abs()
    moved = moved[moved > 0]
    src = ("Source: the 100 statements in `Analysis/mock_statements/` (persona CSVs and `personas.md`), via `forecast.py`. "
           "Target: October 2026 discretionary card spending per persona [GBP], i.e. card (DEB) payments that are neither BNPL "
           "instalments nor committed payments, with committed payments detected by `affordability.detect_committed` on "
           f"the rows up to 30 September (so the fixed football-ticket card payments of {n_tix} personas, which need three "
           "months to be detected, count as discretionary in every month). Models are fitted on August and September only; "
           "October is used only to score. Per-persona data: `Analysis/forecast/predictions_october.csv`. "
           + commits("forecast.py", "affordability.py") + "\n")

    # ---- figure (i): predicted versus actual, and errors of the primary model and the mean baseline
    plt.style.use(Path(tf.__file__).with_name("TeXFormat.mplstyle"))
    col = dict(zip(MODELS, tf.CYCLE))
    bn = T.bnpl_any.to_numpy()
    fig, (a, b) = plt.subplots(1, 2, figsize=(17, 7.5))
    lo, hi = actual.min() * 0.9, actual.max() * 1.05
    a.plot([lo, hi], [lo, hi], color="k", lw=1.2, ls="--", label=r"$y = x$")
    for mask, mk, lab in ((~bn, "o", "no BNPL plan"), (bn, "^", "BNPL plan")):
        a.scatter(actual[mask], P[PRIMARY][mask], marker=mk, s=60, color=col[PRIMARY], label=lab)
        for m in ("mean", PRIMARY):
            b.scatter(actual[mask], (P[m] - actual)[mask], marker=mk, s=60, color=col[m],
                      label=f"{MODELS[m]}, {lab}")
    a.set(xlim=(lo, hi), ylim=(lo, hi), xlabel="Actual October spending [GBP]",
          ylabel="Predicted, pooled regression [GBP]")
    a.legend(frameon=True, fancybox=False, fontsize=tf.fontsizeTiny, loc="upper left")
    b.axhline(0, color="k", lw=1)
    y0, y1 = b.get_ylim()
    b.set_ylim(y0 - 0.4 * (y1 - y0), y1)  # room for the legend below the points
    b.set(xlabel="Actual October spending [GBP]", ylabel="Prediction error [GBP]")
    b.legend(frameon=True, fancybox=False, fontsize=tf.fontsizeTiny, loc="lower left")
    for ax, lab in ((a, "(a)"), (b, "(b)")):
        ax.text(0.97, 0.04 if ax is a else 0.95, lab, transform=ax.transAxes, ha="right",
                va="bottom" if ax is a else "top", fontsize=tf.fontsizeSmall)
    fig.tight_layout()
    for ext in ("pdf", "svg"):
        fig.savefig(FIG / f"forecast_scatter.{ext}")
    plt.close(fig)
    r_err = np.corrcoef(P["mean"] - actual, P[PRIMARY] - actual)[0, 1]
    sub = lambda m, mask: metrics(P[m][mask], actual[mask])
    rows = [[MODELS[m], lab, mask.sum(), pm(sub(m, mask), "MAE"), pm(sub(m, mask), "bias")]
            for m in ("mean", PRIMARY) for mask, lab in ((~bn, "no BNPL plan"), (bn, "BNPL plan"))]
    (FIG / "forecast_scatter.md").write_text(
        "# October discretionary spending: predicted versus actual\n\nPlot: `forecast_scatter.pdf` / `.svg`. "
        f"Written by `forecast.py`; regenerate with it.\n\n## Source and transformations\n\n{src}\n"
        "Panel (a): pooled-regression prediction against the actual value, one point per persona (n = 100), with the line "
        "y = x; triangles mark the personas with a BNPL plan. Panel (b): prediction error (prediction minus actual) against "
        "the actual value for the mean Aug-Sep baseline and the pooled regression. Units GBP. No error bars.\n\n"
        f"Axis range of (a): {lo:.2f} to {hi:.2f} GBP. Actual October spending: min {actual.min():.2f}, median "
        f"{np.median(actual):.2f}, max {actual.max():.2f} GBP.\n\n## Statistics by series\n\n"
        "Uncertainties are ± one standard error across persons.\n\n"
        + md_table(["Model", "Personas", "n", "MAE [GBP] (± SE)", "Mean error [GBP] (± SE)"], rows)
        + f"\nAll persons: pooled regression MAE {pm(M[PRIMARY], 'MAE')} GBP, mean Aug-Sep MAE {pm(M['mean'], 'MAE')} GBP. "
        f"Paired comparisons, fits and tests: `forecast_errors.md`.\n\nRandom seed {SEED} (assignment of persons to "
        f"{FOLDS} cross-validation folds).\n\n## Interpretation\n\nThe points in (a) lie close to y = x: the regression's "
        f"mean absolute percentage error is {M[PRIMARY]['MAPE']:.1f} %. In (b), the errors of the two forecasts are "
        f"{'strongly ' if r_err > 0.7 else ''}correlated across persons (Pearson r = {r_err:.3f}), as expected when "
        "both are dominated by October's own random variation, which no forecast made on 30 September can anticipate. "
        "The table above gives the errors separately for personas with and without a BNPL plan.\n\n"
        + NOISE, encoding="utf-8", newline="\n")

    # ---- figure (ii): MAE by model, and MAE of the cumulative curve by day of October
    fig, (a, b) = plt.subplots(1, 2, figsize=(17, 7.5), gridspec_kw=dict(width_ratios=[1.1, 1]))
    for i, m in enumerate(MODELS):
        tf.bar(a, [i], [M[m]["MAE"]], col[m], yerr=[M[m]["MAE_SE"]], capsize=4, hatch="//" if m == "generator" else None)
    a.set_xticks(range(len(MODELS)), [MODELS[m].replace(" (reference)", "\n(reference)") for m in MODELS],
                 rotation=35, ha="right", fontsize=tf.fontsizeTiny)
    a.set_ylabel("MAE, October [GBP]")
    days = np.arange(1, 32)
    for k, c in zip(CURVES, (col["mean"], col[PRIMARY], col["generator"])):
        mae, se = (np.array([CM[k][d][q] for d in days]) for q in ("MAE", "MAE_SE"))
        b.plot(days, mae, color=c, label=CURVES[k], ls=":" if k == "curve_generator" else "-")
        b.fill_between(days, mae - se, mae + se, color=c, alpha=0.2, lw=0)
    b.set(xlabel="Day of October", ylabel="MAE of cumulative spending [GBP]", xlim=(1, 31))
    b.legend(frameon=True, fancybox=False, fontsize=tf.fontsizeTiny, loc="lower center")
    for ax, lab in ((a, "(a)"), (b, "(b)")):
        ax.text(0.97, 0.95, lab, transform=ax.transAxes, ha="right", va="top", fontsize=tf.fontsizeSmall)
    fig.tight_layout()
    for ext in ("pdf", "svg"):
        fig.savefig(FIG / f"forecast_errors.{ext}")
    plt.close(fig)
    w, s2, tau2 = wts.mean(0)
    lin_better = all(CM["curve_linear"][d]["MAE"] < CM["curve_mean"][d]["MAE"] for d in DAYS)
    curve_rows = [[CURVES[k].replace("$\\times\\, d/31$", "x d/31"), d, pm(CM[k][d], "MAE"), pm(CM[k][d], "RMSE"),
                   pm(CM[k][d], "MAPE", ".1f")] for k in CURVES for d in DAYS]
    (FIG / "forecast_errors.md").write_text(
        "# Forecast error by model, and by day of October for the cumulative curve\n\nPlot: `forecast_errors.pdf` / "
        f"`.svg`. Written by `forecast.py`; regenerate with it.\n\n## Source and transformations\n\n{src}\n"
        "Panel (a): mean absolute error of each model's October forecast across the 100 personas; error bars are ± one "
        "standard error of the mean absolute error across persons; the hatched bar is the generator mean, a reference "
        "that uses the generator's internals and is not a forecast. Panel (b): mean absolute error of the predicted "
        "cumulative discretionary spending on days 1 to d of October, for d = 1 to 31; bands are ± one standard error "
        "across persons. Per-day data: `Analysis/forecast/curves_october.csv`.\n\n## Models (all fitted on August and "
        "September only)\n\n"
        "Last month: October = September. Mean Aug-Sep: October = mean of August and September. Mean + BNPL schedule: mean "
        "of August and September card spending with their BNPL instalments added back, less the instalments that "
        "`affordability.detect_bnpl` schedules for October from the rows up to 30 September. Pooled regression: ordinary "
        "least squares across persons of September discretionary spending on [intercept, household type (3 dummies, "
        "reference: lives alone), tenure (2 dummies, reference: owned outright), August card spending with BNPL added "
        "back, BNPL instalments scheduled for September from the rows up to 31 August, net monthly pay]; applied to "
        "October with the August-September mean of card spending with BNPL added back, the instalments scheduled for "
        "October, and September's net pay. Shrinkage: each person's mean log card spending (BNPL added back) over August "
        "and September, shrunk towards a pooled least-squares prediction from household type, tenure and log net pay, "
        "with weight w = tau^2 / (tau^2 + s^2/2), where s^2 is the within-person variance of one month's log spending "
        "(from the August-September differences) and tau^2 the between-person residual variance less s^2/2; exp of the "
        "result, less the BNPL instalments scheduled for October. The regression and shrinkage are fitted with "
        f"person-level {FOLDS}-fold cross-validation (seed {SEED}): each person's prediction comes from a fit that "
        "excludes that person. No parameter was tuned; October enters only the scores.\n\n"
        "Within-month curves: mean of the August and September cumulative curves at the same day d; or the pooled "
        "regression's October total times d/31 (a constant daily rate); the generator-mean reference times d/31.\n\n"
        "## Panel (a): October totals\n\n" + model_md
        + "\nRatio of each model's RMSE to the reference's: "
        + ", ".join(f"{MODELS[m]} {ratio[m]:.2f}" for m in MODELS if m != "generator")
        + ". Under the generator, a two-month mean that accounts for BNPL should give about 1.22 (square root of 1.5) and "
        "last month alone about 1.41 (square root of 2), before BNPL effects.\n\n"
        "Paired comparisons of absolute error (model minus baseline; negative means the model is better), per person, n = "
        f"100. Pre-specified primary comparison: pooled regression versus mean Aug-Sep. Holm correction over the "
        f"{len(comps)} comparisons, separately for each test. The Wilcoxon signed-rank test (scipy default, two-sided) "
        "drops pairs with zero difference: Mean + BNPL schedule equals Mean Aug-Sep for every persona whose October "
        "BNPL instalments match the August-September average.\n\n" + comp_md
        + f"\nPooled-regression coefficients (mean ± SD over the {FOLDS} fold fits):\n\n"
        + md_table(["Term", "Coefficient"], [[n, f"{coef[:, i].mean():.4g} ± {coef[:, i].std(ddof=1):.2g}"]
                                            for i, n in enumerate(COEF)])
        + f"\nShrinkage, mean over folds: w = {w:.4f}, s^2 = {s2:.3g}, tau^2 = {tau2:.3g} (log scale).\n\n"
        "## Panel (b): cumulative spending at selected days (all days are in the CSV)\n\nn = 100 at every day; "
        "uncertainties ± one standard error across persons; MAPE uses the actual cumulative spending on that day.\n\n"
        + md_table(["Curve", "Day", "MAE [GBP] (± SE)", "RMSE [GBP] (± SE)", "MAPE [%] (± SE)"], curve_rows)
        + "\n## Interpretation\n\n"
        + " ".join(f"{MODELS[m]} against {MODELS[b]}: {c['diff']:+.2f} ± {c['diff_SE']:.2f} GBP in absolute error "
                   f"(Wilcoxon p = {pv(c['p_w'])}, Holm {pv(c['p_w_holm'])})." for m, b, c in comps)
        + (" No model differs detectably from either baseline after Holm correction."
           if all(r[-1] == "no detectable difference" for r in beats) else "")
        + f" Reading the BNPL schedule changes the Aug-Sep mean for only {len(moved)} personas, by {moved.mean():.2f} GBP "
        f"on average (largest {moved.max():.2f} GBP), small beside the month-to-month noise, so it cannot help much here."
        + " The RMSE ratios to the reference (above) are close to the values the generator implies, so most of the "
        "remaining error is October's own random variation. Within the month, the constant daily rate from the pooled "
        f"regression has {'a lower' if lin_better else 'not always a lower'} MAE than the mean of the August and "
        f"September curves at days {', '.join(map(str, DAYS))}, and is close to the generator-mean reference: transaction "
        "days are drawn uniformly over the month, so the expected cumulative curve is a straight line, while averaging "
        "two realised curves keeps their timing noise.\n\n" + NOISE,
        encoding="utf-8", newline="\n")

    # ---- non-plotted targets
    cat_rows = []
    for gname in sorted({g for p in cats for g in cats[p]["oct"]}):
        act = np.array([cats[p]["oct"].get(gname, 0.0) for p in T.index])
        prd = np.array([(cats[p]["aug"].get(gname, 0.0) + cats[p]["sep"].get(gname, 0.0)) / 2 for p in T.index])
        ok = act > 0
        mm = metrics(prd[ok], act[ok])
        cat_rows.append([gname, ok.sum(), f"{act[ok].mean():.2f}", pm(mm, "MAE"), pm(mm, "MAPE", ".1f")])
    agree = int(np.isclose(T.sched_oct, T.bnpl_oct, atol=0.005).sum())
    (ANA / "backtest_summary.md").write_text(
        "# October backtest: further targets\n\nWritten by `forecast.py`; regenerate with it. Figures and the main "
        "results: `Figures/forecast/forecast_errors.md` and `forecast_scatter.md`.\n\n## Total debits in October\n\n"
        "Last month and mean Aug-Sep as for discretionary spending; the third row is September's committed debits "
        "(all debits less discretionary spending and BNPL) plus the BNPL instalments scheduled for October plus the "
        "pooled-regression forecast of discretionary spending.\n\n"
        + md_table(["Forecast", "n", "MAE [GBP] (± SE)", "RMSE [GBP] (± SE)", "MAPE [%] (± SE)"],
                   [[("Committed + BNPL schedule + pooled regression" if k == "regression" else MODELS[k]), TM[k]["n"],
                     pm(TM[k], "MAE"), pm(TM[k], "RMSE"), pm(TM[k], "MAPE")] for k in TM])
        + "\n## Card spending by merchant group, mean Aug-Sep forecast\n\nGroups come from the merchant names in "
        "`mock_statements.MERCH`; TESCO STORES is used for both food (ONS 1) and alcohol (ONS 2), so the two are "
        "merged. Personas with no October spending in a group are excluded from that row. BNPL instalments are "
        "not card spending here, so a group carrying a BNPL plan varies with the plan's schedule.\n\n"
        + md_table(["Group", "n", "Mean October spending [GBP]", "MAE [GBP] (± SE)", "MAPE [%] (± SE)"], cat_rows)
        + f"\n## BNPL schedule\n\nPersonas with a BNPL plan: {int(T.bnpl_any.sum())}. The instalments scheduled for "
        f"October from the rows up to 30 September equal the instalments actually charged in October for {agree} of "
        f"{len(T)} personas.\n\n" + NOISE, encoding="utf-8", newline="\n")
    print(md_table(["Model", "MAE (± SE)", "RMSE (± SE)", "MAPE % (± SE)"],
                   [[MODELS[m], pm(M[m], "MAE"), pm(M[m], "RMSE"), pm(M[m], "MAPE")] for m in MODELS]))
    print(comp_md)
    print(md_table(["Curve", "Day", "MAE (± SE)"], [r[:3] for r in curve_rows]))
    print(f"BNPL schedule matches October for {agree}/{len(T)}; shrinkage w = {w:.4f}")


def check():
    m = metrics([11, 8, 33], [10, 10, 30])  # errors 1, -2, 3; APE 10, 20, 10 %
    assert math.isclose(m["MAE"], 2) and math.isclose(m["MAE_SE"], 1 / math.sqrt(3))
    assert math.isclose(m["RMSE"], math.sqrt(14 / 3)) and math.isclose(m["MAPE"], 40 / 3) and math.isclose(m["bias"], 2 / 3)
    assert np.allclose(holm([0.01, 0.04, 0.03]), [0.03, 0.06, 0.06])
    T, C, cats, P, M, comps, CM, info, means, st = run(write=False)
    # The discretionary definition matches affordability.card_spend when committed payments come from the whole statement.
    for pid, tx in st.items():
        r = person(tx, origin=OCT)[0]
        ref = af.card_spend(tx, af.detect_committed(tx, tx[-1]["date"]))
        assert np.allclose([r["disc_aug"], r["disc_sep"], r["disc_oct"]], ref), pid
        assert all(None not in cats[pid][k] for k in cats[pid]), f"{pid}: unknown merchant"
        assert all(abs(means[pid][c] - info[pid]["md_cats"][c]) <= 0.5 + 1e-9 for c in CATS), f"{pid}: generator mean"
    # Every October total lies within the generator's +-10 % band around its mean (tolerance for pence rounding).
    band = 0.1 * pd.Series({p: sum(means[p].values()) for p in T.index})
    assert ((T.disc_oct - P.generator).abs() <= band + 0.05).all(), "October outside the generator's noise band"
    # No October data in any fit: corrupting every October row leaves every forecast unchanged.
    bad = {pid: [t | dict(debit=t["debit"] * 3, credit=t["credit"] * 3) if ym(t["date"]) == OCT else t for t in tx]
           for pid, tx in st.items()}
    T2, C2, _ = table(bad, info)
    assert not np.allclose(T2.disc_oct, T.disc_oct)
    P2 = forecast(T2.drop(columns=TARGETS))[0]
    pd.testing.assert_frame_equal(P2, P.drop(columns="generator"))
    for k, v in curve_preds(C2, P2).items():
        assert np.array_equal(v, curve_preds(C, P)[k])
    try:
        forecast(T)
    except AssertionError:
        pass
    else:
        raise AssertionError("forecast() accepted October outcomes")
    # Folds: every person is predicted exactly once, by a fit that excludes them; results reproducible.
    _, fold, _, _ = forecast(T.drop(columns=TARGETS))
    assert sorted(np.bincount(fold)) == [len(T) // FOLDS] * FOLDS
    pd.testing.assert_frame_equal(forecast(T.drop(columns=TARGETS))[0], P.drop(columns="generator"))
    print("self-check passed")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true", help="run the self-check (writes nothing)")
    check() if ap.parse_args().check else run()
