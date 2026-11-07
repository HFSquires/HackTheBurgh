"""Open Banking-native synthetic data, generation 2 (task T20).

Twelve months (1 November 2025 to 31 October 2026) of UK Open Banking Read/Write API v3.1 account-information objects for
the same 100 personas as mock_statements.py, with a current account (arranged overdraft), an easy-access savings account
and, for about two-thirds of people, a credit card; merchant details with ISO 18245 merchant category codes; pending card
payments on 1 and 2 November 2026; direct-debit mandates, standing orders and scheduled (BNPL) payments. Each person has
persistent spending habits with known ground truth, saved so that task T22 can test whether models recover them.

Sources. Personas, salaries (ASHE, uprated by AWE), net pay (2026/27 tax and NI), tenure (EHS) and spending (Family
Spending, uprated by CPI) come from mock_statements.py, imported and not changed. Seasonality is the ONS retail-sales
profile (J5AH) computed by market_data.seasonality(). The annual motor-insurance direct debit and the package holiday are
the persona's own ONS Family Spending amounts (workbook 3, A35 rows 366 and 298), taken out of the monthly pools so that
totals are unchanged. Savings interest follows Bank Rate (data/boe_bank_rate_*.csv) less a synthetic margin. Every other
number in the SYNTHETIC block below is an assumption, not from a source.

Output: Analysis/open_banking/<persona>.json (one per persona, compact JSON, about 47 MB in all: gitignored except a
four-persona sample; regenerate in a few seconds), csv/<persona>.csv (current account, statement layout),
ground_truth.csv, ground_truth_monthly.csv and summary.md. Analysis/mock_statements/ is not touched.

Run:   .venv\\Scripts\\python -X utf8 ob_generator.py [--n 100]
Check: .venv\\Scripts\\python -X utf8 ob_generator.py --check  (asserts; generates twice and compares bytes)
"""
import bisect
import calendar
import csv
import datetime as dt
import hashlib
import json
import math
import random
import statistics as st
import sys
import tempfile
from pathlib import Path
from zoneinfo import ZoneInfo

import market_data as md
import mock_bank as mb  # BankTransactionCode names and the OB amount shape (imports affordability, standard library only)
import mock_statements as ms
import affordability as af

OUT = ms.ROOT / "Analysis" / "open_banking"
SEED = ms.SEED
LONDON = ZoneInfo("Europe/London")
START, END = dt.date(2025, 11, 1), dt.date(2026, 10, 31)
MONTHS = [(2025, 11), (2025, 12)] + [(2026, m) for m in range(1, 11)]
PENDING_MONTH = (2026, 11)
AS_OF = dt.datetime(2026, 11, 2, 8, 0, tzinfo=LONDON)  # snapshot: Monday 2 November 2026, 08:00; nothing booked after 31 October
CATS = list(ms.MERCH)  # discretionary card categories (ONS 1, 2, 3, 5, 6, 7, 9, 11, 12)
WK = ms.WK

# ---------------------------------------------------------------- SYNTHETIC assumptions (no source; change here only)
HABIT_SD = 0.25                 # sd of ln(category multiplier); mean-one lognormal, one draw per person and category
AR_SD = 0.10                    # stationary sd of ln(monthly discretionary factor), shared by all categories in a month
AR_RHO = (0.3, 0.7)             # per-person AR(1) coefficient, uniform (mean 0.5)
NOISE = (0.9, 1.1)              # per-category, per-month factor, uniform (as mock_statements.py)
PAYDAY_SHARE = (0.0, 0.3)       # per-person share of discretionary card payments made on payday and the next two days
PAYDAY_DAYS = 3                 # payday and the two days after, within the calendar month
TREND_P, TREND_G = 0.4, 0.08    # 40% of people drift: ln-change per year uniform on (-0.08, 0.08); the rest 0
LUMPY_RATE = 1.0                # synthetic one-off purchases per person-year, Poisson
LUMPY = [("CURRYS", 5732, 9, 250, 1000), ("KWIK FIT", 7538, 7, 150, 800), ("DFS", 5712, 5, 400, 1500)]
#        (merchant, MCC, ONS category whose income-decile ratio scales the amount, low GBP, high GBP; uniform)
BANDS = [(1500, 250, 1000), (2500, 500, 2500), (3500, 1000, 4000), (math.inf, 1500, 6000)]
#        (net monthly pay below GBP, arranged overdraft limit GBP, credit-card limit GBP)
OD_EAR = 0.399                  # overdraft interest, arranged and unarranged alike, EAR; accrued daily, posted monthly
CARD_P, CARD_FULL_P = 2 / 3, 0.6  # share holding a credit card; share of holders who pay in full (others pay the minimum)
CARD_SHARE = (0.3, 0.8)         # holders: share of discretionary card payments made on the credit card, uniform
CARD_OPEN = (0.2, 0.6)          # minimum payers: opening card balance as a share of the limit, uniform; full payers 0
CARD_APR = 0.249                # purchase rate; monthly interest = APR / 12 on the balance carried past the due date
CARD_BUFFER = 0.05              # purchases accepted only up to (1 - buffer) x limit, so interest cannot breach the limit
MIN_PAY = (2500, 0.01)          # minimum payment: max(25 GBP, 1% of the statement balance + that statement's interest)
DUE_DAYS = 25                   # card payment by direct debit this many days after the statement date (day 1 to 28)
SAVE_OPEN = (0.0, 3.0)          # savings opening balance in months of net pay, uniform
SAVE_P, SAVE_SHARE = 0.6, 0.5   # share with a monthly standing order to savings; its size as a share of expected surplus
SAVE_FINAL_P = 1 / 3            # share of those standing orders with a final payment date (a fixed-term savings goal)
# Behaviour: card purchases (everyday and one-off) are foregone while the current account is overdrawn; at the end of
# each day an overdrawn current account is topped up from savings as far as they go. Committed payments (direct debits,
# rent, BNPL instalments, card repayments) are always paid, into unarranged overdraft if need be (flagged per person).
SAVE_MARGIN = 0.75              # savings AER = Bank Rate - 0.75 percentage points, floored at 0
PENDING = (2, 5)                # pending card payments on 1 and 2 November 2026, uniform count

# ISO 18245 merchant category codes (the four-digit codes Visa and Mastercard use); descriptions as in the card schemes'
# public MCC lists, not checked against the ISO text itself. Every MerchantCategoryCode written is from this table.
MCC = {4111: "Local and suburban commuter passenger transportation", 4112: "Passenger railways", 4131: "Bus lines",
       4722: "Travel agencies and tour operators", 5200: "Home supply warehouse stores",
       5331: "Variety stores", 5399: "Miscellaneous general merchandise", 5411: "Grocery stores, supermarkets",
       5541: "Service stations", 5651: "Family clothing stores", 5712: "Furniture, home furnishings and equipment stores",
       5732: "Electronics stores", 5812: "Eating places, restaurants", 5813: "Drinking places (bars, taverns)",
       5814: "Fast food restaurants", 5816: "Digital goods: games", 5912: "Drug stores and pharmacies",
       5921: "Package stores: beer, wine and liquor", 5941: "Sporting goods stores", 5942: "Book stores",
       5995: "Pet shops, pet food and supplies", 5999: "Miscellaneous and specialty retail stores",
       7230: "Barber and beauty shops", 7523: "Parking lots and garages", 7538: "Automotive service shops (non-dealer)",
       7832: "Motion picture theatres", 7941: "Commercial sports, professional sports clubs", 9402: "Postal services"}
MERCHANT_MCC = {"TESCO STORES": 5411, "SAINSBURYS S/MKTS": 5411, "ASDA SUPERSTORE": 5411, "ALDI STORES": 5411,
                "CO-OP FOOD": 5411, "MORRISONS": 5411, "CENTRAL OFF LICENCE": 5921, "PRIMARK": 5651,
                "NEXT RETAIL": 5651, "H&M": 5651, "SPORTS DIRECT": 5941, "B&Q": 5200, "IKEA": 5712, "ARGOS": 5399,
                "HOME BARGAINS": 5331, "BOOTS": 5912, "WELL PHARMACY": 5912, "BP": 5541, "SHELL": 5541, "ESSO": 5541,
                "RINGGO PARKING": 7523, "NATIONAL EXPRESS": 4131, "AMAZON": 5999, "STEAM GAMES": 5816,
                "CINEWORLD": 7832, "WATERSTONES": 5942, "PETS AT HOME": 5995, "COSTA COFFEE": 5814, "GREGGS": 5814,
                "PIZZA EXPRESS": 5812, "DELIVEROO": 5814, "NANDOS": 5812, "WETHERSPOON": 5813, "SUPERDRUG": 5912,
                "BARBERS": 7230, "ROYAL MAIL": 9402, "CURRYS": 5732, "JET2HOLIDAYS": 4722, "KWIK FIT": 7538,
                "DFS": 5712, "CLEARPAY*NEXT RETAIL": 5651, "KLARNA*CURRYS": 5732, "KLARNA*ARGOS": 5399,
                "PAYPAL*PAYIN3 ASOS": 5651, "CLEARPAY*JD SPORTS": 5941, "KLARNA*BOOTS": 5912,
                **{r: 4111 if r == "TFL TRAVEL CHARGE" else 4112 for r in ms.RAIL.values()}}
TICKET_MCC = 7941
assert set(MERCHANT_MCC.values()) | {TICKET_MCC} <= set(MCC)
# ONS Family Spending detail rows (workbook 3, A35) carved out of the monthly pools into annual or one-off payments.
CARVE = {"holiday": (298, "9.6 Package holidays", 9), "motor": (366, "12.4.3 Vehicle insurance", 12)}

# Proprietary codes: the statement types of mock_statements.py, plus CHG (overdraft interest), TFR (transfer between own
# accounts), INT (interest), PUR (card purchase), PAY (card payment received). ponytail: Lloyds-style codes are an
# unchecked belief, as in mock_statements.py; BankTransactionCode is given only for the four codes mock_bank.ISO maps.


def pence(x):
    return int(round(x * 100))


def hexid(*parts):
    return hashlib.sha256("-".join(map(str, parts)).encode()).hexdigest()[:8]


def at(d, h, m=0, s=0):
    return dt.datetime(d.year, d.month, d.day, h, m, s, tzinfo=LONDON)


def iso(t):
    return t.isoformat()


def amt(p):
    return mb.amount(p / 100)


def band(net):
    return next((od, cc) for hi, od, cc in BANDS if net < hi)


def season():
    """Month (1 to 12) -> ONS retail-sales seasonal factor, mean 1: the mean over 2021 to 2025 of each month's value with
    each year scaled to mean 100 (market_data.seasonality, from data/ons_drsi_retail_sales_value_nsa_J5AH.csv) / 100."""
    rel = md.seasonality()[0]
    out = {m: st.mean(rel[y][m - 1] for y in md.YEARS) / 100 for m in range(1, 13)}
    assert abs(st.mean(out.values()) - 1) < 1e-9 and out[12] > out[11] > 1.1
    return out


def poisson(rng, lam):
    k, p, lim = 0, rng.random(), math.exp(-lam)
    while p > lim:
        k, p = k + 1, p * rng.random()
    return k


def ons_scale(key, dec, ons, c):
    """Household-type ratio (A23) x income-decile ratio (A4) of category c, exactly as mock_statements.spend_model's f(c)."""
    col = ms.A23_COLS[key][0]
    h, allh = ms.num(ons["a23"][ms.CAT_A23[c] - 1][col]), ms.num(ons["a4"][ms.CAT_A4[c] - 1][ms.A4_ALL])
    return (h / allh if h is not None and allh else 1.0) * ms.decile_ratio(dec, ons)[c]


def carved(key, region, dec, ons, row, c):
    """Weekly GBP of ONS A35 detail row `row` for this persona: regional value x household and decile ratios x their
    share of the household x CPI factor of category c, the same scaling as the pool it is taken from."""
    v = ms.num(ons["a35"][row - 1][ms.REGION_COL[region][0]]) or 0.0
    return v * ons_scale(key, dec, ons, c) / ms.A23_COLS[key][2] * ons["cpi"][c]


class Rates:
    """Bank Rate in force on a date (data/boe_bank_rate_*.csv via affordability.bank_rate)."""
    def __init__(self):
        rows = af.bank_rate()
        self.d, self.v = [r[0] for r in rows], [r[1] for r in rows]

    def on(self, d):
        return self.v[max(0, bisect.bisect_right(self.d, d) - 1)]

    def aer(self, d):
        return max(0.0, self.on(d) - SAVE_MARGIN)


# ---------------------------------------------------------------- one persona
def habits(idx, net, od, cl):
    """Every person-level trait, drawn in a fixed order from the person's own stream (ground truth)."""
    r = random.Random(f"{SEED}-ob-habit-{idx}")
    h = dict(mult={c: r.lognormvariate(-HABIT_SD ** 2 / 2, HABIT_SD) for c in CATS}, rho=r.uniform(*AR_RHO),
             payday_share=r.uniform(*PAYDAY_SHARE))
    h["trend"] = r.uniform(-TREND_G, TREND_G) if r.random() < TREND_P else 0.0
    e = [r.gauss(0, AR_SD)]
    for _ in range(len(MONTHS)):  # 12 history months and the pending month
        e.append(h["rho"] * e[-1] + math.sqrt(1 - h["rho"] ** 2) * r.gauss(0, AR_SD))
    h["ar"] = [math.exp(x - AR_SD ** 2 / 2) for x in e]
    h["card"] = r.random() < CARD_P
    h["card_full"] = r.random() < CARD_FULL_P
    h["card_share"] = r.uniform(*CARD_SHARE)
    h["stmt_day"] = r.randint(1, 28)
    h["card_open"] = 0 if h["card_full"] else pence(r.uniform(*CARD_OPEN) * cl)
    h["save_open"] = pence(r.uniform(*SAVE_OPEN) * net)
    h["saver"] = r.random() < SAVE_P
    h["save_final"] = r.random() < SAVE_FINAL_P
    h["holiday"] = (r.choice(MONTHS), r.randint(1, 28))
    h["motor"] = (r.choice(MONTHS), r.randint(1, 28))
    h["lumpy"] = [(r.choice(LUMPY), dt.date(*r.choice(MONTHS), r.randint(1, 28)), r.random()) for _ in range(poisson(r, LUMPY_RATE))]
    h["bnpl"] = []
    if idx % 3 == 0:  # the same third as mock_statements.bnpl_plans; three plans with distinct providers, the last still running
        opts = r.sample(ms.BNPL_OPTIONS, 3)
        firsts = sorted([START + dt.timedelta(days=r.randint(0, 150)), dt.date(2026, 4, 1) + dt.timedelta(days=r.randint(0, 120))])
        firsts.append(dt.date(2026, 10, 1) + dt.timedelta(days=r.randint(0, 24)))
        h["bnpl"] = [(*o[:2], f, *o[2:]) for o, f in zip(opts, firsts)]
    h["rent_first"] = dt.date(r.randint(2019, 2025), r.randint(1, 10), 1)
    if not h["card"]:
        h["card_full"] = h["card_share"] = h["stmt_day"] = None
        h["card_open"] = 0
    return h


class Book:
    """Booked and pending transactions of one account, with running balance in pence (positive = in credit)."""
    def __init__(self, acc, opening, limit=None):
        self.acc, self.bal, self.opening, self.limit, self.tx, self.pending = acc, opening, opening, limit, [], []
        self.minbal = opening

    def post(self, t, p, desc, code, cls, **kw):
        self.bal += p
        self.minbal = min(self.minbal, self.bal)
        self.tx.append(dict(t=t, p=p, desc=desc, code=code, cls=cls, bal=self.bal, **kw))


def build(idx, key, p, tenure, ons, rates, seas):
    region, pid = p["region"], f"persona{idx + 1:03d}"
    ashe_gross = ms.num(ons["ashe"][p["occupation"][:3]][1][3])
    gross = ashe_gross * ons["awe"]
    net = ms.net_monthly(gross, region)
    dec = ms.decile(ashe_gross, ons)
    pool, reg = ms.spend_model(key, tenure, region, ons, dec)
    annual = {}
    for k, (row, lab, c) in CARVE.items():
        assert lab.split()[0] in ms.label(ons["a35"][row - 1]), (k, ms.label(ons["a35"][row - 1]))
        w = carved(key, region, dec, ons, row, c)
        assert 0 <= w <= pool[c], (pid, k, w, pool[c])
        pool[c] -= w
        annual[k] = pence(w * 52)
    od_gbp, cl_gbp = band(net)
    h = habits(idx, net, od_gbp, cl_gbp)
    od, cl = pence(od_gbp), pence(cl_gbp)
    rng = random.Random(f"{SEED}-ob-tx-{idx}")
    uid = p["uuid"][:8]
    ids = dict(ca=uid, sv=hexid(p["uuid"], "savings"), cc=hexid(p["uuid"], "card"))
    town = p["municipality"].upper().replace("CITY OF ", "")[:14]
    merch = {c: ([m.replace("@RAIL@", ms.RAIL[region]) for m in ms_], n) for c, (ms_, n) in ms.MERCH.items()}
    skind, sname = ms.sports_item(p)
    dr = ms.decile_ratio(dec, ons)

    # expected discretionary spending (ground truth) and committed amounts
    trend = [math.exp(h["trend"] * (t - 5.5) / 12) for t in range(len(MONTHS) + 1)]
    allm = MONTHS + [PENDING_MONTH]
    E = {(t, c): pool[c] * WK * h["mult"][c] * seas[allm[t][1]] * trend[t] for t in range(len(allm)) for c in CATS}
    fixed = {k: pence(v * WK) for k, v in reg.items()}
    exp_month = sum(pool[c] * WK * h["mult"][c] for c in CATS) + sum(fixed.values()) / 100 + sum(annual.values()) / 1200
    save_so = (math.floor(SAVE_SHARE * (net - exp_month) / 10) * 10) if h["saver"] else 0
    save_so = pence(save_so) if save_so >= 25 else 0

    ca, sv = Book(ids["ca"], pence(net), od), Book(ids["sv"], h["save_open"])  # current account opens with one month's net pay
    cc = Book(ids["cc"], -h["card_open"], cl) if h["card"] else None
    ev = {}  # date -> [(time, seq, event)]
    seq = [0]

    def plan(t, **e):
        if e["p"] <= 0:  # a zero amount (a tiny budget split into pence) is not a transaction
            return
        seq[0] += 1
        ev.setdefault(t.date(), []).append((t, seq[0], e))

    def card_time(d):
        return at(d, 7) + dt.timedelta(seconds=rng.randrange(15 * 3600))

    budget, bnpl_due, mono = {}, [], {}
    for t, (y, m) in enumerate(MONTHS):
        dim = calendar.monthrange(y, m)[1]
        D = lambda day: dt.date(y, m, min(day, dim))
        pday = ms.payday(y, m)
        window = [pday + dt.timedelta(days=k) for k in range(PAYDAY_DAYS) if (pday + dt.timedelta(days=k)).month == m]
        plan(at(pday, 1), kind="credit", acct="ca", p=pence(net), desc="FAKE EMPLOYER LTD SALARY", code="BGC", cls="salary")
        if "rent" in reg:
            plan(at(D(1), 2), kind="debit", acct="ca", p=fixed["rent"], code="SO", cls="committed",
                 desc="RENT " + ("COUNCIL HOUSING" if tenure == "Social rented" else "LETTING AGENT"))
        if save_so:
            plan(at(D(1), 2, 30), kind="save", p=save_so)
        for day, k, desc in ((5, "energy", "ENERGY SUPPLIER AND WATER"),
                             (15, "council_tax", p["municipality"].upper() + " COUNCIL TAX"),
                             (12, "phone", "MOBILE AND BROADBAND"), (20, "tv", "STREAMING AND TV SUBSCRIPTION")):
            plan(at(D(day), 3), kind="debit", acct="ca", p=fixed[k], desc=desc, code="DD", cls="committed")
        if skind == "gym":
            plan(at(D(3), 3), kind="debit", acct="ca", p=fixed["sports"], desc=sname, code="DD", cls="committed")
        else:
            for a, day in zip(ms.pence_split(fixed["sports"] / 100, [1.0, 1.0]), (8, 22)):
                plan(at(D(day), 18), kind="debit", acct="ca", p=pence(a), desc=f"{sname} {town} GB", code="DEB",
                     cls="committed", merchant=sname, mcc=TICKET_MCC)
        if (y, m) == h["motor"][0]:
            plan(at(D(h["motor"][1]), 3), kind="debit", acct="ca", p=annual["motor"], desc="MOTOR INSURANCE ANNUAL",
                 code="DD", cls="annual")
        if (y, m) == h["holiday"][0] and annual["holiday"] > 0:
            plan(card_time(D(h["holiday"][1])), kind="card", pref="cc", p=annual["holiday"], cls="lumpy", cat=9,
                 merchant="JET2HOLIDAYS", desc=f"JET2HOLIDAYS {town} GB")
        bnpl = {}
        for name, c, first, step, n, frac in h["bnpl"]:
            inst = pence(pool[c] * WK * frac)
            for k in range(n):
                d = first + dt.timedelta(days=step * k)
                if (d.year, d.month) == (y, m):
                    if d <= END:
                        plan(at(d, 9), kind="debit", acct="ca", p=inst, desc=f"{name} {town} GB", code="DEB", cls="bnpl",
                             cat=c, merchant=name, mcc=MERCHANT_MCC[name])
                    bnpl[c] = bnpl.get(c, 0) + inst
        for name, c, first, step, n, frac in h["bnpl"]:
            for k in range(n):
                d = first + dt.timedelta(days=step * k)
                if d > END and t == len(MONTHS) - 1:
                    bnpl_due.append((d, name, pence(pool[c] * WK * frac), k + 1, n))
        for c, (merchants, n) in merch.items():
            budget[t, c] = E[t, c] * h["ar"][t] * rng.uniform(*NOISE)
            total = max(0.0, budget[t, c] - bnpl.get(c, 0) / 100)
            for a in ms.pence_split(total, [rng.lognormvariate(0, 0.6) for _ in range(n)]):
                d = rng.choice(window) if rng.random() < h["payday_share"] else D(rng.randint(1, dim))
                mname = rng.choice(merchants)
                pref = "cc" if cc and rng.random() < h["card_share"] else "ca"
                plan(card_time(d), kind="card", pref=pref, p=pence(a), cls="disc", cat=c, merchant=mname,
                     desc=f"{mname} {town} GB")
    for (merchant, mcc, c, lo, hi), d, u in h["lumpy"]:
        plan(card_time(d), kind="card", pref="cc", p=pence((lo + (hi - lo) * u) * dr[c]), cls="lumpy", cat=c,
             merchant=merchant, desc=f"{merchant} {town} GB")

    # card statements: the opening balance is the statement of the month before the history starts
    if cc:
        prev = dt.date(2025, 10, h["stmt_day"])
        state = dict(stmt=h["card_open"], paid=0)
        due = prev + dt.timedelta(days=DUE_DAYS)
        if h["card_open"] and due >= START:
            plan(at(due, 3), kind="cardpay", p=min_pay(h["card_open"], 0))

    declined, unarranged, od_days = [], set(), 0
    od_acc = sv_acc = 0.0
    day = START
    while day <= END:
        for t, _, e in sorted(ev.get(day, []), key=lambda x: (x[0], x[1])):
            if e["kind"] == "credit":
                ca.post(t, e["p"], e["desc"], e["code"], e["cls"])
            elif e["kind"] == "debit":
                ca.post(t, -e["p"], e["desc"], e["code"], e["cls"], **{k: e[k] for k in ("cat", "merchant", "mcc") if k in e})
                if ca.bal < -od:
                    unarranged.add(day)
            elif e["kind"] == "save":
                if ca.bal - e["p"] >= -od:  # a standing order the account cannot cover within its limit is returned unpaid
                    ca.post(t, -e["p"], f"MOCKBANK SAVINGS {ids['sv'].upper()}", "SO", "transfer")
                    sv.post(t, e["p"], f"FROM CURRENT ACCOUNT {ids['ca'].upper()}", "TFR", "transfer")
                else:
                    declined.append((t, "save", e["p"], None, "returned"))
            elif e["kind"] == "cardpay":
                pay = e["p"]
                if pay > 0:
                    ca.post(t, -pay, "MOCKBANK CREDIT CARD", "DD", "committed")
                    cc.post(t, pay, "PAYMENT RECEIVED - THANK YOU", "PAY", "transfer")
                    state["paid"] += pay
                    if ca.bal < -od:
                        unarranged.add(day)
            elif ca.bal < 0:  # card purchase while the current account is overdrawn: foregone (cut back)
                declined.append((t, e["cls"], e["p"], e["cat"], "foregone"))
            else:  # card purchase: preferred account, else the other, else declined
                route = ["cc", "ca"] if e["pref"] == "cc" else ["ca", "cc"]
                done = False
                for a in route:
                    if a == "cc" and cc and -cc.bal + e["p"] <= cl * (1 - CARD_BUFFER):
                        cc.post(t, -e["p"], e["desc"], "PUR", e["cls"], cat=e["cat"], merchant=e["merchant"],
                                mcc=MERCHANT_MCC[e["merchant"]])
                        done = True
                    elif a == "ca" and ca.bal - e["p"] >= -od:
                        ca.post(t, -e["p"], e["desc"], "DEB", e["cls"], cat=e["cat"], merchant=e["merchant"],
                                mcc=MERCHANT_MCC[e["merchant"]])
                        done = True
                    if done:
                        break
                if not done:
                    declined.append((t, e["cls"], e["p"], e["cat"], "declined"))
        # end of day: card statement, interest accrual, month-end postings
        if cc and day.day == h["stmt_day"]:
            carried = max(0, state["stmt"] - state["paid"])
            interest = round(carried * CARD_APR / 12)
            if interest:
                cc.post(at(day, 23, 59), -interest, "PURCHASE INTEREST", "INT", "interest")
            owed = -cc.bal
            state.update(stmt=owed, paid=0)
            due = day + dt.timedelta(days=DUE_DAYS)
            if owed > 0 and due <= END:
                plan(at(due, 3), kind="cardpay", p=owed if h["card_full"] else min_pay(owed, interest))
        if ca.bal < 0 < sv.bal:  # an overdrawn current account is topped up from savings, as far as they go
            move = min(sv.bal, -ca.bal)
            sv.post(at(day, 23, 59, 10), -move, f"TO CURRENT ACCOUNT {ids['ca'].upper()}", "TFR", "transfer")
            ca.post(at(day, 23, 59, 10), move, f"FROM SAVINGS {ids['sv'].upper()}", "TFR", "transfer")
        if ca.bal < 0:  # end-of-day balance after any top-up from savings
            od_days += 1
            od_acc += -ca.bal * ((1 + OD_EAR) ** (1 / 365) - 1)
        sv_acc += max(0, sv.bal) * rates.aer(day) / 100 / 365
        if (day + dt.timedelta(days=1)).day == 1:
            if round(od_acc):
                ca.post(at(day, 23, 59, 30), -round(od_acc), "OVERDRAFT INTEREST", "CHG", "interest")
                if ca.bal < -od:
                    unarranged.add(day)
            if round(sv_acc):
                sv.post(at(day, 23, 59, 30), round(sv_acc), "INTEREST", "INT", "interest")
            od_acc = sv_acc = 0.0
        day += dt.timedelta(days=1)

    # pending card payments, 1 November (any time) and 2 November (before 08:00), from the November 2026 budget
    t12 = len(MONTHS)
    avail = dict(ca=ca.bal, cc=cc.bal if cc else 0)
    for k in range(rng.randint(*PENDING)):
        c = rng.choices(CATS, weights=[E[t12, c] for c in CATS])[0]
        merchants, n = merch[c]
        mname = rng.choice(merchants)
        a = pence(E[t12, c] * h["ar"][t12] / n * rng.lognormvariate(-0.18, 0.6))
        t = (at(dt.date(2026, 11, 1), 7) + dt.timedelta(seconds=rng.randrange(15 * 3600)) if rng.random() < 0.7
             else at(dt.date(2026, 11, 2), 6) + dt.timedelta(seconds=rng.randrange(7200)))
        pref = "cc" if cc and rng.random() < h["card_share"] else "ca"
        for acct in ([pref, "ca" if pref == "cc" else "cc"] if avail["ca"] >= 0 else []):
            if acct == "cc" and cc and -avail["cc"] + a <= cl * (1 - CARD_BUFFER) or acct == "ca" and avail["ca"] - a >= -od:
                avail[acct] -= a
                (cc if acct == "cc" else ca).pending.append(dict(t=t, p=-a, desc=f"{mname} {town} GB",
                                                                 code="DEB" if acct == "ca" else "PUR", cls="pending",
                                                                 cat=c, merchant=mname, mcc=MERCHANT_MCC[mname]))
                break

    return dict(pid=pid, uid=uid, p=p, key=key, tenure=tenure, net=net, gross=gross, dec=dec, h=h, ids=ids, ca=ca, sv=sv,
                cc=cc, od=od, cl=cl, E=E, budget=budget, declined=declined, unarranged=sorted(unarranged),
                od_days=od_days, fixed=fixed, annual=annual, save_so=save_so, bnpl_due=sorted(bnpl_due),
                rates=rates, pool=pool)


def min_pay(owed, interest):
    return min(owed, max(MIN_PAY[0], round(MIN_PAY[1] * owed) + interest))


# ---------------------------------------------------------------- Open Banking v3.1 objects
def ob_tx(acc, i, x, pending=False, card=None):
    debit = x["p"] < 0
    out = {"AccountId": acc, "TransactionId": f"{acc}-{'P' if pending else ''}{i:05d}",
           "TransactionReference": f"MB{x['t']:%y%m%d}{hexid(acc, i, pending).upper()}",
           "CreditDebitIndicator": "Debit" if debit else "Credit", "Status": "Pending" if pending else "Booked",
           "BookingDateTime": iso(x["t"]), "ValueDateTime": iso(x["t"]), "TransactionInformation": x["desc"],
           "Amount": amt(x["p"])}
    if x["code"] in mb.ISO:
        out["BankTransactionCode"] = dict(zip(("Code", "SubCode"), mb.ISO[x["code"]]))
    out["ProprietaryBankTransactionCode"] = {"Code": x["code"], "Issuer": "MockBank"}
    if not pending:
        out["Balance"] = {"Amount": amt(x["bal"]), "CreditDebitIndicator": "Credit" if x["bal"] >= 0 else "Debit",
                          "Type": "InterimBooked"}
    if "mcc" in x:
        out["MerchantDetails"] = {"MerchantName": x["merchant"], "MerchantCategoryCode": str(x["mcc"])}
        if card:
            out["CardInstrument"] = card
    return out


def balances(book, line):
    b = book.bal
    rows = [("OpeningBooked", at(START, 0), book.opening), ("InterimBooked", AS_OF, b),
            ("InterimAvailable", AS_OF, b + sum(x["p"] for x in book.pending))]
    out = []
    for typ, t, v in rows:
        o = {"AccountId": book.acc, "Amount": amt(v), "CreditDebitIndicator": "Credit" if v >= 0 else "Debit",
             "Type": typ, "DateTime": iso(t)}
        if line:
            o["CreditLine"] = [{"Included": False, "Type": line, "Amount": amt(book.limit)}]
        out.append(o)
    return out


def ob_document(r):
    ids, h, idx = r["ids"], r["h"], int(r["pid"][7:])
    acct_no = f"{idx:08d}"
    accounts = [{"AccountId": ids["ca"], "Status": "Enabled", "Currency": "GBP", "AccountType": "Personal",
                 "AccountSubType": "CurrentAccount", "Nickname": "Mock current account",
                 "Account": [{"SchemeName": "UK.OBIE.SortCodeAccountNumber", "Identification": "000000" + acct_no,
                              "Name": r["pid"]}]},
                {"AccountId": ids["sv"], "Status": "Enabled", "Currency": "GBP", "AccountType": "Personal",
                 "AccountSubType": "Savings", "Nickname": "Mock easy-access savings",
                 "Account": [{"SchemeName": "UK.OBIE.SortCodeAccountNumber", "Identification": f"000000{50000000 + idx:08d}",
                              "Name": r["pid"]}]}]
    rate_now = r["rates"].aer(AS_OF.date())
    products = [{"AccountId": ids["ca"], "ProductId": "MOCK-PCA", "ProductName": "Mock Current Account",
                 "ProductType": "PersonalCurrentAccount",
                 "SupplementaryData": {"ArrangedOverdraftLimit": amt(r["od"]), "OverdraftEAR": f"{OD_EAR * 100:.2f}",
                                       "Note": "Synthetic: overdraft limit by income band and rate are assumptions"}},
                {"AccountId": ids["sv"], "ProductId": "MOCK-EAS", "ProductName": "Mock Easy Access Saver",
                 "ProductType": "Other", "OtherProductType": {"Name": "EasyAccessSavings", "Description": "Variable rate"},
                 "SupplementaryData": {"InterestRateAER": f"{rate_now:.2f}",
                                       "Note": f"Synthetic: Bank Rate minus {SAVE_MARGIN} percentage points, floored at 0"}}]
    debit_card = {"CardSchemeName": "VISA", "Identification": f"************{idx:04d}"}
    credit_card = {"CardSchemeName": "MASTERCARD", "Identification": f"************{9000 + idx:04d}"}
    books = [(r["ca"], debit_card), (r["sv"], None)]
    bal = balances(r["ca"], "Arranged") + balances(r["sv"], None)
    if r["cc"]:
        accounts.append({"AccountId": ids["cc"], "Status": "Enabled", "Currency": "GBP", "AccountType": "Personal",
                         "AccountSubType": "CreditCard", "Nickname": "Mock credit card",
                         "Account": [{"SchemeName": "UK.OBIE.PAN", "Identification": credit_card["Identification"],
                                      "Name": r["pid"]}]})
        products.append({"AccountId": ids["cc"], "ProductId": "MOCK-CC", "ProductName": "Mock Credit Card",
                         "ProductType": "Other", "OtherProductType": {"Name": "CreditCard", "Description": "Purchase rate"},
                         "SupplementaryData": {"PurchaseAPR": f"{CARD_APR * 100:.2f}", "CreditLimit": amt(r["cl"]),
                                               "StatementDay": h["stmt_day"], "PaymentDueDaysAfterStatement": DUE_DAYS,
                                               "Note": "Synthetic: limit by income band and rate are assumptions"}})
        books.append((r["cc"], credit_card))
        bal += balances(r["cc"], "Credit")
    tx = []
    for book, card in books:
        tx += [ob_tx(book.acc, i, x, card=card) for i, x in enumerate(book.tx, 1)]
        tx += [ob_tx(book.acc, i, x, pending=True, card=card) for i, x in enumerate(book.pending, 1)]

    ca_tx = r["ca"].tx
    dds, sos = [], []
    groups = {}
    for x in ca_tx:
        if x["code"] in ("DD", "SO"):
            groups.setdefault((x["code"], x["desc"]), []).append(x)
    count = {"DD": 0, "SO": 0}
    for (code, desc), g in groups.items():
        count[code] += 1
        last, ident = g[-1], f"{ids['ca']}-{code}{count[code]:02d}"
        if code == "DD":
            freq = ("IntrvlMnthDay:12:" if g[0]["cls"] == "annual" else "IntrvlMnthDay:01:") + f"{last['t'].day:02d}"
            dd = {"AccountId": ids["ca"], "DirectDebitId": ident, "MandateIdentification": f"MOCK{ident.upper()}",
                  "DirectDebitStatusCode": "Active", "Name": desc, "PreviousPaymentDateTime": iso(last["t"]),
                  "PreviousPaymentAmount": amt(-last["p"])}
            if desc != "MOCKBANK CREDIT CARD":  # the card payment's day and amount vary with each statement
                dd["Frequency"] = freq
            dds.append(dd)
            continue
        so = {"AccountId": ids["ca"], "StandingOrderId": ident, "Frequency": f"IntrvlMnthDay:01:{last['t'].day:02d}",
              "Reference": desc, "StandingOrderStatusCode": "Active",
              "LastPaymentDateTime": iso(last["t"]), "LastPaymentAmount": amt(-last["p"]),
              "NextPaymentDateTime": iso(at(dt.date(2026, 11, last["t"].day), last["t"].hour, last["t"].minute)),
              "NextPaymentAmount": amt(-last["p"])}
        if desc.startswith("RENT"):
            so = {**so, "FirstPaymentDateTime": iso(at(h["rent_first"], 2)), "FirstPaymentAmount": amt(-last["p"]),
                  "CreditorAccount": {"SchemeName": "UK.OBIE.SortCodeAccountNumber",
                                      "Identification": f"999999{hexid(r['uid'], 'landlord')[:8].translate(str.maketrans('abcdef', '123456'))}",
                                      "Name": desc[5:]}}
        else:
            so = {**so, "FirstPaymentDateTime": iso(g[0]["t"]), "FirstPaymentAmount": amt(-g[0]["p"]),
                  "CreditorAccount": {"SchemeName": "UK.OBIE.SortCodeAccountNumber",
                                      "Identification": accounts[1]["Account"][0]["Identification"], "Name": r["pid"]}}
            if h["save_final"]:
                so["FinalPaymentDateTime"] = iso(at(dt.date(2027, 4, 1), 2, 30))
        sos.append(so)
    sched = [{"AccountId": ids["ca"], "ScheduledPaymentId": f"{ids['ca']}-SP{k:02d}",
              "ScheduledPaymentDateTime": iso(at(d, 9)), "ScheduledType": "Execution", "Reference": name,
              "InstructedAmount": amt(a),
              "SupplementaryData": {"Instalment": f"{i} of {n}",
                                    "Note": "BNPL instalment schedule as a BNPL provider would hold it; mock only"}}
             for k, (d, name, a, i, n) in enumerate(r["bnpl_due"], 1)]
    meta = {"Persona": r["pid"], "Uuid8": r["uid"], "FirstAvailableDateTime": iso(at(START, 0)),
            "LastAvailableDateTime": iso(AS_OF), "Generator": "ob_generator.py (task T20)", "Seed": SEED,
            "Synthetic": "Not real bank data. Amounts from ONS figures and stated synthetic assumptions."}
    return {"Data": {"Account": accounts, "Balance": bal, "Product": products, "DirectDebit": dds,
                     "StandingOrder": sos, "ScheduledPayment": sched, "Transaction": tx}, "Meta": meta}


def csv_rows(r):
    acct = f"{int(r['pid'][7:]):08d}"
    return [[x["t"].strftime(ms.DATE_FMT), x["code"], ms.SORT_CODE, acct, x["desc"],
             f"{-x['p'] / 100:.2f}" if x["p"] < 0 else "", f"{x['p'] / 100:.2f}" if x["p"] > 0 else "",
             f"{x['bal'] / 100:.2f}"] for x in r["ca"].tx]


# ---------------------------------------------------------------- ground truth and outputs
def observed(r):
    """{(month index, category): booked GBP} of discretionary card payments and BNPL instalments, all accounts."""
    out = {k: 0.0 for k in r["budget"]}
    for b in (r["ca"], r["cc"]) if r["cc"] else (r["ca"],):
        for x in b.tx:
            if x["cls"] in ("disc", "bnpl"):
                out[MONTHS.index((x["t"].year, x["t"].month)), x["cat"]] += -x["p"] / 100
    return out


def truth_rows(r):
    h = r["h"]
    row = {"persona": r["pid"], "uuid8": r["uid"], "region": r["p"]["region"], "household": r["key"], "tenure": r["tenure"],
           "net_monthly": f"{r['net']:.2f}", "income_decile": r["dec"],
           **{f"mult_cat{c}": f"{h['mult'][c]:.6f}" for c in CATS},
           **{f"ons_monthly_cat{c}": f"{r['pool'][c] * WK:.2f}" for c in CATS}, "ar_rho": f"{h['rho']:.6f}", "ar_sd": AR_SD,
           "payday_share": f"{h['payday_share']:.6f}", "trend_per_year": f"{h['trend']:.6f}",
           "overdraft_limit": f"{r['od'] / 100:.2f}", "has_credit_card": int(bool(r["cc"])),
           "card_limit": f"{r['cl'] / 100:.2f}" if r["cc"] else "", "card_paid_in_full": "" if not r["cc"] else int(h["card_full"]),
           "card_share": f"{h['card_share']:.6f}" if r["cc"] else "", "card_opening_balance": f"{h['card_open'] / 100:.2f}",
           "savings_opening": f"{h['save_open'] / 100:.2f}", "savings_standing_order": f"{r['save_so'] / 100:.2f}",
           "holiday_month": "%d-%02d" % h["holiday"][0], "holiday_amount": f"{r['annual']['holiday'] / 100:.2f}",
           "motor_insurance_month": "%d-%02d" % h["motor"][0], "motor_insurance_amount": f"{r['annual']['motor'] / 100:.2f}",
           "lumpy_purchases": ";".join(f"{d.isoformat()} {m[0]}" for m, d, _ in sorted(h["lumpy"], key=lambda x: x[1])),
           "bnpl_plans": ";".join(f"{f.isoformat()} {nm}" for nm, _, f, *_ in h["bnpl"]),
           **{f"{k}_{w}": (sum(d[4] == k for d in r["declined"]) if w == "count" else
                           f"{sum(d[2] for d in r['declined'] if d[4] == k) / 100:.2f}")
              for k in ("foregone", "declined", "returned") for w in ("count", "amount")},
           "below_zero_at_any_time": int(r["ca"].minbal < 0),
           "overdrawn_days": r["od_days"], "unarranged_overdraft_days": len(r["unarranged"]),
           "current_end_balance": f"{r['ca'].bal / 100:.2f}", "savings_end_balance": f"{r['sv'].bal / 100:.2f}",
           "card_end_balance": f"{-r['cc'].bal / 100:.2f}" if r["cc"] else ""}
    obs, dec = observed(r), {}
    for d in r["declined"]:
        if d[1] == "disc":  # foregone or declined everyday spending
            dec[MONTHS.index((d[0].year, d[0].month)), d[3]] = dec.get((MONTHS.index((d[0].year, d[0].month)), d[3]), 0) + d[2] / 100
    monthly = [{"persona": r["pid"], "month": "%d-%02d" % MONTHS[t], "category": c,
                "ar_factor": f"{h['ar'][t]:.6f}", "trend_factor": f"{math.exp(h['trend'] * (t - 5.5) / 12):.6f}",
                "expected": f"{r['E'][t, c]:.2f}", "budget": f"{r['budget'][t, c]:.2f}", "booked": f"{obs[t, c]:.2f}",
                "not_spent": f"{dec.get((t, c), 0):.2f}"} for t in range(len(MONTHS)) for c in CATS]
    return row, monthly


def write_csv(path, rows):
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]), lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


def summary(results, seas):
    n = len(results)
    cards = [r for r in results if r["cc"]]
    ends = sorted(r["ca"].bal / 100 for r in results)
    q = lambda xs, f: xs[min(len(xs) - 1, int(f * len(xs)))]
    lines = [f"# Open Banking synthetic data: summary", "",
             f"Written by `ob_generator.py` (seed {SEED}, N = {n}); 1 November 2025 to 31 October 2026, pending payments "
             "on 1 and 2 November 2026. Synthetic data, not real bank records.", "",
             "| Quantity | Value |", "|---|---|",
             f"| Personas | {n} |",
             f"| Accounts held | {sum(2 + bool(r['cc']) for r in results)} (current {n}, savings {n}, credit card {len(cards)}) |",
             f"| Credit-card holders paying in full | {sum(r['h']['card_full'] for r in cards)} of {len(cards)} |",
             f"| Current account below zero at any time | {sum(r['ca'].minbal < 0 for r in results)} |",
             f"| Overdrawn at the end of at least one day, after any top-up from savings | {sum(r['od_days'] > 0 for r in results)} |",
             f"| Topped up from savings at least once | {sum(any(x['desc'].startswith('FROM SAVINGS') for x in r['ca'].tx) for r in results)} |",
             f"| In unarranged overdraft at least one day (flagged) | {sum(bool(r['unarranged']) for r in results)} |",
             *[f"| Persons with {k} payments (count) | {sum(any(d[4] == k for d in r['declined']) for r in results)} "
               f"({sum(d[4] == k for r in results for d in r['declined'])}) |" for k in ("foregone", "declined", "returned")],
             f"| Savings standing order | {sum(r['save_so'] > 0 for r in results)} |",
             f"| BNPL plans (persons) | {sum(bool(r['h']['bnpl']) for r in results)} |",
             f"| Synthetic lumpy purchases | {sum(len(r['h']['lumpy']) for r in results)} |",
             f"| Booked transactions | {sum(len(r['ca'].tx) + len(r['sv'].tx) + (len(r['cc'].tx) if r['cc'] else 0) for r in results)} |",
             f"| Pending transactions | {sum(len(r['ca'].pending) + (len(r['cc'].pending) if r['cc'] else 0) for r in results)} |",
             f"| Current-account end balance [GBP], min / lower quartile / median / upper quartile / max | "
             f"{ends[0]:.2f} / {q(ends, 0.25):.2f} / {q(ends, 0.5):.2f} / {q(ends, 0.75):.2f} / {ends[-1]:.2f} |",
             f"| Savings end balance [GBP], median | {sorted(r['sv'].bal for r in results)[n // 2] / 100:.2f} |",
             f"| Card end balance owed [GBP], median over holders | "
             f"{sorted(-r['cc'].bal for r in cards)[len(cards) // 2] / 100 if cards else 0:.2f} |", "",
             "Seasonal factors (ONS retail sales J5AH, mean of 2021 to 2025 with each year scaled to mean 1):", "",
             "| " + " | ".join(calendar.month_abbr[m] for m in range(1, 13)) + " |", "|" + "---|" * 12,
             "| " + " | ".join(f"{seas[m]:.4f}" for m in range(1, 13)) + " |", ""]
    return "\n".join(lines)


def generate(out, n=100):
    out.mkdir(parents=True, exist_ok=True)
    (out / "csv").mkdir(exist_ok=True)
    for old in [*out.glob("persona*.json"), *(out / "csv").glob("persona*.csv"), out / "ground_truth.csv",
                out / "ground_truth_monthly.csv", out / "summary.md"]:
        old.unlink(missing_ok=True)  # generated outputs only
    ons, rates, seas = ms.load_ons(), Rates(), season()
    rng = random.Random(SEED + 1)  # the same tenure stream as mock_statements.generate
    chosen = ms.choose_personas(ons, n)[0]
    results, truth, monthly = [], [], []
    for i, (key, p) in enumerate(chosen):
        tenure = ms.sample_tenure(int(p["age"]), ons, rng)
        r = build(i, key, p, tenure, ons, rates, seas)
        base = f"{r['pid']}_{r['uid']}"
        (out / f"{base}.json").write_text(json.dumps(ob_document(r), separators=(",", ":")), encoding="utf-8")
        with open(out / "csv" / f"{base}.csv", "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh, lineterminator=ms.LINE_END)
            w.writerow(ms.COLUMNS)
            w.writerows(csv_rows(r))
        row, mon = truth_rows(r)
        truth.append(row)
        monthly += mon
        results.append(r)
    write_csv(out / "ground_truth.csv", truth)
    write_csv(out / "ground_truth_monthly.csv", monthly)
    (out / "summary.md").write_text(summary(results, seas), encoding="utf-8", newline="\n")
    return results


# ---------------------------------------------------------------- self-check
def corr(x, y):
    mx, my = st.mean(x), st.mean(y)
    return sum((a - mx) * (b - my) for a, b in zip(x, y)) / math.sqrt(sum((a - mx) ** 2 for a in x) * sum((b - my) ** 2 for b in y))


def check(n=100):
    with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
        res = generate(Path(a), n)
        generate(Path(b), n)
        files = sorted(p.relative_to(a) for p in Path(a).rglob("*") if p.is_file())
        assert files == sorted(p.relative_to(b) for p in Path(b).rglob("*") if p.is_file())
        for f in files:
            assert (Path(a) / f).read_bytes() == (Path(b) / f).read_bytes(), f"{f} differs between runs"
        print(f"reruns identical: {len(files)} files")
        # same personas as mock_statements (names and uuid8)
        if n == 100 and ms.OUT.exists():
            assert [f"{r['pid']}_{r['uid']}" for r in res] == sorted(p.stem for p in ms.OUT.glob("persona*.csv"))
        mccs, unarr = set(), 0
        for r in res:
            doc = json.loads((Path(a) / f"{r['pid']}_{r['uid']}.json").read_text(encoding="utf-8"))["Data"]
            accs = {x["AccountId"]: x for x in doc["Account"]}
            assert len(accs) == 2 + bool(r["cc"]) and [x["AccountSubType"] for x in doc["Account"]][:2] == ["CurrentAccount", "Savings"]
            for acc in accs:
                tx = [x for x in doc["Transaction"] if x["AccountId"] == acc]
                booked = [x for x in tx if x["Status"] == "Booked"]
                pend = [x for x in tx if x["Status"] == "Pending"]
                bal = {x["Type"]: mb.signed(x) for x in doc["Balance"] if x["AccountId"] == acc}
                run = bal["OpeningBooked"]
                times = [dt.datetime.fromisoformat(x["BookingDateTime"]) for x in booked]
                assert times == sorted(times) and times[-1].date() <= END
                for x in booked:  # balances reconcile transaction by transaction
                    run += mb.pennies(x["Amount"]["Amount"]) * (-1 if x["CreditDebitIndicator"] == "Debit" else 1)
                    assert mb.signed(x["Balance"]) == run, (r["pid"], x)
                    if "MerchantDetails" in x:
                        mccs.add(int(x["MerchantDetails"]["MerchantCategoryCode"]))
                assert bal["InterimBooked"] == run, "pending payments must not change the booked balance"
                assert all("Balance" not in x and dt.datetime.fromisoformat(x["BookingDateTime"]) < AS_OF
                           and dt.datetime.fromisoformat(x["BookingDateTime"]).date() > END for x in pend)
                assert bal["InterimAvailable"] == run - sum(mb.pennies(x["Amount"]["Amount"]) for x in pend)
                mccs |= {int(x["MerchantDetails"]["MerchantCategoryCode"]) for x in pend}
                sub = accs[acc]["AccountSubType"]
                if sub == "CreditCard":  # never above the limit
                    assert all(-mb.signed(x["Balance"]) <= r["cl"] for x in booked) and r["cc"].minbal >= -r["cl"]
                if sub == "CurrentAccount":  # within the arranged limit unless a flagged committed payment or interest
                    for x, y in zip(booked, r["ca"].tx):
                        if mb.signed(x["Balance"]) < -r["od"] and y["p"] < 0:
                            assert y["cls"] in ("committed", "bnpl", "interest", "annual") and r["unarranged"], (r["pid"], y)
                if sub == "Savings":
                    assert all(mb.signed(x["Balance"]) >= 0 for x in booked)
            unarr += bool(r["unarranged"])
            # current-account CSV through the engine
            text = (Path(a) / "csv" / f"{r['pid']}_{r['uid']}.csv").read_text(encoding="utf-8")
            tx = af.parse(text)
            assert len(tx) == len(r["ca"].tx) and tx[-1]["balance"] == r["ca"].bal / 100
            inc = af.detect_income(tx)
            assert inc["name"] == "FAKE EMPLOYER LTD SALARY" and inc["monthly"] == r["net"], (r["pid"], inc)
            due = {c["name"] for c in af.detect_committed(tx, END)}
            want = {t["desc"] for t in tx if t["type"] in ("DD", "SO") and (END - t["date"]).days <= 35}
            assert want and want <= due, (r["pid"], want - due)
            assert {"ENERGY SUPPLIER AND WATER", "MOBILE AND BROADBAND"} <= due
            assert len({(t["date"].year, t["date"].month) for t in tx}) == 12
        assert mccs <= set(MCC), mccs - set(MCC)
        print(f"balances reconcile; pending excluded from booked; card limits held; {unarr} persons flagged unarranged; "
              f"{len(mccs)} MCCs used, all in the table; CSV exports parse and salary and committed payments detected")

        # ground truth recoverable in aggregate
        clean = [r for r in res if not any(d[1] == "disc" for d in r["declined"])]
        ratio, lx, ly = [], [], []
        for r in clean:
            obs = observed(r)
            for c in CATS:
                o = sum(obs[t, c] for t in range(len(MONTHS)))
                e = sum(r["E"][t, c] for t in range(len(MONTHS)))  # ONS mean x multiplier x season x trend
                ratio.append(o / e)
                lx.append(math.log(r["h"]["mult"][c]))
                ly.append(math.log(o / e * r["h"]["mult"][c]))  # observed multiplier estimate
        med = st.median(ratio)
        c_m = corr(lx, ly)
        print(f"multipliers: {len(clean)} persons without declined spending; median observed/expected {med:.4f}; "
              f"range {min(ratio):.3f} to {max(ratio):.3f}; corr(ln estimate, ln truth) {c_m:.3f}")
        assert abs(med - 1) <= 0.03 and all(abs(x - 1) <= 0.35 for x in ratio) and c_m >= 0.9
        num_, den = 0.0, 0.0
        for r in clean:
            obs = observed(r)
            y = [math.log(sum(obs[t, c] for c in CATS) / sum(r["E"][t, c] for c in CATS)) + AR_SD ** 2 / 2
                 for t in range(len(MONTHS))]
            num_ += sum(a * b for a, b in zip(y, y[1:]))
            den += sum(a * a for a in y[:-1])
        rho_hat, rho_true = num_ / den, st.mean(r["h"]["rho"] for r in clean)
        print(f"AR(1): pooled estimate {rho_hat:.3f}, mean true coefficient {rho_true:.3f}")
        assert abs(rho_hat - rho_true) <= 0.1
        s_hat, s_true = [], []
        for r in res:
            win, tot, frac = 0.0, 0.0, []
            for t, (y, m) in enumerate(MONTHS):
                pday, dim = ms.payday(y, m), calendar.monthrange(y, m)[1]
                wdays = {pday + dt.timedelta(days=k) for k in range(PAYDAY_DAYS)} & {dt.date(y, m, d) for d in range(1, dim + 1)}
                frac.append(len(wdays) / dim)
                for b in (r["ca"], r["cc"]) if r["cc"] else (r["ca"],):
                    for x in b.tx:
                        if x["cls"] == "disc" and (x["t"].year, x["t"].month) == (y, m):
                            tot += -x["p"]
                            win += -x["p"] if x["t"].date() in wdays else 0
            k = st.mean(frac)
            s_hat.append((win / tot - k) / (1 - k))
            s_true.append(r["h"]["payday_share"])
        c_s, mae = corr(s_hat, s_true), st.mean(abs(a - b) for a, b in zip(s_hat, s_true))
        print(f"payday share: corr(estimate, truth) {c_s:.3f}, mean absolute error {mae:.3f}")
        assert c_s >= 0.8 and mae <= 0.05
        g_hat, g_true = [], []
        for r in clean:
            obs = observed(r)
            y = [math.log(sum(obs[t, c] for c in CATS) / sum(r["E"][t, c] / math.exp(r["h"]["trend"] * (t - 5.5) / 12) for c in CATS))
                 for t in range(len(MONTHS))]
            ts = [t - 5.5 for t in range(len(MONTHS))]
            g_hat.append(12 * sum(a * b for a, b in zip(ts, y)) / sum(a * a for a in ts))
            g_true.append(r["h"]["trend"])
        print(f"trend (diagnostic, not asserted): corr(estimate, truth) {corr(g_hat, g_true):.3f}; "
              f"sd of estimate minus truth {st.stdev(a - b for a, b in zip(g_hat, g_true)):.3f} per year")
    print("self-check passed")


if __name__ == "__main__":
    sys.modules.setdefault("ob_generator", sys.modules[__name__])
    n = int(sys.argv[sys.argv.index("--n") + 1]) if "--n" in sys.argv else 100
    if "--check" in sys.argv:
        check(n)
    else:
        res = generate(OUT, n)
        print(f"wrote {len(res)} personas to {OUT}")
