"""Open Banking-native synthetic data, generation 2 (task T20).

Twelve months (1 November 2025 to 31 October 2026) of UK Open Banking Read/Write API v3.1 account-information objects for
the same 100 personas as mock_statements.py. Each person holds between one and seven accounts, decided from their
persona attributes: a main current account (everyone, arranged overdraft), and possibly a second current account at
another provider, a joint current account (couples only), an easy-access savings account, a cash ISA and up to two
credit cards (the second at another provider). Money moves consistently between a person's own accounts. Transactions
carry merchant details with ISO 18245 merchant category codes; there are pending card payments on 1 and 2 November
2026, direct-debit mandates, standing orders and scheduled (BNPL) payments. Each person has persistent spending habits
with known ground truth, saved so that task T22 can test whether models recover them.

Sources. Personas, salaries (ASHE, uprated by AWE), net pay (2026/27 tax and NI), tenure (EHS) and spending (Family
Spending, uprated by CPI) come from mock_statements.py, imported and not changed. Seasonality is the ONS retail-sales
profile (J5AH) from market_data.seasonality(). The annual motor-insurance direct debit and the package holiday are the
persona's own Family Spending amounts (workbook 3, A35 rows 366 and 298); motor insurance is taken out of the monthly
pool so that totals are unchanged, and the package holiday is added (mock_statements.py excludes it from everyday spending). Holding probabilities for savings accounts, cash ISAs, credit cards and a second current-account provider
come from the FCA Financial Lives 2024 survey tables (data/financial-lives-survey-2024-tables-volume-{3,5}-*.xlsx; see
HOLDINGS). Savings interest follows Bank Rate (data/boe_bank_rate_*.csv) less a synthetic margin. Every number in the
SYNTHETIC block below is an assumption, not from a source.

Output: Analysis/open_banking/<persona>.json (one per persona, compact JSON, about 50 MB in all: gitignored except a
five-persona sample; regenerate in a few seconds), csv/<persona>.csv (main current account, statement layout),
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
from collections import Counter
from pathlib import Path
from zoneinfo import ZoneInfo

import openpyxl

import market_data as md
import mock_bank as mb  # BankTransactionCode names and the OB amount shape (imports statements, standard library only)
import mock_statements as ms
import statements as af

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
#        (net monthly pay below GBP, arranged overdraft limit GBP, first credit-card limit GBP)
OD_EAR = 0.399                  # overdraft interest, arranged and unarranged alike, EAR; accrued daily, posted monthly
JOINT_P = 0.5                   # couples (household type) holding a joint current account
JOINT_BILLS = ("rent", "energy", "council_tax")  # paid from the joint account, at twice the persona's share
CARD2_P = (0.15, 0.35)          # card holders holding a second card: household income below / at least 50,000 GBP
CARD2_LIMIT = 0.5               # second card's limit as a share of the first card's
CARD1_P = 0.7                   # two-card holders: share of card payments made on the first card
CARD_FULL_P = 0.6               # share of card holders who pay in full (the others pay the minimum), all cards alike
CARD_SHARE = (0.3, 0.8)         # card holders: share of discretionary card payments made on a credit card, uniform
CARD_OPEN = (0.2, 0.6)          # minimum payers: each card's opening balance as a share of its limit; full payers 0
CARD_APR = 0.249                # purchase rate; monthly interest = APR / 12 on the balance carried past the due date
CARD_BUFFER = 0.05              # purchases accepted only up to (1 - buffer) x limit, so interest cannot breach the limit
MIN_PAY = (2500, 0.01)          # minimum payment: max(25 GBP, 1% of the statement balance + that statement's interest)
DUE_DAYS = 25                   # card payment by direct debit this many days after the statement date (day 1 to 28)
SECOND_CATS = (9, 11)           # second current account: recreation and eating-out card payments come from it first
SECOND_ROUND = 1000             # its monthly top-up = expected spending in SECOND_CATS, rounded up to 10 GBP (pence)
SAVE_OPEN = (0.0, 3.0)          # savings opening balance in months of net pay, uniform (savings-account holders)
ISA_OPEN = (0.0, 6.0)           # cash ISA opening balance in months of net pay, uniform (ISA holders)
SAVE_P, SAVE_SHARE = 0.6, 0.5   # share of savings or ISA holders with a monthly standing order; its size vs expected surplus
SAVE_FINAL_P = 1 / 3            # share of those standing orders with a final payment date (a fixed-term savings goal)
ISA_TOPUP = 0.5                 # once, in March or April 2026: this share of the savings balance moves to the ISA
SAVE_MARGIN, ISA_MARGIN = 0.75, 0.5  # AER = Bank Rate minus this many percentage points, floored at 0
PENDING = (2, 5)                # pending card payments on 1 and 2 November 2026, uniform count
# Behaviour: card purchases (everyday and one-off) are foregone while the main current account is overdrawn; at the end
# of each day an overdrawn main current account is topped up from savings, then the cash ISA, as far as they go.
# Committed payments (direct debits, rent, BNPL instalments, card repayments, transfers to the joint account) are always
# paid, into unarranged overdraft if need be (flagged per person). The partner's joint-account contribution equals the
# persona's (the partner is not otherwise modelled).

# ---------------------------------------------------------------- HOLDINGS from the FCA Financial Lives 2024 survey
# Weighted data tables, base all UK adults (fieldwork 5 February to 16 June 2024, 17,950 respondents). Volume 3, sheet
# ProductHolding: column percentages holding each product. Volume 5, sheet ProductHolding, Table 1 (P_RB5_rebased, base
# adults with a current account with a bank, building society or credit union): share holding a current account with
# each provider group. P(current accounts at two or more provider groups) is taken as sum(group shares) - 1, a lower
# bound on holding a second provider (two providers in one group count once). Each probability combines the persona's
# age band and household-income band as total x (age / total) x (income / total), clipped to [0.01, 0.99]
# (ponytail: age and income treated as independent; upgrade with the microdata from the Geographic Data Service).
# Household income = the persona's ASHE gross pay (April 2025), doubled for couples (synthetic: partner earns the same).
F_FLS3 = ms.DATA / "financial-lives-survey-2024-tables-volume-3-product-ownership.xlsx"
F_FLS5 = ms.DATA / "financial-lives-survey-2024-tables-volume-5-retail-banking.xlsx"
FLS_AGE = (5, ("18-24", "25-34", "35-44", "45-54", "55-64"))
FLS_INC = (34, ("Less than £15k", "£15k - <£30k", "£30k - <£50k", "£50k - <£70k", "£70k - <£100k", "£100k - <£250k", "£250k+"))
FLS_INC_LO = (0, 15000, 30000, 50000, 70000, 100000, 250000)
FLS_AGE_LO = (18, 25, 35, 45, 55)
FLS3_ROWS = {"savings": "Savings account (bank, building society or NS&I)", "cash_isa": "Cash ISA", "credit_card": "Credit card"}
FLS5_ROWS = ("NET: Building societies", "NET: Challengers", "NET: Digital banks", "NET: Main high street banks", "NET: Other banks")
COUPLES = ("couple", "couple_kids")

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
# ONS Family Spending detail rows (workbook 3, A35) paid as annual or one-off payments. Motor insurance is carved out of the
# monthly pool 12 here; package holidays are already excluded from pool 9 by ms.spend_model, so they are only added.
CARVE = {"holiday": (298, "9.6 Package holidays", 9), "motor": (366, "12.4.3 Vehicle insurance", 12)}
assert CARVE["holiday"][0] == ms.A35["pkg_hol"][0]

# Accounts: key -> (OB AccountSubType, provider, nickname, sort code or None for a card). Providers are fictional.
ACCOUNTS = {"ca": ("CurrentAccount", "MockBank", "Current account", "000000"),
            "ca2": ("CurrentAccount", "MockDigital", "Current account (other provider)", "000001"),
            "joint": ("CurrentAccount", "MockBank", "Joint current account", "000000"),
            "sv": ("Savings", "MockBank", "Easy-access savings", "000000"),
            "isa": ("Savings", "MockBank", "Cash ISA", "000000"),
            "cc1": ("CreditCard", "MockBank", "Credit card", None),
            "cc2": ("CreditCard", "MockCards", "Credit card (other provider)", None)}
CARDS, CURRENT = ("cc1", "cc2"), ("ca", "ca2", "joint")
# Proprietary codes: the statement types of mock_statements.py, plus CHG (overdraft interest), TFR (transfer between own
# accounts), FPI (faster payment in, the partner's contribution), INT (interest), PUR (card purchase), PAY (card payment
# received). ponytail: Lloyds-style codes are an unchecked belief, as in mock_statements.py; BankTransactionCode is given
# only for the four codes mock_bank.ISO maps.


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


def fls():
    """Product -> [total, five age bands 18-24 to 55-64, seven household-income bands] as fractions (see HOLDINGS)."""
    out = {}
    for f, names in ((F_FLS3, FLS3_ROWS), (F_FLS5, dict(enumerate(FLS5_ROWS)))):
        assert f.exists(), f"{f.name} is missing; see data/README.md for the download command"
        rows = list(openpyxl.load_workbook(f, read_only=True)["ProductHolding"].iter_rows(values_only=True))
        assert rows[1][2] == "Total" and tuple(rows[2][FLS_AGE[0]:FLS_AGE[0] + 5]) == FLS_AGE[1]
        assert tuple(rows[2][FLS_INC[0]:FLS_INC[0] + 7]) == FLS_INC[1], f.name
        end = next((i for i, r in enumerate(rows) if i > 0 and str(r[0] or "").startswith("Table ")), len(rows))
        assert str(rows[0][0]) == "Table 1" and (f == F_FLS3 or "P_RB5" in str(rows[1][0]))
        for key, label in names.items():
            i = next(i for i in range(end) if rows[i][0] == label and rows[i][1] == "Unweighted")
            c = rows[i + 2]
            assert c[1] == "Col %", (f.name, label)
            v = [c[2], *c[FLS_AGE[0]:FLS_AGE[0] + 5], *c[FLS_INC[0]:FLS_INC[0] + 7]]
            assert all(isinstance(x, (int, float)) and 0 < x <= 1 for x in v), (label, v)
            out[key] = [float(x) for x in v]
    groups = [out.pop(k) for k in range(len(FLS5_ROWS))]
    out["second_current"] = [sum(g[j] for g in groups) - 1 for j in range(13)]
    assert all(0 < x < 1 for x in out["second_current"])
    return out


def holding_p(rates, age, hh_income):
    """Product -> probability for this age and household income (see HOLDINGS)."""
    a = bisect.bisect_right(FLS_AGE_LO, age) - 1
    i = bisect.bisect_right(FLS_INC_LO, hh_income) - 1
    assert 0 <= a < 5
    return {k: min(0.99, max(0.01, v[1 + a] * v[6 + i] / v[0])) for k, v in rates.items()}, FLS_AGE[1][a], FLS_INC[1][i]


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
    """Bank Rate in force on a date (data/boe_bank_rate_*.csv via statements.bank_rate)."""
    def __init__(self):
        rows = af.bank_rate()
        self.d, self.v = [r[0] for r in rows], [r[1] for r in rows]

    def on(self, d):
        return self.v[max(0, bisect.bisect_right(self.d, d) - 1)]

    def aer(self, d, margin):
        return max(0.0, self.on(d) - margin)


# ---------------------------------------------------------------- one persona
def habits(idx, key, p, ashe_gross, net, cl, rates_fls):
    """Holdings and every person-level trait, drawn in a fixed order from the person's own stream (ground truth)."""
    r = random.Random(f"{SEED}-ob-habit-{idx}")
    h = dict(mult={c: r.lognormvariate(-HABIT_SD ** 2 / 2, HABIT_SD) for c in CATS}, rho=r.uniform(*AR_RHO),
             payday_share=r.uniform(*PAYDAY_SHARE))
    h["trend"] = r.uniform(-TREND_G, TREND_G) if r.random() < TREND_P else 0.0
    e = [r.gauss(0, AR_SD)]
    for _ in range(len(MONTHS)):  # 12 history months and the pending month
        e.append(h["rho"] * e[-1] + math.sqrt(1 - h["rho"] ** 2) * r.gauss(0, AR_SD))
    h["ar"] = [math.exp(x - AR_SD ** 2 / 2) for x in e]
    # holdings
    hh = ashe_gross * (2 if key in COUPLES else 1)
    prob, h["age_band"], h["income_band"] = holding_p(rates_fls, int(p["age"]), hh)
    h["p"] = prob | {"joint": JOINT_P if key in COUPLES else 0.0}
    held = ["ca"]
    if r.random() < prob["second_current"]:
        held.append("ca2")
    if r.random() < h["p"]["joint"]:
        held.append("joint")
    if r.random() < prob["savings"]:
        held.append("sv")
    if r.random() < prob["cash_isa"]:
        held.append("isa")
    p2 = CARD2_P[hh >= 50000]
    h["p"]["second_card_given_card"] = p2
    if r.random() < prob["credit_card"]:
        held.append("cc1")
        if r.random() < p2:
            held.append("cc2")
    h["held"] = held
    h["card_full"] = r.random() < CARD_FULL_P
    h["card_share"] = r.uniform(*CARD_SHARE)
    h["stmt_day"] = {k: r.randint(1, 28) for k in CARDS}
    h["limit"] = {"cc1": pence(cl), "cc2": pence(cl * CARD2_LIMIT)}
    h["card_open"] = {k: 0 if h["card_full"] else pence(r.uniform(*CARD_OPEN) * h["limit"][k] / 100) for k in CARDS}
    h["save_open"] = pence(r.uniform(*SAVE_OPEN) * net)
    h["isa_open"] = pence(r.uniform(*ISA_OPEN) * net)
    h["saver"] = r.random() < SAVE_P
    h["save_final"] = r.random() < SAVE_FINAL_P
    h["isa_topup"] = dt.date(2026, 3, 15) + dt.timedelta(days=r.randint(0, 31))
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
    return h


class Book:
    """Booked and pending transactions of one account, with running balance in pence (positive = in credit).
    limit: arranged overdraft (current accounts) or credit limit (cards), in pence."""
    def __init__(self, key, acc, opening, limit=0):
        self.key, self.acc, self.bal, self.opening, self.limit, self.tx, self.pending = key, acc, opening, opening, limit, [], []
        self.minbal = opening

    def post(self, t, p, desc, code, cls, **kw):
        self.bal += p
        self.minbal = min(self.minbal, self.bal)
        self.tx.append(dict(t=t, p=p, desc=desc, code=code, cls=cls, bal=self.bal, **kw))

    def room(self, p, bal=None):
        """Can a purchase of p pence be taken? Cards keep a buffer below the limit; current accounts stay in the arranged limit."""
        b = self.bal if bal is None else bal
        return -b + p <= self.limit * (1 - CARD_BUFFER) if self.key in CARDS else b - p >= -self.limit


def build(idx, key, p, tenure, ons, rates, seas, rates_fls):
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
        if k != "holiday":  # package holidays are already out of pool 9 (see CARVE)
            assert 0 <= w <= pool[c], (pid, k, w, pool[c])
            pool[c] -= w
        annual[k] = pence(w * 52)
    od_gbp, cl_gbp = band(net)
    h = habits(idx, key, p, ashe_gross, net, cl_gbp, rates_fls)
    od = pence(od_gbp)
    rng = random.Random(f"{SEED}-ob-tx-{idx}")
    uid = p["uuid"][:8]
    town = p["municipality"].upper().replace("CITY OF ", "")[:14]
    merch = {c: ([m.replace("@RAIL@", ms.RAIL[region]) for m in ms_], n) for c, (ms_, n) in ms.MERCH.items()}
    skind, sname = ms.sports_item(p)
    dr = ms.decile_ratio(dec, ons)
    held = h["held"]
    cards = [k for k in CARDS if k in held]
    joint = "joint" in held

    # expected discretionary spending (ground truth) and committed amounts
    trend = [math.exp(h["trend"] * (t - 5.5) / 12) for t in range(len(MONTHS) + 1)]
    allm = MONTHS + [PENDING_MONTH]
    E = {(t, c): pool[c] * WK * h["mult"][c] * seas[allm[t][1]] * trend[t] for t in range(len(allm)) for c in CATS}
    fixed = {k: pence(v * WK) for k, v in reg.items()}
    joint_share = sum(fixed.get(k, 0) for k in JOINT_BILLS) if joint else 0
    exp_month = sum(pool[c] * WK * h["mult"][c] for c in CATS) + sum(fixed.values()) / 100 + sum(annual.values()) / 1200
    save_to = "sv" if "sv" in held else "isa" if "isa" in held else None
    save_so = (math.floor(SAVE_SHARE * (net - exp_month) / 10) * 10) if h["saver"] and save_to else 0
    save_so = pence(save_so) if save_so >= 25 else 0
    top2 = -(-pence(sum(pool[c] * WK * h["mult"][c] for c in SECOND_CATS)) // SECOND_ROUND) * SECOND_ROUND if "ca2" in held else 0

    ids = {k: uid if k == "ca" else hexid(p["uuid"], k) for k in held}
    opening = {"ca": pence(net), "ca2": top2, "joint": 2 * joint_share, "sv": h["save_open"], "isa": h["isa_open"],
               **{k: -h["card_open"][k] for k in CARDS}}  # main current account opens with one month's net pay
    limits = {"ca": od, "ca2": 0, "joint": od, **h["limit"]}  # ca2: no arranged overdraft (synthetic)
    B = {k: Book(k, ids[k], opening[k], limits.get(k, 0)) for k in held}
    ca = B["ca"]
    ev = {}  # date -> [(time, seq, event)]
    seq, pair = [0], [0]

    def plan(t, **e):
        if e["p"] <= 0:  # a zero amount (a tiny budget split into pence) is not a transaction
            return
        seq[0] += 1
        ev.setdefault(t.date(), []).append((t, seq[0], e))

    def card_time(d):
        return at(d, 7) + dt.timedelta(seconds=rng.randrange(15 * 3600))

    def transfer(t, src, dst, p, desc_out, desc_in, code_out="TFR", cls="transfer"):
        """Move p pence between two of the person's accounts; both legs share a TransactionReference."""
        pair[0] += 1
        ref = f"T{pair[0]:05d}"
        B[src].post(t, -p, desc_out, code_out, cls, pair=ref)
        B[dst].post(t, p, desc_in, "PAY" if dst in CARDS else "TFR", "transfer", pair=ref)

    def name(k):
        return f"{ACCOUNTS[k][1].upper()} {ACCOUNTS[k][2].upper()} {ids[k].upper()}"

    budget, bnpl_due = {}, []
    for t, (y, m) in enumerate(MONTHS):
        dim = calendar.monthrange(y, m)[1]
        D = lambda day: dt.date(y, m, min(day, dim))
        pday = ms.payday(y, m)
        window = [pday + dt.timedelta(days=k) for k in range(PAYDAY_DAYS) if (pday + dt.timedelta(days=k)).month == m]
        plan(at(pday, 1), kind="credit", acct="ca", p=pence(net), desc="FAKE EMPLOYER LTD SALARY", code="BGC", cls="salary")
        bill = lambda k: ("joint", 2 * fixed[k]) if joint and k in JOINT_BILLS else ("ca", fixed[k])
        if "rent" in reg:
            a, v = bill("rent")
            plan(at(D(1), 2), kind="debit", acct=a, p=v, code="SO", cls="committed",
                 desc="RENT " + ("COUNCIL HOUSING" if tenure == "Social rented" else "LETTING AGENT"))
        if joint:  # both partners pay their share in on the 28th, before the bills of the 1st
            plan(at(D(28), 2), kind="xfer", src="ca", dst="joint", p=joint_share, code="SO", committed=True,
                 desc_out=name("joint"), desc_in=f"FROM {name('ca')}")
            plan(at(D(28), 2, 5), kind="credit", acct="joint", p=joint_share, desc="PARTNER CONTRIBUTION", code="FPI",
                 cls="external")
        if save_so:
            plan(at(D(1), 2, 30), kind="xfer", src="ca", dst=save_to, p=save_so, code="SO", committed=False,
                 desc_out=name(save_to), desc_in=f"FROM {name('ca')}")
        if top2:
            plan(at(D(1), 2, 15), kind="xfer", src="ca", dst="ca2", p=top2, code="SO", committed=False,
                 desc_out=name("ca2"), desc_in=f"FROM {name('ca')}")
        for day, k, desc in ((5, "energy", "ENERGY SUPPLIER AND WATER"),
                             (15, "council_tax", p["municipality"].upper() + " COUNCIL TAX"),
                             (12, "phone", "MOBILE AND BROADBAND"), (20, "tv", "STREAMING AND TV SUBSCRIPTION")):
            a, v = bill(k)
            plan(at(D(day), 3), kind="debit", acct=a, p=v, desc=desc, code="DD", cls="committed")
        if skind == "gym":
            plan(at(D(3), 3), kind="debit", acct="ca", p=fixed["sports"], desc=sname, code="DD", cls="committed")
        else:
            for a, day in zip(ms.pence_split(fixed["sports"] / 100, [1.0, 1.0]), (8, 22)):
                plan(at(D(day), 18), kind="debit", acct="ca", p=pence(a), desc=f"{sname} {town} GB", code="DEB",
                     cls="committed", merchant=sname, mcc=TICKET_MCC)
        if (y, m) == h["motor"][0]:
            plan(at(D(h["motor"][1]), 3), kind="debit", acct="ca", p=annual["motor"], desc="MOTOR INSURANCE ANNUAL",
                 code="DD", cls="annual")
        if (y, m) == h["holiday"][0]:
            plan(card_time(D(h["holiday"][1])), kind="card", route=cards[::-1] + ["ca"], p=annual["holiday"],
                 cls="lumpy", cat=9, merchant="JET2HOLIDAYS", desc=f"JET2HOLIDAYS {town} GB")
        if "isa" in held and (y, m) == (h["isa_topup"].year, h["isa_topup"].month):
            plan(at(h["isa_topup"], 10), kind="isatopup", p=1)
        bnpl = {}
        for nm, c, first, step, n, frac in h["bnpl"]:
            inst = pence(pool[c] * WK * frac)
            for k in range(n):
                d = first + dt.timedelta(days=step * k)
                if (d.year, d.month) == (y, m):
                    plan(at(d, 9), kind="debit", acct="ca", p=inst, desc=f"{nm} {town} GB", code="DEB", cls="bnpl",
                         cat=c, merchant=nm, mcc=MERCHANT_MCC[nm])
                    bnpl[c] = bnpl.get(c, 0) + inst
                elif d > END and t == len(MONTHS) - 1:
                    bnpl_due.append((d, nm, inst, k + 1, n))
        for c, (merchants, n) in merch.items():
            budget[t, c] = E[t, c] * h["ar"][t] * rng.uniform(*NOISE)
            total = max(0.0, budget[t, c] - bnpl.get(c, 0) / 100)
            for a in ms.pence_split(total, [rng.lognormvariate(0, 0.6) for _ in range(n)]):
                d = rng.choice(window) if rng.random() < h["payday_share"] else D(rng.randint(1, dim))
                mname = rng.choice(merchants)
                plan(card_time(d), kind="card", route=route(rng, h, cards, held, c), p=pence(a), cls="disc", cat=c,
                     merchant=mname, desc=f"{mname} {town} GB")
    for (merchant, mcc, c, lo, hi), d, u in h["lumpy"]:
        plan(card_time(d), kind="card", route=cards[::-1] + ["ca"], p=pence((lo + (hi - lo) * u) * dr[c]), cls="lumpy",
             cat=c, merchant=merchant, desc=f"{merchant} {town} GB")

    # card statements: each opening balance is the statement of the month before the history starts
    state = {}
    for k in cards:
        state[k] = dict(stmt=h["card_open"][k], paid=0)
        due = dt.date(2025, 10, h["stmt_day"][k]) + dt.timedelta(days=DUE_DAYS)
        if h["card_open"][k] and due >= START:
            plan(at(due, 3), kind="cardpay", card=k, p=min_pay(h["card_open"][k], 0))

    declined, unarranged, od_days = [], set(), 0
    acc = {k: 0.0 for k in held}  # interest accrued this month (pence)
    day = START
    while day <= END:
        for t, _, e in sorted(ev.get(day, []), key=lambda x: (x[0], x[1])):
            k = e["kind"]
            if k == "credit":
                B[e["acct"]].post(t, e["p"], e["desc"], e["code"], e["cls"])
            elif k == "debit":
                b = B[e["acct"]]
                b.post(t, -e["p"], e["desc"], e["code"], e["cls"], **{x: e[x] for x in ("cat", "merchant", "mcc") if x in e})
                if b.bal < -b.limit:
                    unarranged.add(day)
            elif k == "xfer":
                if e["committed"] or ca.room(e["p"]):  # an optional standing order the account cannot cover is returned
                    transfer(t, e["src"], e["dst"], e["p"], e["desc_out"], e["desc_in"], e["code"],
                             "committed" if e["committed"] else "transfer")
                    if ca.bal < -ca.limit:
                        unarranged.add(day)
                else:
                    declined.append((t, "save", e["p"], None, "returned"))
            elif k == "isatopup":
                src = "sv" if "sv" in held else "ca"
                move = int(ISA_TOPUP * max(0, B[src].bal - (pence(net) if src == "ca" else 0)))
                if move >= 10000:
                    transfer(t, src, "isa", move, name("isa"), f"FROM {name(src)}")
            elif k == "cardpay":
                transfer(t, "ca", e["card"], e["p"], f"{ACCOUNTS[e['card']][1].upper()} CREDIT CARD",
                         "PAYMENT RECEIVED - THANK YOU", "DD", "committed")
                state[e["card"]]["paid"] += e["p"]
                if ca.bal < -ca.limit:
                    unarranged.add(day)
            elif ca.bal < 0:  # card purchase while the main current account is overdrawn: foregone (cut back)
                declined.append((t, e["cls"], e["p"], e["cat"], "foregone"))
            else:  # card purchase: first account on the route with room, else declined
                a = next((a for a in e["route"] if B[a].room(e["p"])), None)
                if a:
                    B[a].post(t, -e["p"], e["desc"], "PUR" if a in CARDS else "DEB", e["cls"], cat=e["cat"],
                              merchant=e["merchant"], mcc=MERCHANT_MCC[e["merchant"]])
                else:
                    declined.append((t, e["cls"], e["p"], e["cat"], "declined"))
        # end of day: card statements, top-up from savings, interest accrual, month-end postings
        for k in cards:
            if day.day == h["stmt_day"][k]:
                carried = max(0, state[k]["stmt"] - state[k]["paid"])
                interest = round(carried * CARD_APR / 12)
                if interest:
                    B[k].post(at(day, 23, 59), -interest, "PURCHASE INTEREST", "INT", "interest")
                owed = -B[k].bal
                state[k].update(stmt=owed, paid=0)
                due = day + dt.timedelta(days=DUE_DAYS)
                if owed > 0 and due <= END:
                    plan(at(due, 3), kind="cardpay", card=k, p=owed if h["card_full"] else min_pay(owed, interest))
        for src in ("sv", "isa"):  # an overdrawn main current account is topped up from savings, as far as they go
            if src in held and ca.bal < 0 < B[src].bal:
                transfer(at(day, 23, 59, 10), src, "ca", min(B[src].bal, -ca.bal), f"TO {name('ca')}", f"FROM {name(src)}")
        if ca.bal < 0:  # end-of-day balance after any top-up
            od_days += 1
        for k, b in B.items():
            if k in CURRENT and b.bal < 0:
                acc[k] += -b.bal * ((1 + OD_EAR) ** (1 / 365) - 1)
            elif k in ("sv", "isa"):
                acc[k] += max(0, b.bal) * rates.aer(day, SAVE_MARGIN if k == "sv" else ISA_MARGIN) / 100 / 365
        if (day + dt.timedelta(days=1)).day == 1:
            for k, b in B.items():
                if round(acc[k]) and k in CURRENT:
                    b.post(at(day, 23, 59, 30), -round(acc[k]), "OVERDRAFT INTEREST", "CHG", "interest")
                    if b.bal < -b.limit:
                        unarranged.add(day)
                elif round(acc[k]):
                    b.post(at(day, 23, 59, 30), round(acc[k]), "INTEREST", "INT", "interest")
                acc[k] = 0.0
        day += dt.timedelta(days=1)

    # pending card payments, 1 November (any time) and 2 November (before 08:00), from the November 2026 budget
    t12 = len(MONTHS)
    avail = {k: b.bal for k, b in B.items()}
    for _ in range(rng.randint(*PENDING)):
        c = rng.choices(CATS, weights=[E[t12, c] for c in CATS])[0]
        merchants, n = merch[c]
        mname = rng.choice(merchants)
        a = pence(E[t12, c] * h["ar"][t12] / n * rng.lognormvariate(-0.18, 0.6))
        t = (at(dt.date(2026, 11, 1), 7) + dt.timedelta(seconds=rng.randrange(15 * 3600)) if rng.random() < 0.7
             else at(dt.date(2026, 11, 2), 6) + dt.timedelta(seconds=rng.randrange(7200)))
        rt = route(rng, h, cards, held, c)
        k = next((k for k in rt if B[k].room(a, avail[k])), None) if avail["ca"] >= 0 and a > 0 else None
        if k:
            avail[k] -= a
            B[k].pending.append(dict(t=t, p=-a, desc=f"{mname} {town} GB", code="PUR" if k in CARDS else "DEB",
                                     cls="pending", cat=c, merchant=mname, mcc=MERCHANT_MCC[mname]))

    return dict(pid=pid, uid=uid, p=p, key=key, tenure=tenure, net=net, gross=gross, ashe=ashe_gross, dec=dec, h=h,
                ids=ids, B=B, od=od, E=E, budget=budget, declined=declined, unarranged=sorted(unarranged),
                od_days=od_days, fixed=fixed, annual=annual, save_so=save_so, save_to=save_to, top2=top2,
                joint_share=joint_share, bnpl_due=sorted(bnpl_due), rates=rates, pool=pool)


def route(rng, h, cards, held, c):
    """Accounts to try for an everyday card payment, in order (drawn now, so balances never change the random stream)."""
    first = []
    if "ca2" in held and c in SECOND_CATS:
        first = ["ca2"]
    if cards and rng.random() < h["card_share"]:
        cc = cards if len(cards) == 1 or rng.random() < CARD1_P else cards[::-1]
        return first + cc + ["ca"]
    return first + ["ca"] + cards


def min_pay(owed, interest):
    return min(owed, max(MIN_PAY[0], round(MIN_PAY[1] * owed) + interest))


# ---------------------------------------------------------------- Open Banking v3.1 objects
def ob_tx(acc, i, x, pending=False, card=None):
    debit = x["p"] < 0
    out = {"AccountId": acc, "TransactionId": f"{acc}-{'P' if pending else ''}{i:05d}",
           "TransactionReference": f"MB{x['t']:%y%m%d}{x['pair'] if 'pair' in x else hexid(acc, i, pending).upper()}",
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


def mandates(r, k):
    """DirectDebit and StandingOrder objects of current account k, from its own booked payments."""
    ids, h, b = r["ids"], r["h"], r["B"][k]
    groups, dds, sos, count = {}, [], [], {"DD": 0, "SO": 0}
    for x in b.tx:
        if x["code"] in ("DD", "SO") and x["p"] < 0:
            groups.setdefault((x["code"], x["desc"]), []).append(x)
    for (code, desc), g in groups.items():
        count[code] += 1
        last, ident = g[-1], f"{ids[k]}-{code}{count[code]:02d}"
        if code == "DD":
            dd = {"AccountId": ids[k], "DirectDebitId": ident, "MandateIdentification": f"MOCK{ident.upper()}",
                  "DirectDebitStatusCode": "Active", "Name": desc, "PreviousPaymentDateTime": iso(last["t"]),
                  "PreviousPaymentAmount": amt(-last["p"])}
            if not desc.endswith("CREDIT CARD"):  # a card payment's day and amount vary with each statement
                dd["Frequency"] = ("IntrvlMnthDay:12:" if g[0]["cls"] == "annual" else "IntrvlMnthDay:01:") + f"{last['t'].day:02d}"
            dds.append(dd)
            continue
        so = {"AccountId": ids[k], "StandingOrderId": ident, "Frequency": f"IntrvlMnthDay:01:{last['t'].day:02d}",
              "Reference": desc, "StandingOrderStatusCode": "Active",
              "LastPaymentDateTime": iso(last["t"]), "LastPaymentAmount": amt(-last["p"]),
              "NextPaymentDateTime": iso(at(add_month(last["t"].date()), last["t"].hour, last["t"].minute)),
              "NextPaymentAmount": amt(-last["p"])}
        dest = next((d for d in r["B"] if d != k and r["ids"][d].upper() in desc), None)
        if desc.startswith("RENT"):
            so |= {"FirstPaymentDateTime": iso(at(h["rent_first"], 2)), "FirstPaymentAmount": amt(-last["p"]),
                   "CreditorAccount": {"SchemeName": "UK.OBIE.SortCodeAccountNumber",
                                       "Identification": "999999" + hexid(r["uid"], "landlord").translate(str.maketrans("abcdef", "123456")),
                                       "Name": desc[5:]}}
        else:  # to one of the person's own accounts
            so |= {"FirstPaymentDateTime": iso(g[0]["t"]), "FirstPaymentAmount": amt(-g[0]["p"]),
                   "CreditorAccount": identification(r, dest)}
            if dest in ("sv", "isa") and h["save_final"]:
                so["FinalPaymentDateTime"] = iso(at(dt.date(2027, 4, 1), 2, 30))
        sos.append(so)
    return dds, sos


def add_month(d):
    return af.add_months(d, 1)


def identification(r, k):
    idx = int(r["pid"][7:])
    sub, prov, _, sort = ACCOUNTS[k]
    if sort is None:
        return {"SchemeName": "UK.OBIE.PAN", "Identification": f"************{(9000 if k == 'cc1' else 8000) + idx:04d}",
                "Name": r["pid"]}
    num = {"ca": 0, "ca2": 0, "joint": 10_000_000, "sv": 50_000_000, "isa": 60_000_000}[k] + idx
    return {"SchemeName": "UK.OBIE.SortCodeAccountNumber", "Identification": f"{sort}{num:08d}",
            "Name": f"{r['pid']} and partner" if k == "joint" else r["pid"]}


def ob_document(r):
    """{"Providers": [{"Provider", "Data": {OB v3.1 objects}}], "Meta"}: one block per provider, as an aggregator sees them."""
    ids, h, idx = r["ids"], r["h"], int(r["pid"][7:])
    blocks = {}
    for k, b in r["B"].items():
        sub, prov, nick, sort = ACCOUNTS[k]
        D = blocks.setdefault(prov, {"Account": [], "Balance": [], "Product": [], "DirectDebit": [], "StandingOrder": [],
                                     "ScheduledPayment": [], "Transaction": []})
        D["Account"].append({"AccountId": ids[k], "Status": "Enabled", "Currency": "GBP", "AccountType": "Personal",
                             "AccountSubType": sub, "Nickname": f"Mock {nick[0].lower()}{nick[1:]}", "Account": [identification(r, k)]})
        D["Balance"] += balances(b, "Arranged" if k in CURRENT else "Credit" if k in CARDS else None)
        sd = {"Note": "Synthetic product terms; see ob_generator.py"}
        if k in CURRENT:
            prod = {"ProductName": f"{prov} Current Account", "ProductType": "PersonalCurrentAccount"}
            sd |= {"ArrangedOverdraftLimit": amt(b.limit), "OverdraftEAR": f"{OD_EAR * 100:.2f}"}
            if k == "joint":
                sd["JointAccount"] = True
        elif k in ("sv", "isa"):
            name = "CashISA" if k == "isa" else "EasyAccessSavings"
            prod = {"ProductName": f"{prov} {'Cash ISA' if k == 'isa' else 'Easy Access Saver'}", "ProductType": "Other",
                    "OtherProductType": {"Name": name, "Description": "Variable rate"}}
            margin = ISA_MARGIN if k == "isa" else SAVE_MARGIN
            sd |= {"InterestRateAER": f"{r['rates'].aer(AS_OF.date(), margin):.2f}",
                   "InterestRateRule": f"Bank Rate minus {margin} percentage points, floored at 0"}
        else:
            prod = {"ProductName": f"{prov} Credit Card", "ProductType": "Other",
                    "OtherProductType": {"Name": "CreditCard", "Description": "Purchase rate"}}
            sd |= {"PurchaseAPR": f"{CARD_APR * 100:.2f}", "CreditLimit": amt(b.limit), "StatementDay": h["stmt_day"][k],
                   "PaymentDueDaysAfterStatement": DUE_DAYS}
        D["Product"].append({"AccountId": ids[k], "ProductId": f"MOCK-{k.upper()}", **prod, "SupplementaryData": sd})
        card = ({"CardSchemeName": "MASTERCARD", "Identification": identification(r, k)["Identification"]} if k in CARDS
                else {"CardSchemeName": "VISA", "Identification": f"************{(0 if k == 'ca' else 7000) + idx:04d}"}
                if k in ("ca", "ca2") else None)
        D["Transaction"] += [ob_tx(ids[k], i, x, card=card) for i, x in enumerate(b.tx, 1)]
        D["Transaction"] += [ob_tx(ids[k], i, x, pending=True, card=card) for i, x in enumerate(b.pending, 1)]
        if k in CURRENT:
            dds, sos = mandates(r, k)
            D["DirectDebit"] += dds
            D["StandingOrder"] += sos
        if k == "ca":
            D["ScheduledPayment"] = [{"AccountId": ids["ca"], "ScheduledPaymentId": f"{ids['ca']}-SP{n:02d}",
                                      "ScheduledPaymentDateTime": iso(at(d, 9)), "ScheduledType": "Execution",
                                      "Reference": nm, "InstructedAmount": amt(a),
                                      "SupplementaryData": {"Instalment": f"{i} of {m}", "Note":
                                                            "BNPL instalment schedule as a BNPL provider would hold it; mock only"}}
                                     for n, (d, nm, a, i, m) in enumerate(r["bnpl_due"], 1)]
    meta = {"Persona": r["pid"], "Uuid8": r["uid"], "FirstAvailableDateTime": iso(at(START, 0)),
            "LastAvailableDateTime": iso(AS_OF), "Generator": "ob_generator.py (task T20)", "Seed": SEED,
            "Synthetic": "Not real bank data. Amounts from ONS figures and stated synthetic assumptions; providers fictional."}
    return {"Providers": [{"Provider": k, "Data": v} for k, v in blocks.items()], "Meta": meta}


def csv_rows(r):
    acct = f"{int(r['pid'][7:]):08d}"
    return [[x["t"].strftime(ms.DATE_FMT), x["code"], ms.SORT_CODE, acct, x["desc"],
             f"{-x['p'] / 100:.2f}" if x["p"] < 0 else "", f"{x['p'] / 100:.2f}" if x["p"] > 0 else "",
             f"{x['bal'] / 100:.2f}"] for x in r["B"]["ca"].tx]


# ---------------------------------------------------------------- ground truth and outputs
def observed(r):
    """{(month index, category): booked GBP} of discretionary card payments and BNPL instalments, all accounts."""
    out = {k: 0.0 for k in r["budget"]}
    for b in r["B"].values():
        for x in b.tx:
            if x["cls"] in ("disc", "bnpl"):
                out[MONTHS.index((x["t"].year, x["t"].month)), x["cat"]] += -x["p"] / 100
    return out


def holdings_text(held):
    c = Counter(ACCOUNTS[k][0] + ("Joint" if k == "joint" else "ISA" if k == "isa" else "") for k in held)
    return ";".join(f"{k}x{v}" for k, v in c.items())


def truth_rows(r):
    h, B = r["h"], r["B"]
    cards = [k for k in CARDS if k in B]
    row = {"persona": r["pid"], "uuid8": r["uid"], "age": r["p"]["age"], "region": r["p"]["region"],
           "household": r["key"], "marital_status": r["p"].get("marital_status", "unknown"), "tenure": r["tenure"],
           "occupation": r["p"]["occupation"], "net_monthly": f"{r['net']:.2f}", "income_decile": r["dec"],
           "fls_age_band": h["age_band"], "fls_household_income_band": h["income_band"],
           "accounts": holdings_text(h["held"]), "n_accounts": len(h["held"]), "account_keys": ";".join(h["held"]),
           "n_credit_cards": len(cards), **{f"p_{k}": f"{v:.4f}" for k, v in h["p"].items()},
           **{f"mult_cat{c}": f"{h['mult'][c]:.6f}" for c in CATS},
           **{f"ons_monthly_cat{c}": f"{r['pool'][c] * WK:.2f}" for c in CATS}, "ar_rho": f"{h['rho']:.6f}", "ar_sd": AR_SD,
           "payday_share": f"{h['payday_share']:.6f}", "trend_per_year": f"{h['trend']:.6f}",
           "overdraft_limit": f"{r['od'] / 100:.2f}",
           "card_limits": ";".join(f"{B[k].limit / 100:.2f}" for k in cards), "card_paid_in_full": int(h["card_full"]) if cards else "",
           "card_share": f"{h['card_share']:.6f}" if cards else "",
           "card_opening_balances": ";".join(f"{h['card_open'][k] / 100:.2f}" for k in cards),
           "savings_opening": f"{h['save_open'] / 100:.2f}" if "sv" in B else "",
           "isa_opening": f"{h['isa_open'] / 100:.2f}" if "isa" in B else "",
           "savings_standing_order": f"{r['save_so'] / 100:.2f}", "savings_standing_order_to": r["save_to"] if r["save_so"] else "",
           "second_current_monthly_topup": f"{r['top2'] / 100:.2f}", "joint_monthly_share": f"{r['joint_share'] / 100:.2f}",
           "holiday_month": "%d-%02d" % h["holiday"][0], "holiday_amount": f"{r['annual']['holiday'] / 100:.2f}",
           "motor_insurance_month": "%d-%02d" % h["motor"][0], "motor_insurance_amount": f"{r['annual']['motor'] / 100:.2f}",
           "lumpy_purchases": ";".join(f"{d.isoformat()} {m[0]}" for m, d, _ in sorted(h["lumpy"], key=lambda x: x[1])),
           "bnpl_plans": ";".join(f"{f.isoformat()} {nm}" for nm, _, f, *_ in h["bnpl"]),
           **{f"{k}_{w}": (sum(d[4] == k for d in r["declined"]) if w == "count" else
                           f"{sum(d[2] for d in r['declined'] if d[4] == k) / 100:.2f}")
              for k in ("foregone", "declined", "returned") for w in ("count", "amount")},
           "below_zero_at_any_time": int(B["ca"].minbal < 0), "overdrawn_days": r["od_days"],
           "unarranged_overdraft_days": len(r["unarranged"]),
           **{f"end_balance_{k}": f"{B[k].bal / 100:.2f}" if k in B else "" for k in ACCOUNTS}}
    obs, dec = observed(r), {}
    for d in r["declined"]:
        if d[1] == "disc":  # foregone or declined everyday spending
            key = (MONTHS.index((d[0].year, d[0].month)), d[3])
            dec[key] = dec.get(key, 0) + d[2] / 100
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


def summary(results, seas, rates_fls):
    n = len(results)
    held = [r["h"]["held"] for r in results]
    ncards = [sum(k in CARDS for k in x) for x in held]
    ends = sorted(r["B"]["ca"].bal / 100 for r in results)
    q = lambda xs, f: xs[min(len(xs) - 1, int(f * len(xs)))]
    dist = Counter(len(x) for x in held)
    fl = {"sv": "savings", "isa": "cash_isa", "ca2": "second_current"}
    lines = ["# Open Banking synthetic data: summary", "",
             f"Written by `ob_generator.py` (seed {SEED}, N = {n}); 1 November 2025 to 31 October 2026, pending payments "
             "on 1 and 2 November 2026. Synthetic data, not real bank records.", "",
             "## Accounts held", "",
             "| Accounts per person | " + " | ".join(str(k) for k in sorted(dist)) + " |",
             "|---|" + "---|" * len(dist),
             "| Persons | " + " | ".join(str(dist[k]) for k in sorted(dist)) + " |", "",
             "| Account | Persons holding | Mean model probability | FLS 2024 UK adults (total) |", "|---|---|---|---|",
             *[f"| {ACCOUNTS[k][2]} | {sum(k in x for x in held)} | "
               f"{st.mean(r['h']['p'][fl[k]] if k in fl else r['h']['p']['joint'] if k == 'joint' else 1.0 for r in results):.3f} | "
               f"{rates_fls[fl[k]][0]:.2f}{' (derived lower bound)' if k == 'ca2' else ''} |" if k in fl else
               f"| {ACCOUNTS[k][2]} | {sum(k in x for x in held)} | "
               f"{st.mean(r['h']['p']['joint'] for r in results) if k == 'joint' else 1.0:.3f} | "
               f"{'not available (synthetic rule)' if k == 'joint' else '0.97 (any current account)'} |"
               for k in ("ca", "ca2", "joint", "sv", "isa")],
             f"| Credit cards, 0 / 1 / 2 | {ncards.count(0)} / {ncards.count(1)} / {ncards.count(2)} | "
             f"{st.mean(r['h']['p']['credit_card'] for r in results):.3f} (any card) | {rates_fls['credit_card'][0]:.2f} (any card) |",
             "", "## Balances and behaviour", "", "| Quantity | Value |", "|---|---|",
             f"| Main current account below zero at any time | {sum(r['B']['ca'].minbal < 0 for r in results)} |",
             f"| Main current account overdrawn at the end of at least one day, after any top-up from savings | {sum(r['od_days'] > 0 for r in results)} |",
             f"| Topped up from savings or ISA at least once | {sum(any(x['desc'].startswith('FROM') and x['code'] == 'TFR' and x['p'] > 0 for x in r['B']['ca'].tx) for r in results)} |",
             f"| In unarranged overdraft at least one day (flagged) | {sum(bool(r['unarranged']) for r in results)} |",
             *[f"| Persons with {k} payments (count) | {sum(any(d[4] == k for d in r['declined']) for r in results)} "
               f"({sum(d[4] == k for r in results for d in r['declined'])}) |" for k in ("foregone", "declined", "returned")],
             f"| Savings or ISA standing order | {sum(r['save_so'] > 0 for r in results)} |",
             f"| BNPL plans (persons) | {sum(bool(r['h']['bnpl']) for r in results)} |",
             f"| Synthetic lumpy purchases | {sum(len(r['h']['lumpy']) for r in results)} |",
             f"| Booked transactions | {sum(len(b.tx) for r in results for b in r['B'].values())} |",
             f"| Pending transactions | {sum(len(b.pending) for r in results for b in r['B'].values())} |",
             f"| Main current-account end balance [GBP], min / lower quartile / median / upper quartile / max | "
             f"{ends[0]:.2f} / {q(ends, 0.25):.2f} / {q(ends, 0.5):.2f} / {q(ends, 0.75):.2f} / {ends[-1]:.2f} |", "",
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
    ons, rates, seas, rates_fls = ms.load_ons(), Rates(), season(), fls()
    rng = random.Random(SEED + 1)  # the same tenure stream as mock_statements.generate
    chosen = ms.choose_personas(ons, n)[0]
    results, truth, monthly = [], [], []
    for i, (key, p) in enumerate(chosen):
        tenure = ms.sample_tenure(int(p["age"]), ons, rng)
        r = build(i, key, p, tenure, ons, rates, seas, rates_fls)
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
    (out / "summary.md").write_text(summary(results, seas, rates_fls), encoding="utf-8", newline="\n")
    return results


# ---------------------------------------------------------------- self-check
def corr(x, y):
    mx, my = st.mean(x), st.mean(y)
    return sum((a - mx) * (b - my) for a, b in zip(x, y)) / math.sqrt(sum((a - mx) ** 2 for a in x) * sum((b - my) ** 2 for b in y))


def check(n=100):
    # holding probabilities: the FLS figures read back as published (spot values from the tables)
    f = fls()
    assert f["credit_card"][0] == 0.65 and f["savings"][1] == 0.40 and f["cash_isa"][12] == 0.37
    assert abs(f["second_current"][0] - 0.27) < 1e-9  # 0.02 + 0.12 + 0.14 + 0.89 + 0.10 - 1
    assert holding_p(f, 21, 10000)[1:] == ("18-24", "Less than £15k") and holding_p(f, 64, 260000)[1:] == ("55-64", "£250k+")
    with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
        res = generate(Path(a), n)
        generate(Path(b), n)
        files = sorted(p.relative_to(a) for p in Path(a).rglob("*") if p.is_file())
        assert files == sorted(p.relative_to(b) for p in Path(b).rglob("*") if p.is_file())
        for f_ in files:
            assert (Path(a) / f_).read_bytes() == (Path(b) / f_).read_bytes(), f"{f_} differs between runs"
        print(f"reruns identical: {len(files)} files")
        if n == 100 and ms.OUT.exists():  # same personas as mock_statements (names and uuid8)
            assert [f"{r['pid']}_{r['uid']}" for r in res] == sorted(p.stem for p in ms.OUT.glob("persona*.csv"))
        mccs, unarr = set(), 0
        for r in res:
            doc = json.loads((Path(a) / f"{r['pid']}_{r['uid']}.json").read_text(encoding="utf-8"))
            accs, tx_all, bal_all = {}, [], []
            for blk in doc["Providers"]:
                accs |= {x["AccountId"]: x for x in blk["Data"]["Account"]}
                tx_all += blk["Data"]["Transaction"]
                bal_all += blk["Data"]["Balance"]
            keys = {v: k for k, v in r["ids"].items()}
            assert len(accs) == len(r["h"]["held"]) and r["h"]["held"][0] == "ca"
            assert "joint" not in r["h"]["held"] or r["key"] in COUPLES
            pairs = Counter()
            for acc in accs:
                k = keys[acc]
                tx = [x for x in tx_all if x["AccountId"] == acc]
                booked = [x for x in tx if x["Status"] == "Booked"]
                pend = [x for x in tx if x["Status"] == "Pending"]
                bal = {x["Type"]: mb.signed(x) for x in bal_all if x["AccountId"] == acc}
                run = bal["OpeningBooked"]
                times = [dt.datetime.fromisoformat(x["BookingDateTime"]) for x in booked]
                assert times == sorted(times) and (not times or times[-1].date() <= END)
                for x, y in zip(booked, r["B"][k].tx):  # balances reconcile transaction by transaction
                    run += mb.signed(x)
                    assert mb.signed(x["Balance"]) == run, (r["pid"], x)
                    if "MerchantDetails" in x:
                        mccs.add(int(x["MerchantDetails"]["MerchantCategoryCode"]))
                    if "pair" in y:
                        pairs[y["pair"]] += mb.signed(x)
                    if k in CURRENT and run < -r["B"][k].limit and y["p"] < 0:  # beyond the arranged limit: flagged and committed
                        assert y["cls"] in ("committed", "bnpl", "interest", "annual") and r["unarranged"], (r["pid"], k, y)
                assert bal["InterimBooked"] == run, "pending payments must not change the booked balance"
                assert all("Balance" not in x and dt.datetime.fromisoformat(x["BookingDateTime"]) < AS_OF
                           and dt.datetime.fromisoformat(x["BookingDateTime"]).date() > END for x in pend)
                assert bal["InterimAvailable"] == run + sum(mb.signed(x) for x in pend)
                mccs |= {int(x["MerchantDetails"]["MerchantCategoryCode"]) for x in pend}
                if k in CARDS:  # never above the limit
                    assert all(-mb.signed(x["Balance"]) <= r["B"][k].limit for x in booked) and r["B"][k].minbal >= -r["B"][k].limit
                if k in ("sv", "isa", "ca2"):
                    assert r["B"][k].minbal >= 0, (r["pid"], k)
                assert ("CreditLine" in next(x for x in bal_all if x["AccountId"] == acc)) == (k in CURRENT or k in CARDS)
            assert all(v == 0 for v in pairs.values()) and all(v == 2 for v in Counter(
                y["pair"] for b in r["B"].values() for y in b.tx if "pair" in y).values()), "own-account transfers must net to zero"
            unarr += bool(r["unarranged"])
            # main current-account CSV through the engine
            text = (Path(a) / "csv" / f"{r['pid']}_{r['uid']}.csv").read_text(encoding="utf-8")
            tx = af.parse(text)
            assert len(tx) == len(r["B"]["ca"].tx) and tx[-1]["balance"] == r["B"]["ca"].bal / 100
            inc = af.detect_income(tx)
            assert inc["name"] == "FAKE EMPLOYER LTD SALARY" and inc["monthly"] == r["net"], (r["pid"], inc)
            due = {c["name"] for c in af.detect_committed(tx, END)}
            want = {t["desc"] for t in tx if t["type"] in ("DD", "SO") and (END - t["date"]).days <= 35}
            assert want and want <= due, (r["pid"], want - due)
            assert "MOBILE AND BROADBAND" in due and ("ENERGY SUPPLIER AND WATER" in due) != ("joint" in r["B"])
            assert len({(t["date"].year, t["date"].month) for t in tx}) == 12
        assert mccs <= set(MCC), mccs - set(MCC)
        dist = Counter(len(r["h"]["held"]) for r in res)
        assert len(dist) >= 4 and min(dist) == 1 and max(dist) >= 5, dist
        print(f"balances reconcile on every account; own-account transfers net to zero; pending excluded from booked; "
              f"card limits held; {unarr} persons flagged unarranged; {len(mccs)} MCCs used, all in the table; CSV "
              f"exports parse and salary and committed payments detected; accounts per person {dict(sorted(dist.items()))}")

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
        med, c_m = st.median(ratio), corr(lx, ly)
        print(f"multipliers: {len(clean)} persons without foregone or declined spending; median observed/expected "
              f"{med:.4f}; range {min(ratio):.3f} to {max(ratio):.3f}; corr(ln estimate, ln truth) {c_m:.3f}")
        assert abs(med - 1) <= 0.03 and all(abs(x - 1) <= 0.35 for x in ratio) and c_m >= 0.9
        num_, den = 0.0, 0.0
        for r in clean:
            obs = observed(r)
            y = [math.log(sum(obs[t, c] for c in CATS) / sum(r["E"][t, c] for c in CATS)) + AR_SD ** 2 / 2
                 for t in range(len(MONTHS))]
            num_ += sum(a_ * b_ for a_, b_ in zip(y, y[1:]))
            den += sum(a_ * a_ for a_ in y[:-1])
        rho_hat, rho_true = num_ / den, st.mean(r["h"]["rho"] for r in clean)
        print(f"AR(1): pooled estimate {rho_hat:.3f}, mean true coefficient {rho_true:.3f}")
        assert abs(rho_hat - rho_true) <= 0.1
        s_hat, s_true, s_clean = [], [], []
        for r in res:
            win, tot, frac = 0.0, 0.0, []
            for t, (y, m) in enumerate(MONTHS):
                pday, dim = ms.payday(y, m), calendar.monthrange(y, m)[1]
                wdays = {pday + dt.timedelta(days=k) for k in range(PAYDAY_DAYS)} & {dt.date(y, m, d) for d in range(1, dim + 1)}
                frac.append(len(wdays) / dim)
                for bk in r["B"].values():
                    for x in bk.tx:
                        if x["cls"] == "disc" and (x["t"].year, x["t"].month) == (y, m):
                            tot += -x["p"]
                            win += -x["p"] if x["t"].date() in wdays else 0
            k = st.mean(frac)
            s_hat.append((win / tot - k) / (1 - k))
            s_true.append(r["h"]["payday_share"])
            s_clean.append(r in clean)
        print(f"payday share, all {len(res)} persons (diagnostic; foregone spending bunches after payday): corr "
              f"{corr(s_hat, s_true):.3f}, mean absolute error {st.mean(abs(a_ - b_) for a_, b_ in zip(s_hat, s_true)):.3f}")
        s_hat, s_true = [a_ for a_, c_ in zip(s_hat, s_clean) if c_], [b_ for b_, c_ in zip(s_true, s_clean) if c_]
        c_s, mae = corr(s_hat, s_true), st.mean(abs(a_ - b_) for a_, b_ in zip(s_hat, s_true))
        print(f"payday share, {len(s_hat)} persons without foregone or declined spending: corr(estimate, truth) "
              f"{c_s:.3f}, mean absolute error {mae:.3f}")
        assert c_s >= 0.8 and mae <= 0.05
        g_hat, g_true = [], []
        for r in clean:
            obs = observed(r)
            y = [math.log(sum(obs[t, c] for c in CATS) / sum(r["E"][t, c] / math.exp(r["h"]["trend"] * (t - 5.5) / 12) for c in CATS))
                 for t in range(len(MONTHS))]
            ts = [t - 5.5 for t in range(len(MONTHS))]
            g_hat.append(12 * sum(a_ * b_ for a_, b_ in zip(ts, y)) / sum(a_ * a_ for a_ in ts))
            g_true.append(r["h"]["trend"])
        print(f"trend (diagnostic, not asserted): corr(estimate, truth) {corr(g_hat, g_true):.3f}; "
              f"sd of estimate minus truth {st.stdev(a_ - b_ for a_, b_ in zip(g_hat, g_true)):.3f} per year")
    print("self-check passed")


if __name__ == "__main__":
    sys.modules.setdefault("ob_generator", sys.modules[__name__])
    n = int(sys.argv[sys.argv.index("--n") + 1]) if "--n" in sys.argv else 100
    if "--check" in sys.argv:
        check(n)
    else:
        res = generate(OUT, n)
        print(f"wrote {len(res)} personas to {OUT}")
