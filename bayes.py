"""Bayesian model of everyday spending and the probability of going below zero before payday (task T17).

Unit. x = discretionary card spending on one calendar day [GBP]: card (DEB) payments that are neither BNPL instalments
nor committed payments, as affordability.card_spend defines them, with committed payments detected on the rows up to the
last observed day; a day with no such payment is an observation of 0. Daily rather than weekly so that the posterior
moves with each day's transactions; on the mock statements 23 % of days have no card spending, which a raw-scale model
takes as it is and a log scale cannot.

Likelihood ("monthly budget"). Person i has a monthly budget beta and a daily variance sigma^2. In a calendar month of D
days each day's spending has mean beta / D and variance sigma^2; two days of the same month have correlation
rho = (phi - 1) / (D - 1); days of different months are independent. A month's total then has mean beta and variance
phi D sigma^2, so phi = 1 is independent days, phi < 1 a month's total that varies less than independent days would
give (a budget spent whatever the timing), phi > 1 more. phi is one population constant estimated from the data. On the
mock statements it is about 0.02: a month's total varies by about 2 % while independent days would imply about 18 %.
ponytail: Gaussian on the raw scale, so k-day sums stay Gaussian but single days' right skew is ignored and intervals over
a few days are rough; blocks are calendar months, not pay cycles. Upgrade: a compound Poisson-gamma day model, pay-cycle
blocks.

Prior (Normal-Inverse-Gamma, population level). beta | sigma^2 ~ N(m0, sigma^2 / kappa0), sigma^2 ~ InvGamma(a0, b0):
    m0     = exp(c0 + c1 ln(net monthly pay) + tau^2 / 2)  least squares of ln(mean monthly total) on ln(net pay),
    kappa0 = r / tau^2                                      so that Var(beta) is about tau^2 m0^2,
    b0     = (a0 - 1) r m0^2                                so that E[sigma^2] = r m0^2,
    a0     = 2 + mean(r_i)^2 / var(r_i)                     inverse-gamma moments matched to the spread of r_i,
with r_i = sigma_i^2 / beta_i^2 (pooled within-month variance of a day over the squared mean monthly total), r its mean,
tau^2 the regression's residual variance less the mean sampling variance of ln(beta_i) (phi D r_i / J_i for J_i months),
and phi the mean over persons of var(month totals) / (D sigma_i^2). All from full calendar months of other persons only.
Net pay is the only covariate because it is the only one an uploaded statement reveals (affordability.detect_income);
household type adds little on these data (residual variance of ln budget 0.020 with net pay alone, 0.016 with it).

Update (exact, one day at a time). Given n earlier days of the same month with sum s, a new day y satisfies
    y | earlier days, beta, sigma^2 ~ N(c + g beta, v sigma^2),
    e = 1 / (1 + (n - 1) rho),   g = (1 - n rho e) / D,   c = rho e s,   v = 1 - n rho^2 e,
so kappa' = kappa + g^2 / v,  m' = (kappa m + g (y - c) / v) / kappa',  a' = a + 1/2,
   b' = b + (y - c - g m)^2 / (2 (v + g^2 / kappa)).
By the chain rule this equals the batch posterior computed with the full covariance matrix (asserted in --check).

Predictive. For k future days in a month of which n days (sum s) have been seen, E[F | data, beta] = A beta + C with
A = k (1 - n rho e) / D and C = k rho e s, and Var(F | data, beta, sigma^2) = V sigma^2 with
V = k (1 + (k - 1) rho) - k^2 n rho^2 e; months add. Integrating out beta and sigma^2 gives a Student t with 2a degrees
of freedom, location A m + C and squared scale (b / a)(V + A^2 / kappa).

Shortfall. P(cushion - max(0, F) < 0), where cushion = balance after the statement's last day - committed payments and BNPL
instalments due after that day and before payday - the purchase (the full price, or the pay-in-3 instalments due before
payday), and F is discretionary spending on the days from the day after the statement's last day to the day before
payday. Negative predictive mass is censored at zero for spending means, intervals and risk; a negative cushion always
means a shortfall. This physical constraint does not establish calibration on real-world spending shocks.
With no credits before payday the balance only falls, so this is also the probability of dropping below zero at
any point before payday.

Run:   .venv\\Scripts\\python -X utf8 bayes.py          # October backtest: writes Analysis/bayes/ and Figures/bayes/
Check: .venv\\Scripts\\python -X utf8 bayes.py --check  # asserts only; writes nothing
"""
import argparse
import calendar
import datetime as dt
import functools
import math
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import linalg, stats

import affordability as af
import mock_statements as ms


def _fc():
    """forecast.py, imported late: it loads matplotlib and TeXFormat, which the API (affordability.py) does not need."""
    import forecast
    return forecast

HERE = Path(__file__).resolve().parent
ANA, FIG = HERE / "Analysis" / "bayes", HERE / "Figures" / "bayes"
ORIGIN, TODAY = dt.date(2026, 9, 30), dt.date(2026, 10, 1)  # backtest: fit on rows up to ORIGIN, purchase on TODAY
OCT = (2026, 10)
START = dt.date(*ms.MONTHS[0], 1)                            # first day the mock statements cover
HORIZONS = (7, 14, 21, 28, 31)                                # cumulative October spending on days 1 to d
LEVELS = (0.5, 0.8, 0.95)
PRICES = (50, 300, 1200)
SIM_SEED = 20261107
MODELS = {"budget": r"Monthly budget ($\hat\phi$ fitted)", "iid": r"Independent days ($\phi = 1$)"}
BINS = [0, 0.05, 0.2, 0.5, 0.8, 0.95, 1.0]


# ---------------------------------------------------------------- data
def blocks(tx, as_of=None, start=None):
    """{(year, month): (days in month, array of daily discretionary spending on the observed days)}, from start to
    as_of (defaults: the first and the last transaction's dates; a statement known to cover more days can say so)."""
    as_of = as_of or tx[-1]["date"]
    rows = [t for t in tx if t["date"] <= as_of]
    fixed = {(c["name"], c["amount"]) for c in af.detect_committed(rows, as_of)}
    d0 = start or rows[0]["date"]
    x = np.zeros((as_of - d0).days + 1)
    for t in rows:
        if t["type"] == "DEB" and t["debit"] > 0 and not af.BNPL.search(t["desc"]) and (t["desc"], t["debit"]) not in fixed:
            x[(t["date"] - d0).days] += t["debit"]
    out = {}
    for i, v in enumerate(x):
        d = d0 + dt.timedelta(days=i)
        out.setdefault((d.year, d.month), []).append(v)
    return {k: (calendar.monthrange(*k)[1], np.array(v)) for k, v in out.items()}


def days(first, last):
    """{(year, month): number of days} for the days first to last inclusive."""
    return Counter((d.year, d.month) for d in (first + dt.timedelta(days=i) for i in range((last - first).days + 1)))


def head(blk, t):
    """The first t observed days of blk."""
    out = {}
    for key, (D, x) in blk.items():
        if t <= 0:
            break
        out[key], t = (D, x[:t]), t - len(x)
    return out


# ---------------------------------------------------------------- model
def fit_prior(people, phi=None):
    """Population hyperparameters from [(blocks, net monthly pay)] (full months only; at least two per person).
    phi=None estimates phi; a number fixes it (phi=1: independent days)."""
    rows = []
    for blk, net in people:
        full = [x for D, x in blk.values() if len(x) == D]
        if len(full) < 2:
            continue
        S = np.array([x.sum() for x in full])
        s2 = sum(((x - x.mean()) ** 2).sum() for x in full) / sum(len(x) - 1 for x in full)
        # ponytail: s2 estimates sigma^2 (1 - rho), about 3 % low when phi is near 0; ignored
        D = np.mean([len(x) for x in full])
        rows.append((math.log(net), math.log(S.mean()), s2 / S.mean() ** 2, S.var(ddof=1) / (s2 * D), D, len(full)))
    ln_net, ln_b, r, ph, D, J = map(np.array, zip(*rows))
    phi = float(ph.mean()) if phi is None else float(phi)
    Z = np.column_stack([np.ones(len(rows)), ln_net])
    coef = np.linalg.lstsq(Z, ln_b, rcond=None)[0]
    res = ln_b - Z @ coef
    tau2 = max(res @ res / (len(rows) - 2) - np.mean(phi * D * r / J), 1e-6)
    return dict(c0=coef[0], c1=coef[1], tau2=tau2, r=r.mean(), a0=2 + r.mean() ** 2 / r.var(ddof=1), phi=phi,
                kappa0=r.mean() / tau2, n=len(rows))


def prior(h, net):
    """(m0, kappa0, a0, b0) for a person with net monthly pay `net`."""
    m0 = math.exp(h["c0"] + h["c1"] * math.log(net) + h["tau2"] / 2)
    return m0, h["kappa0"], h["a0"], (h["a0"] - 1) * h["r"] * m0 ** 2


def posterior(nig, blk, phi):
    """Normal-Inverse-Gamma (m, kappa, a, b) after updating `nig` one observed day at a time."""
    m, k, a, b = nig
    for D, x in blk.values():
        rho, s = (phi - 1) / (D - 1), 0.0
        for n, y in enumerate(x):
            e = 1 / (1 + (n - 1) * rho)
            g, c, v = (1 - n * rho * e) / D, rho * e * s, 1 - n * rho * rho * e
            resid, k2 = y - c - g * m, k + g * g / v
            b += resid ** 2 / (2 * (v + g * g / k))
            m, k, a, s = (k * m + g * (y - c) / v) / k2, k2, a + 0.5, s + y
    return m, k, a, b


def predictive(post, blk, phi, future):
    """Student-t (scipy frozen) of total discretionary spending over `future` ({(year, month): days}), given the
    posterior and the days already seen in blk."""
    m, kap, a, b = post
    A = C = V = 0.0
    for key, k in future.items():
        D = calendar.monthrange(*key)[1]
        rho, x = (phi - 1) / (D - 1), blk.get(key, (D, np.zeros(0)))[1]
        n, s = len(x), x.sum()
        assert n + k <= D, f"{key}: {n} days seen and {k} to come"
        e = 1 / (1 + (n - 1) * rho)
        A, C = A + k * (1 - n * rho * e) / D, C + k * rho * e * s
        V += k * (1 + (k - 1) * rho) - k * k * n * rho * rho * e
    return stats.t(2 * a, loc=A * m + C, scale=math.sqrt(b / a * (V + A * A / kap)))


def credible(post):
    """Student-t posterior of the monthly budget beta."""
    m, k, a, b = post
    return stats.t(2 * a, loc=m, scale=math.sqrt(b / (a * k)))


@functools.cache
def population():
    """Hyperparameters fitted on every statement in Analysis/mock_statements, which cover START to ms.END."""
    people = []
    for f in sorted(af.STATEMENTS.glob("persona[0-9][0-9][0-9]_*.csv")):
        tx = af.parse(f.read_text(encoding="utf-8"))
        people.append((blocks(tx, ms.END, START), af.detect_income(tx)["monthly"]))
    return fit_prior(people)


def shortfall_probability(tx, price, today=None, payday=None, pay_in_3=False, hyper=None):
    """Probability that the balance falls below zero before payday after buying at `price` [GBP] on `today`.
    tx: affordability.parse output. today, payday: dates (defaults as affordability.assess: the day after the last
    transaction; the detected next payday). pay_in_3: pay by affordability's plain pay-in-3 schedule instead of in full.
    hyper: population hyperparameters (default population()). Returns a dict; the probability is 'probability'."""
    a = af.assess(tx, price, today)
    as_of, today = dt.date.fromisoformat(a["asOf"]), dt.date.fromisoformat(a["today"])
    if not a["income"]:
        raise af.StatementError("No salary detected; the spending prior needs net monthly pay.")
    if a["assessmentStatus"] == "incomplete":
        raise af.StatementError(" ".join(a["assessmentWarnings"]))
    payday = payday or dt.date.fromisoformat(a["income"]["nextPayday"])
    due = lambda d: as_of < dt.date.fromisoformat(d) < payday
    out = (sum(c["amount"] for c in a["committed"] if due(c["due"]))
           + sum(s["amount"] for p in a["bnplPlans"] for s in p["schedule"] if due(s["due"])))
    plan = next(o for o in a["options"] if o["kind"] == "bnplPlain")["schedule"]
    buy = ([(dt.date.fromisoformat(s["due"]), s["amount"]) for s in plan if dt.date.fromisoformat(s["due"]) < payday]
           if pay_in_3 else [(today, float(price))])
    cushion = a["balance"] - out - sum(x for _, x in buy)
    first, last = as_of + dt.timedelta(days=1), payday - dt.timedelta(days=1)
    res = dict(probability=float(cushion < 0), cushion=af.money(cushion), spendMean=0.0, spend80=[0.0, 0.0],
               firstDay=first, lastDay=last, payday=payday, purchaseDue=buy, committedAndBnplDue=af.money(out))
    F = spending_until(tx, payday, hyper)
    if F is None:  # no day left before payday
        return res
    summary = spending_summary(F)
    return res | dict(probability=spending_risk(F, cushion), spendMean=summary["mean"], spend80=summary["interval80"])


def spending_summary(F):
    """Mean and central 80% interval of max(0, F), for the raw Student-t spending predictive (None means zero days).
    The positive-part mean is loc * P(T > z) + scale * (df + z^2)/(df - 1) * t_pdf(z), z = -loc/scale.
    Censoring moves negative mass to zero; merely clipping the mean would not be the expectation of this distribution.
    ponytail: this enforces non-negative expenditure, not calibration on real spending shocks; replace the raw Gaussian
    daily likelihood with a non-negative spending model when real-data validation is available."""
    if F is None:
        return dict(mean=0.0, interval80=[0.0, 0.0])
    loc, scale, df = float(F.mean()), F.kwds["scale"], F.args[0]
    z = -loc / scale
    mean = loc * stats.t.sf(z, df) + scale * (df + z * z) / (df - 1) * stats.t.pdf(z, df)
    return dict(mean=max(0.0, float(mean)), interval80=[max(0.0, float(x)) for x in F.interval(0.8)])


def spending_risk(F, cushion):
    """P(max(0, F) > cushion): a negative cash cushion is a certain shortfall, even if F has negative mass."""
    if cushion < 0:
        return 1.0
    return float(F.sf(cushion)) if F is not None else 0.0


def spending_until(tx, payday, hyper=None):
    """Raw Student-t predictive from the day after the last transaction to the day before payday, or None for no days.
    Use spending_summary and spending_risk to obtain non-negative expenditure statistics for decisions."""
    first, last = tx[-1]["date"] + dt.timedelta(days=1), payday - dt.timedelta(days=1)
    if last < first:
        return None
    h = hyper or population()
    blk = blocks(tx)
    return predictive(posterior(prior(h, af.detect_income(tx)["monthly"]), blk, h["phi"]), blk, h["phi"], days(first, last))


# ---------------------------------------------------------------- October backtest
def fit(st):
    """Fit on the rows up to 30 September only, with person-level cross-validation (forecast.py's folds): each
    person's prior comes from the other folds. Returns per-person results, hyperparameters by fold, folds."""
    fc = _fc()
    pids = sorted(st)
    tx9 = {p: [t for t in st[p] if t["date"] <= ORIGIN] for p in pids}
    blk = {p: blocks(tx9[p], ORIGIN, START) for p in pids}
    net = {p: af.detect_income(tx9[p])["monthly"] for p in pids}
    fold = np.random.default_rng(fc.SEED).permutation(len(pids)) % fc.FOLDS
    H = {}
    for k in range(fc.FOLDS):
        train = [(blk[p], net[p]) for p, f in zip(pids, fold) if f != k]
        H[k] = dict(budget=fit_prior(train), iid=fit_prior(train, phi=1.0))
    R = {}
    for p, f in zip(pids, fold):
        R[p] = dict(blk=blk[p], net=net[p], fold=int(f))
        for name, h in H[f].items():
            post = posterior(prior(h, net[p]), blk[p], h["phi"])
            R[p][name] = dict(post=post, pred={d: predictive(post, blk[p], h["phi"], {OCT: d}) for d in HORIZONS})
        R[p]["shortfall"] = {(price, plan): shortfall_probability(tx9[p], price, TODAY, pay_in_3=plan,
                                                                  hyper=H[f]["budget"])
                             for price in PRICES for plan in (False, True)}
    return R, H, fold


def outcome(tx, s):
    """Lowest balance from the purchase day to the day before payday, after the purchase payments then due."""
    start = [t["balance"] for t in tx if t["date"] < s["firstDay"]][-1]
    path = [(min(d for d, _ in s["purchaseDue"]), start)] + [(t["date"], t["balance"]) for t in tx
                                                             if s["firstDay"] <= t["date"] <= s["lastDay"]]
    return min(b - sum(x for d, x in s["purchaseDue"] if d <= when) for when, b in path)


def binom(k, n):
    p = k / n
    return p, math.sqrt(p * (1 - p) / n)


def run():
    fc = _fc()
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import TeXFormat as tf

    T, C, cats, P, M, comps, CM, info, means, st = fc.run(write=False)
    R, H, fold = fit(st)
    pids = list(T.index)
    assert pids == sorted(R)
    ANA.mkdir(parents=True, exist_ok=True)
    FIG.mkdir(parents=True, exist_ok=True)
    md = fc.md_table

    # ---- intervals
    rows = []
    for i, p in enumerate(pids):
        for name in MODELS:
            for d in HORIZONS:
                F, y = R[p][name]["pred"][d], C["oct"][i, d]
                r = dict(persona=p, model=name, day=d, actual=y, mean=F.mean())
                for L in LEVELS:
                    lo, hi = F.interval(L)
                    r |= {f"lo{L * 100:.0f}": lo, f"hi{L * 100:.0f}": hi, f"in{L * 100:.0f}": int(lo <= y <= hi)}
                rows.append(r)
    I = pd.DataFrame(rows)
    I.round(2).to_csv(ANA / "intervals_october.csv", index=False, lineterminator="\n")
    cov = {}
    for (name, d), g in I.groupby(["model", "day"]):
        for L in LEVELS:
            q = f"{L * 100:.0f}"
            w = g[f"hi{q}"] - g[f"lo{q}"]
            cov[name, d, L] = (*binom(int(g[f"in{q}"].sum()), len(g)), w.mean(), w.std(ddof=1) / math.sqrt(len(g)), len(g))

    # ---- point forecasts against T12
    actual = T.disc_oct.to_numpy()
    bayes_mean = np.array([R[p]["budget"]["pred"][31].mean() for p in pids])
    MB = fc.metrics(bayes_mean, actual)
    pairs = {b: fc.paired(bayes_mean, P[b], actual) for b in ("last", "mean", "regression", "shrinkage")}

    # ---- shortfall
    srows = []
    for p in pids:
        for (price, plan), s in R[p]["shortfall"].items():
            low = outcome(st[p], s)
            srows.append(dict(persona=p, price=price, plan="pay-in-3" if plan else "pay now", payday=s["payday"],
                              first_day=s["firstDay"], last_day=s["lastDay"],
                              purchase_due=sum(x for _, x in s["purchaseDue"]),
                              committed_bnpl_due=s["committedAndBnplDue"], cushion=s["cushion"],
                              spend_mean=s["spendMean"], spend_lo80=s["spend80"][0], spend_hi80=s["spend80"][1],
                              p_shortfall=s["probability"], actual_lowest_balance=low, shortfall=int(low < 0)))
    S = pd.DataFrame(srows)
    S.round(6).to_csv(ANA / "shortfall_october.csv", index=False, lineterminator="\n")
    credits = sum(t["credit"] > 0 for p in pids for t in st[p] if TODAY <= t["date"] < S.payday.iloc[0])

    def brier(g):
        o, q = g.shortfall.to_numpy(), g.p_shortfall.to_numpy()
        e = (q - o) ** 2
        return [len(g), int(o.sum()), f"{e.mean():.4f} ± {e.std(ddof=1) / math.sqrt(len(g)):.4f}",
                f"{o.mean() * (1 - o.mean()):.4f}"]
    brier_rows = [[plan, price, *brier(g)] for (plan, price), g in S.groupby(["plan", "price"], sort=False)]
    brier_rows += [[plan, "all three", *brier(g)] for plan, g in S.groupby("plan", sort=False)]
    rel = {}
    for plan, g in S.groupby("plan", sort=False):
        b = np.clip(np.digitize(g.p_shortfall, BINS[1:-1]), 0, len(BINS) - 2)
        rel[plan] = [[f"{BINS[j]:.2f} to {BINS[j + 1]:.2f}", int((b == j).sum()),
                      f"{g.p_shortfall[b == j].mean():.3f}" if (b == j).any() else "not applicable",
                      int(g.shortfall[b == j].sum()),
                      "{:.3f} ± {:.3f}".format(*binom(int(g.shortfall[b == j].sum()), int((b == j).sum())))
                      if (b == j).any() else "not applicable"] for j in range(len(BINS) - 1)]

    # ---- shared text
    hyp = pd.DataFrame([H[k]["budget"] for k in range(fc.FOLDS)])
    hyp_iid = pd.DataFrame([H[k]["iid"] for k in range(fc.FOLDS)])
    pop = population()
    hrow = lambda name, k, f: [name, f"{hyp[k].mean():{f}} ± {hyp[k].std(ddof=1):{f}}",
                               f"{hyp_iid[k].mean():{f}} ± {hyp_iid[k].std(ddof=1):{f}}", f"{pop[k]:{f}}"]
    hyper_md = md(["Hyperparameter", "Monthly budget, mean ± SD over the 10 folds", "Independent days (phi = 1), "
                   "mean ± SD over folds", "Default for live use (all 100 statements, Aug-Oct)"],
                  [hrow("c0 (intercept, ln GBP)", "c0", ".4f"), hrow("c1 (slope on ln net pay)", "c1", ".4f"),
                   hrow("tau^2 (between-person variance of ln budget)", "tau2", ".4g"),
                   hrow("r (daily variance / budget^2)", "r", ".4g"), hrow("a0", "a0", ".3f"),
                   hrow("kappa0 = r / tau^2", "kappa0", ".4g"), hrow("phi", "phi", ".4f"),
                   hrow("persons used per fit", "n", ".0f")])
    src = ("Source: the 100 statements in `Analysis/mock_statements/`, via `bayes.py` (which reuses `forecast.py` and "
           "`affordability.py`). Discretionary spending as in `affordability.card_spend` (card payments that are neither "
           "BNPL instalments nor committed payments), committed payments detected on the rows up to 30 September 2026. "
           "Every model is fitted on the rows up to 30 September only (August and September); each person's prior "
           f"comes from a fit on the other persons, by person-level {fc.FOLDS}-fold cross-validation with forecast.py's "
           f"folds (seed {fc.SEED}). October is used only to score. "
           + fc.commits("bayes.py", "forecast.py", "affordability.py") + "\n")
    model_txt = ("Model (full derivation in the docstring of `bayes.py`): daily discretionary spending, Gaussian on the "
                 "raw scale; within a calendar month of D days each day has mean beta / D (beta: the person's monthly "
                 "budget) and variance sigma^2, and two days of the same month have correlation (phi - 1) / (D - 1), so "
                 "a month's total has variance phi D sigma^2. Normal-Inverse-Gamma prior on (beta, sigma^2) centred on a "
                 "population regression of ln budget on ln net pay; exact conjugate update after each day; Student-t "
                 "predictive for the sum over any set of future days. The independent-days model is the same with "
                 "phi fixed at 1.\n")

    plt.style.use(Path(tf.__file__).with_name("TeXFormat.mplstyle"))
    marks = "osD^v"
    # ---- figure (i): calibration
    fig, axes = plt.subplots(1, 2, figsize=(17, 7.5), sharey=True)
    for ax, name, lab in zip(axes, MODELS, ("(a)", "(b)")):
        ax.plot([0.4, 1.0], [0.4, 1.0], color="k", lw=1.2, ls="--", label=r"$y = x$")
        for j, (d, col, mk) in enumerate(zip(HORIZONS, tf.CYCLE, marks)):
            x = np.array(LEVELS) + (j - 2) * 0.008
            y, se = (np.array([cov[name, d, L][q] for L in LEVELS]) for q in (0, 1))
            ax.errorbar(x, y, yerr=se, fmt=mk, color=col, ms=8, capsize=3,
                        label=f"days 1 to {d}" if d < 31 else "October total")
        ax.set(xlim=(0.4, 1.02), ylim=(0.4, 1.03), xlabel="Nominal coverage", title=MODELS[name])
        ax.text(0.03, 0.95, lab, transform=ax.transAxes, ha="left", va="top", fontsize=tf.fontsizeSmall)
    axes[0].set_ylabel("Empirical coverage, October")
    axes[0].legend(frameon=True, fancybox=False, fontsize=tf.fontsizeTiny, loc="lower right")
    fig.tight_layout()
    for ext in ("pdf", "svg"):
        fig.savefig(FIG / f"calibration.{ext}")
    plt.close(fig)
    cov_rows = [[MODELS[name].replace("$\\hat\\phi$", "phi").replace("$\\phi = 1$", "phi = 1"),
                 "October total" if d == 31 else f"days 1 to {d}", f"{L:.2f}",
                 f"{cov[name, d, L][0]:.2f} ± {cov[name, d, L][1]:.2f}", cov[name, d, L][4],
                 f"{cov[name, d, L][2]:.1f} ± {cov[name, d, L][3]:.1f}"]
                for name in MODELS for d in HORIZONS for L in LEVELS]
    ok = lambda name: sum(abs(cov[name, d, L][0] - L) <= 2 * max(cov[name, d, L][1], 1e-9) for d in HORIZONS
                          for L in LEVELS)
    oct_tot = np.mean(actual)
    (FIG / "calibration.md").write_text(
        "# Calibration of the posterior predictive intervals, October 2026\n\nPlot: `calibration.pdf` / `.svg`. Written "
        f"by `bayes.py`; regenerate with it.\n\n## Source and transformations\n\n{src}\n{model_txt}\n"
        "For each person, central posterior predictive intervals (50 %, 80 %, 95 %) of cumulative October discretionary "
        "spending on days 1 to d (d = 7, 14, 21, 28) and of the October total (d = 31), from the posterior after 30 "
        "September; empirical coverage = fraction of the 100 persons whose actual value lies inside the interval. Points: "
        "empirical coverage against nominal level, offset slightly along x by horizon for legibility; error bars ± one "
        "binomial standard error, sqrt(p (1 - p) / n), which is 0 when p = 1. Dashed line: perfect calibration. The 15 "
        "points of a panel use the same 100 persons and are not independent. Per-person intervals: "
        "`Analysis/bayes/intervals_october.csv`.\n\n## Hyperparameters\n\n" + hyper_md
        + "\n## Coverage and mean interval width\n\nWidth: mean ± SE across persons [GBP].\n\n"
        + md(["Model", "Horizon", "Nominal", "Empirical coverage (± binomial SE)", "n", "Mean width [GBP] (± SE)"],
             cov_rows)
        + f"\nMean actual October total: {oct_tot:.2f} GBP.\n\nRandom seed: not applicable (no sampling; fold "
        f"assignment seed {fc.SEED}).\n\n## Interpretation\n\nMonthly budget: {ok('budget')} of 15 coverages lie within two "
        f"binomial standard errors of nominal; independent days: {ok('iid')} of 15. The independent-days model "
        "treats a month's total as the sum of 31 independent days, which on these statements makes its intervals for "
        f"the October total about {cov['iid', 31, 0.8][2] / cov['budget', 31, 0.8][2]:.1f} times as wide as the budget "
        "model's (80 % level), so it covers almost everyone. The budget model's phi, estimated from August and September, "
        "carries the generator's fixed monthly totals into the intervals; at 7 days the two models differ little, "
        "because a week's spending varies nearly as independent days would.\n\n" + fc.NOISE,
        encoding="utf-8", newline="\n")

    # ---- figure (ii): cold start
    gap = {p: abs(math.log(prior(H[R[p]["fold"]]["budget"], R[p]["net"])[0] / R[p]["budget"]["post"][0])) for p in pids}
    ex = [min(gap, key=gap.get), max(gap, key=gap.get)]
    tmax = sum(len(x) for _, x in R[ex[0]]["blk"].values())
    fig, axes = plt.subplots(1, 2, figsize=(17, 7.5))
    cold, jumps = [], []
    for ax, p, lab in zip(axes, ex, ("(a)", "(b)")):
        h, i = H[R[p]["fold"]]["budget"], pids.index(p)
        pr = prior(h, R[p]["net"])
        ts = np.arange(tmax + 1)
        posts = [posterior(pr, head(R[p]["blk"], t), h["phi"]) for t in ts]
        cr = np.array([[credible(q).mean(), *credible(q).interval(0.95)] for q in posts])
        pd_ = np.array([[*predictive(q, head(R[p]["blk"], t), h["phi"], {OCT: 31}).interval(0.95)]
                        for q, t in zip(posts, ts)])
        ax.plot(ts, pd_[:, 0], color=tf.CYCLE[2], ls="-.", lw=1.2, label="95 \\% predictive, October total")
        ax.plot(ts, pd_[:, 1], color=tf.CYCLE[2], ls="-.", lw=1.2)
        ax.fill_between(ts, cr[:, 1], cr[:, 2], color=tf.CYCLE[0], alpha=0.3, lw=0, label="95 \\% credible, budget")
        ax.plot(ts, cr[:, 0], color=tf.CYCLE[0], label="Posterior mean budget")
        ax.axhline(P.generator[p], color=tf.CYCLE[1], ls="--", lw=1.2, label="Generator mean, October")
        ax.axhline(actual[i], color="k", ls=":", lw=1.2, label="Actual October total")
        ax.axvline(31, color="0.6", lw=0.8)
        ax.set(xlabel="Days observed (from 1 August)", xlim=(0, tmax), title=f"{p}, net pay {R[p]['net']:.0f} GBP")
        ax.set_ylabel("Monthly discretionary spending [GBP]")
        ax.text(0.97, 0.04, lab, transform=ax.transAxes, ha="right", va="bottom", fontsize=tf.fontsizeSmall)
        xs = np.concatenate([x for _, x in R[p]["blk"].values()])
        jumps += [f"{p}: after day {t + 1} ({START + dt.timedelta(days=t)}, spending {xs[t]:.2f} GBP) the posterior "
                  f"mean moved from {cr[t, 0]:.2f} to {cr[t + 1, 0]:.2f} GBP, outside the previous 95 % credible "
                  f"interval ({cr[t, 1]:.2f} to {cr[t, 2]:.2f})" for t in range(tmax)
                  if not cr[t, 1] <= cr[t + 1, 0] <= cr[t, 2]]
        for t in (0, 7, 14, 30, tmax):
            cold.append([p, t, f"{pr[0]:.2f}", f"{cr[t, 0]:.2f}", f"{cr[t, 1]:.2f} to {cr[t, 2]:.2f}",
                         f"{cr[t, 2] - cr[t, 1]:.2f}", f"{pd_[t, 0]:.2f} to {pd_[t, 1]:.2f}", f"{pd_[t, 1] - pd_[t, 0]:.2f}",
                         f"{posts[t][2]:.1f}"])
        lo = min(cr[:, 1].min(), pd_[:, 0].min(), actual[i])
        hi = max(cr[:, 2].max(), pd_[:, 1].max(), actual[i])
        ax.set_ylim(lo - 0.05 * (hi - lo), hi + 0.45 * (hi - lo))
    axes[0].legend(frameon=True, fancybox=False, fontsize=tf.fontsizeTiny, loc="upper center", ncol=2)
    fig.tight_layout()
    for ext in ("pdf", "svg"):
        fig.savefig(FIG / f"cold_start.{ext}")
    plt.close(fig)
    (FIG / "cold_start.md").write_text(
        "# Cold start: the posterior as days of spending are observed\n\nPlot: `cold_start.pdf` / `.svg`. Written by "
        f"`bayes.py`; regenerate with it.\n\n## Source and transformations\n\n{src}\n{model_txt}\n"
        f"Two example persons, chosen by rule: the persons whose prior mean budget is closest to ({ex[0]}) and furthest "
        f"from ({ex[1]}) their posterior mean after 30 September (absolute log ratio). For t = 0 (prior only) to {tmax} "
        "days observed from 1 August, the monthly-budget posterior after the first t days: posterior mean of beta "
        "(line), 95 % central credible interval of beta (dark band), and 95 % central posterior predictive interval "
        "of the October total (light band; budget uncertainty plus October's own variation). Dashed: the generator's "
        "expected October discretionary spending (`forecast.generator_mean`, a reference using the generator's "
        "internals); dotted: the actual October total; grey vertical line: end of August. Each person's prior comes "
        f"from the cross-validation fold that excludes them. Units GBP. n = 1 person per panel, {tmax + 1} posteriors "
        "each.\n\n## Values at selected days\n\n"
        + md(["Person", "Days observed", "Prior mean [GBP]", "Posterior mean budget [GBP]", "95 % credible [GBP]",
              "Width [GBP]", "95 % predictive, October total [GBP]", "Width [GBP]", "a (posterior shape)"], cold)
        + "\n" + md(["Person", "Generator mean, October [GBP]", "Actual October [GBP]", "Net monthly pay [GBP]"],
                    [[p, f"{P.generator[p]:.2f}", f"{actual[pids.index(p)]:.2f}", f"{R[p]['net']:.2f}"] for p in ex])
        + "\nRandom seed: not applicable.\n\n## Interpretation\n\nWith no data the interval is the population prior "
        "(its width set by tau^2, the between-person spread left after net pay). During the first days the data barely "
        "move it, because a few days' spending says little about a month's total. As the first month fills, each "
        "day becomes more informative, since under the budget model the days still to come in a month must make up "
        "its total; the credible interval collapses near the end of August and narrows again through September. "
        "The predictive interval for October cannot shrink below October's own variation, phi D sigma^2. "
        + ("Days on which one day's spending moved the posterior mean outside its previous 95 % credible interval: "
           + "; ".join(jumps) + ". Single days are right-skewed (a few large card payments), which the Gaussian "
           "likelihood ignores, so near the end of a month one large day can move the estimate further than the "
           "interval allowed." if jumps else "No single day moved the posterior mean outside its previous 95 % "
           "credible interval.") + "\n\n" + fc.NOISE,
        encoding="utf-8", newline="\n")

    # ---- summary
    pair_rows = [[fc.MODELS[b], f"{fc.metrics(P[b], actual)['MAE']:.2f} ± {fc.metrics(P[b], actual)['MAE_SE']:.2f}",
                  f"{c['diff']:+.2f} ± {c['diff_SE']:.2f}", f"{c['t']:.2f}", fc.pv(c["p_t"]), f"{c['W']:.0f}",
                  fc.pv(c["p_w"])] for b, c in pairs.items()]
    (ANA / "bayes_summary.md").write_text(
        "# Bayesian spending model: October backtest\n\nWritten by `bayes.py`; regenerate with it. Calibration: "
        "`Figures/bayes/calibration.md`; cold start: `Figures/bayes/cold_start.md`.\n\n"
        f"{src}\n{model_txt}\n## Hyperparameters\n\n" + hyper_md
        + "\n## Point forecast of the October total\n\nPosterior predictive mean of the monthly-budget model against "
        "T12's forecasts (`forecast.py`), absolute error per person, n = 100; difference = Bayes minus the other "
        "(negative: Bayes better); paired t and Wilcoxon signed-rank tests, two-sided, uncorrected.\n\n"
        f"Bayes posterior predictive mean: MAE {MB['MAE']:.2f} ± {MB['MAE_SE']:.2f} GBP, RMSE {MB['RMSE']:.2f} ± "
        f"{MB['RMSE_SE']:.2f} GBP, mean error {MB['bias']:+.2f} ± {MB['bias_SE']:.2f} GBP.\n\n"
        + md(["T12 forecast", "MAE [GBP] (± SE)", "Bayes minus it, absolute error [GBP] (± SE)", "Paired t", "p (t)",
              "Wilcoxon W", "p (W)"], pair_rows)
        + "\n## Shortfall: probability of going below zero before the October payday\n\n"
        f"Purchases of GBP {', '.join(map(str, PRICES))} on {TODAY}, paid in full or by affordability's plain pay-in-3 "
        "schedule (first instalment on the day; the others fall after payday), using each statement up to 30 "
        "September. Predicted: `shortfall_probability` with the person's cross-validated prior. Observed: whether the "
        "actual balance, less the purchase payments then due, fell below zero on any day from 1 October to the day "
        f"before the detected payday ({', '.join(sorted({str(d) for d in S.payday}))}). Credits in that window across all "
        f"statements: {credits}, so the balance only falls and the lowest balance is the last one. Per-person data: "
        "`Analysis/bayes/shortfall_october.csv`.\n\nBrier score = mean of (p - outcome)^2 (± SE across persons); "
        "reference = Brier score of always predicting the observed frequency, o (1 - o).\n\n"
        + md(["Plan", "Price [GBP]", "n", "Shortfalls observed", "Brier (± SE)", "Reference o (1 - o)"], brier_rows)
        + "".join(f"\nReliability, {plan}, all three prices pooled (n = {len(S[S.plan == plan])}; observed frequency ± "
                  "binomial SE):\n\n" + md(["Predicted probability", "n", "Mean predicted", "Shortfalls",
                                             "Observed frequency (± SE)"], rel[plan]) for plan in rel)
        + "\nWith 100 persons and few shortfalls these figures are noisy: most persons' cushions are far from zero, so "
        "most predictions are near 0 or 1 and only a handful test the model's uncertainty.\n\n" + fc.NOISE,
        encoding="utf-8", newline="\n")

    print(md(["Model", "Horizon", "Nominal", "Coverage (± SE)", "n", "Width (± SE)"], cov_rows))
    print(f"Bayes MAE {MB['MAE']:.2f} ± {MB['MAE_SE']:.2f}")
    print(md(["T12", "MAE", "diff", "t", "p", "W", "p"], pair_rows))
    print(md(["Plan", "Price", "n", "Shortfalls", "Brier", "Ref"], brier_rows))
    for plan in rel:
        print(plan)
        print(md(["Bin", "n", "Mean p", "Shortfalls", "Freq"], rel[plan]))
    print(md(["Person", "t", "Prior", "Mean", "95 % cred", "W", "95 % pred", "W", "a"], cold))
    print(hyper_md)


# ---------------------------------------------------------------- self-check
def batch(nig, blk, phi):
    """Batch posterior with the full covariance matrix (for the check)."""
    m0, k0, a0, b0 = nig
    h = np.concatenate([np.full(len(x), 1 / D) for D, x in blk.values()])
    x = np.concatenate([x for _, x in blk.values()])
    Ri = np.linalg.inv(linalg.block_diag(*[(1 - (r := (phi - 1) / (D - 1))) * np.eye(len(v)) + r
                                           for D, v in blk.values()]))
    k = k0 + h @ Ri @ h
    m = (k0 * m0 + h @ Ri @ x) / k
    return m, k, a0 + len(x) / 2, b0 + (x @ Ri @ x + k0 * m0 ** 2 - k * m ** 2) / 2


def check():
    fc = _fc()
    st, info = fc.load()
    T = fc.table(st, info)[0]
    h = population()
    # Censored spending: analytic positive-part expectation agrees with independent numerical integration.
    for loc in (-20, -3, 0, 5):
        F = stats.t(8, loc=loc, scale=2)
        summary = spending_summary(F)
        assert math.isclose(summary["mean"], F.expect(lambda x: x, lb=0), rel_tol=1e-7)
        assert all(x >= 0 for x in summary["interval80"])
        assert spending_risk(F, -0.01) == 1.0 and spending_risk(F, 0) == F.sf(0)
    assert spending_summary(None) == dict(mean=0.0, interval80=[0.0, 0.0])
    assert spending_risk(None, -1) == 1.0 and spending_risk(None, 0) == 0.0
    # Data: month sums equal forecast.py's discretionary spending for August and September.
    for p in sorted(st):
        blk = blocks([t for t in st[p] if t["date"] <= ORIGIN], ORIGIN, START)
        assert np.allclose([x.sum() for _, x in blk.values()], [T.disc_aug[p], T.disc_sep[p]]), p
    # Sequential daily updates equal the batch posterior (full covariance), with a partial month and both phi.
    p = sorted(st)[0]
    blk = blocks(st[p], dt.date(2026, 10, 12))
    for phi in (h["phi"], 1.0, 2.5):
        nig = prior(h | dict(phi=phi), 2500.0)
        assert np.allclose(posterior(nig, blk, phi), batch(nig, blk, phi), rtol=1e-9), phi
    # Simulated from the model itself: 80 % predictive intervals cover close to 80 %.
    rng = np.random.default_rng(SIM_SEED)
    phi, (m0, k0, a0, b0) = h["phi"], prior(h, 2500.0)
    months = [(2026, 8), (2026, 9), (2026, 10), (2026, 11)]
    L = {D: np.linalg.cholesky((1 - (r := (phi - 1) / (D - 1))) * np.eye(D) + r) for D in (30, 31)}
    hits, n_sim = np.zeros(2), 4000
    for _ in range(n_sim):
        s2 = b0 / rng.gamma(a0)
        beta = rng.normal(m0, math.sqrt(s2 / k0))
        x = {k: beta / (D := calendar.monthrange(*k)[1]) + math.sqrt(s2) * L[D] @ rng.standard_normal(D) for k in months}
        seen = {k: (calendar.monthrange(*k)[1], x[k]) for k in months[:2]} | {months[2]: (31, x[months[2]][:10])}
        post = posterior((m0, k0, a0, b0), seen, phi)
        for j, (fut, truth) in enumerate((({months[2]: 7}, x[months[2]][10:17].sum()),
                                          ({months[2]: 21, months[3]: 30}, x[months[2]][10:].sum() + x[months[3]].sum()))):
            lo, hi = predictive(post, seen, phi, fut).interval(0.8)
            hits[j] += lo <= truth <= hi
    se = math.sqrt(0.8 * 0.2 / n_sim)
    assert np.all(np.abs(hits / n_sim - 0.8) < 3 * se), hits / n_sim
    # Shortfall probability is non-decreasing in price.
    for p in sorted(st)[::10]:
        for plan in (False, True):
            q = [shortfall_probability(st[p], x, pay_in_3=plan)["probability"] for x in np.geomspace(1, 30000, 25)]
            assert all(b >= a - 1e-12 for a, b in zip(q, q[1:])), (p, plan, q)
    # No October data in any fit: corrupting every October row leaves every fitted quantity unchanged.
    R, H, _ = fit(st)
    bad = {p: [t | dict(debit=t["debit"] * 3, credit=t["credit"] * 3, balance=t["balance"] - 999)
               if t["date"] > ORIGIN else t for t in tx] for p, tx in st.items()}
    R2, H2, _ = fit(bad)
    assert H == H2
    for p in R:
        for name in MODELS:
            assert R[p][name]["post"] == R2[p][name]["post"]
            assert all(R[p][name]["pred"][d].interval(0.8) == R2[p][name]["pred"][d].interval(0.8) for d in HORIZONS)
        assert R[p]["shortfall"] == R2[p]["shortfall"]
    print(f"self-check passed (simulated 80 % coverage: 7 days {hits[0] / n_sim:.3f}, 51 days {hits[1] / n_sim:.3f}; "
          f"phi = {h['phi']:.4f})")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true", help="run the self-check (writes nothing)")
    check() if ap.parse_args().check else run()
