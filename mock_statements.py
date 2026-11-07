"""Mock bank-statement generator for the HackTheBurgh demo (tasks T05, T05b, T05c).

Personas: Nemotron-Personas-UK rows (data/personas_rows_offset*.json), N of them (default 100) from any UK region.
Salary:   ONS ASHE Table 14.7a (annual gross pay, 2025 revised), 3-digit SOC 2020 median.
Spending: ONS Family Spending FYE 2025, workbooks 2 and 3 (each persona's own region, workbook 3), scaled by the gross
          income decile of the persona's salary (workbook 2, Table A4).
Tenure:   English Housing Survey 2024-25 live table FA1201 (England), by age of household reference person.
Output:   Analysis/mock_statements/<persona>.csv and personas.md.

Run:   .venv\\Scripts\\python mock_statements.py [--n 100]
Check: .venv\\Scripts\\python mock_statements.py --check  (asserts; regenerates twice and compares bytes)
Every ONS figure is read from the spreadsheets in data/; none is typed in here.
Merchant names, dates, transaction counts and the BNPL plans are synthetic flavour.
"""
import calendar
import csv
import datetime as dt
import json
import random
import sys
import tempfile
from pathlib import Path

import openpyxl
import pandas as pd

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
OUT = ROOT / "Analysis" / "mock_statements"
SEED = 20261107
END = dt.date(2026, 10, 31)
MONTHS = [(2026, 8), (2026, 9), (2026, 10)]  # three calendar months ending 31 October 2026
WK = 52 / 12  # weeks per month; ONS figures are GBP per week

# ---- Lloyds Banking Group export layout (unchecked belief; change here only) ----
COLUMNS = ["Transaction Date", "Transaction Type", "Sort Code", "Account Number",
           "Transaction Description", "Debit Amount", "Credit Amount", "Balance"]
DATE_FMT = "%d/%m/%Y"
LINE_END = "\n"
SORT_CODE = "00-00-00"  # obviously fake

# ---- Spreadsheet locations. Rows are 1-based, columns 0-based; labels are asserted before use ----
F_ASHE = DATA / "ashe_table14_7a_annual_gross_2025revised.xlsx"   # sheet "All": col 1 SOC code, col 3 median
F_INC = DATA / "fs_workbook2_by_income_fye2025.xlsx"              # A4 (all households), A23 (composition), A32 (tenure)
F_EHS = DATA / "ehs_fa1201_age_by_tenure_2024-25.ods"             # sheet "2024-25": percentages within age group
F_REG = DATA / "fs_workbook3_by_region_fye2025.xlsx"              # A33 (categories), A35 (detail), 3-year average
# A33 / A35 columns by region (header rows 6 to 8 are asserted); key = Nemotron `region`, value = (column, ONS header text)
REGION_COL = {"North East": (6, "north east"), "North West": (7, "north west"),
              "Yorkshire and The Humber": (8, "yorkshire and the humber"), "East Midlands": (9, "east midlands"),
              "West Midlands": (10, "west midlands"), "East of England": (11, "east"), "London": (12, "london"),
              "South East": (13, "south east"), "South West": (14, "south west"), "Wales": (15, "wales"),
              "Scotland": (16, "scotland"), "Northern Ireland": (17, "northern ireland")}
UK = 4                     # A33 / A35 column: United Kingdom
A4_ALL = 14                # A4 column: all households
CAT_A33 = {1: 24, 2: 26, 3: 28, 4: 30, 5: 32, 6: 34, 7: 36, 8: 38, 9: 40, 10: 42, 11: 44, 12: 46}
CAT_A4 = {c: r + 3 for c, r in CAT_A33.items()}
CAT_A23 = {c: r + 1 for c, r in CAT_A33.items()}
# A23 columns used: household type -> (column, persons per household as published, adults sharing the bills)
A23_COLS = {"alone": (10, "1.0", 1), "couple": (11, "2.0", 2),
            "lone_parent": (13, "2.0", 1), "couple_kids": (17, "4.0", 2)}
# A35 detail rows (any region column), with a label fragment asserted at each row
A35 = {"maint": (142, "Maintenance"), "water": (144, "relating to the dwelling"), "energy": (146, "Electricity, gas"),
       "veh_purchase": (210, "Purchase of vehicles"), "tel": (232, "Telephone and telefax services"),
       "internet": (233, "Internet"), "combined_tel": (234, "Combined telecom"),
       "sports": (283, "and equipment hire"), "tv": (286, "and TV licences"), "council_tax": (382, "council tax etc.")}
# A32 (tenure): housing row 30; columns for owned outright, all social rented (col 10, header "All"), all private rented (col 15, "All")
A32_ROW = 30
A32_TENURE = {"Owned outright": 4, "Social rented": 10, "Private rented": 15}
# A4 (income decile): lower boundary row 11 (deciles 2 to 10 in columns 5 to 13), total expenditure row 58; columns 4 to 13 are deciles 1 to 10
A4_BOUND_ROW, A4_TOTAL_ROW, A4_DEC0 = 11, 58, 4
# EHS FA1201, 0-based rows of "percentages within age group" and age columns (header row asserted)
EHS_ROWS = {"Owned outright": 29, "Mortgage": 30, "Social rented": 35, "Private rented": 37}
EHS_BANDS = [(16, 24), (25, 34), (35, 44), (45, 54), (55, 64)]  # columns 1 to 5; personas are aged 21 to 64
# 2025/26 Scottish income tax bands (https://www.gov.uk/scottish-rate-income-tax/2025-to-2026-tax-year, read 7 November 2026):
# (upper limit of gross income, rate). Personal allowance 12,570 at 0%. Rest-of-UK bands are in net_monthly.
SCOT_BANDS = [(12570, 0.0), (15397, 0.19), (27491, 0.20), (43662, 0.21), (75000, 0.42), (125140, 0.45), (float("inf"), 0.48)]


def num(x):
    """ONS cells are text such as '12.30', '[0.40]', '0.00~', '..' or ':'. Return a float, or None if suppressed."""
    if isinstance(x, (int, float)):
        return float(x)
    try:
        return float(str(x).replace(",", "").strip("[]~ "))
    except ValueError:
        return None


def sheet(path, name):
    return list(openpyxl.load_workbook(path, read_only=True)[name].iter_rows(values_only=True))


def label(row):
    return " ".join(str(c) for c in row[:4] if c)


def load_ons():
    ashe = {str(r[1]).lstrip("'"): (n, r) for n, r in enumerate(sheet(F_ASHE, "All"), 1) if r[1]}
    ehs = pd.read_excel(F_EHS, sheet_name="2024-25", header=None, engine="odf")
    assert "percentages within age group" in str(ehs.iloc[28, 8]) and list(ehs.iloc[3, 1:6]) == ["16-24", "25-34", "35-44", "45-54", "55-64"]
    for t, r in EHS_ROWS.items():
        assert ehs.iloc[r, 0] == {"Owned outright": "own outright", "Mortgage": "buying with mortgage",
                                  "Social rented": "all social renters", "Private rented": "all private renters"}[t], (t, r)
    ons = dict(ehs=ehs, ashe=ashe, a33=sheet(F_REG, "A33"), a35=sheet(F_REG, "A35"), a4=sheet(F_INC, "A4"),
               a23=sheet(F_INC, "A23"), a32=sheet(F_INC, "A32"))
    for t in ("a33", "a35"):
        for reg, (c, hdr) in REGION_COL.items():
            got = " ".join(str(ons[t][r][c]) for r in (5, 6, 7) if ons[t][r][c]).lower()
            got = " ".join(got.split())
            assert got == hdr or (reg == "East of England" and got == "east"), (t, reg, got)
        assert ons[t][5][UK] == "United"
    assert ons["a4"][5][A4_ALL] == "All"
    for name, (r, frag) in A35.items():
        assert frag in label(ons["a35"][r - 1]), (name, r, label(ons["a35"][r - 1]))
    assert "Food" in label(ons["a35"][23])
    assert "Housing" in label(ons["a32"][A32_ROW - 1])
    a32 = ons["a32"]
    assert a32[5][4] == "Owners" and a32[5][8].startswith("Social rented") and a32[5][12].startswith("Private rented")
    assert a32[6][4] == "Owned" and a32[6][10] == "All" and a32[6][15] == "All", "A32 tenure columns moved"
    a4 = ons["a4"]
    assert a4[5][A4_DEC0] == "Lowest" and a4[5][A4_DEC0 + 9] == "Highest" and a4[5][A4_ALL] == "All"
    assert a4[A4_BOUND_ROW - 1][0].startswith("Lower boundary") and a4[A4_TOTAL_ROW - 1][0] == "Total expenditure"
    for c, r in CAT_A4.items():
        assert str(c) == str(a4[r - 1][0]), (c, r)
    return ons


# ---- Personas ----
# Nemotron household_type -> (household key = A23 column, age range). Other household types have no A23 column and are skipped.
HTYPES = {"Lives alone, under 65/66": ("alone", 21, 64),
          "Cohabiting couple, no children": ("couple", 21, 64),
          "Married or civil partnership couple, no children": ("couple", 21, 64),
          "Lone parent, dependent children": ("lone_parent", 21, 64),
          "Cohabiting couple, dependent children": ("couple_kids", 21, 64),
          "Married or civil partnership couple, dependent children": ("couple_kids", 21, 64)}
KEYS = ["alone", "couple", "lone_parent", "couple_kids"]
# BNPL options (synthetic): (descriptor, ONS category, interval days, instalments, share of that category's monthly spend)
BNPL_OPTIONS = [("CLEARPAY*NEXT RETAIL", 3, 14, 4, 0.20), ("KLARNA*CURRYS", 9, 30, 3, 0.25), ("KLARNA*ARGOS", 5, 30, 3, 0.25),
                ("PAYPAL*PAYIN3 ASOS", 3, 30, 3, 0.20), ("CLEARPAY*JD SPORTS", 3, 14, 4, 0.20), ("KLARNA*BOOTS", 6, 30, 3, 0.25)]


def bnpl_plans(idx):
    """About a third of personas (idx % 3 == 0) have one plan; provider and first date come from a seeded RNG."""
    if idx % 3:
        return []
    r = random.Random(f"{SEED}-bnpl-{idx}")
    name, c, step, n, frac = r.choice(BNPL_OPTIONS)
    return [(name, c, dt.date(2026, 8, 5) + dt.timedelta(days=r.randint(0, 40)), step, n, frac)]


def choose_personas(ons, n):
    """Seeded, stratified pick: regions cycle and the household key rotates by one each lap; a stratum with no unused
    usable row falls through to the next household key. Returns (chosen, skipped-row counts, usable row count)."""
    rows, skipped = [], {"household type has no A23 column": 0, "age outside 21-64": 0, "no ASHE occupation median": 0}
    for f in sorted(DATA.glob("personas_rows_offset*.json")):
        rows += [r["row"] for r in json.load(open(f, encoding="utf-8"))["rows"] if r["row"]]
    assert {r["region"] for r in rows} <= set(REGION_COL), {r["region"] for r in rows} - set(REGION_COL)
    pool = {}
    for r in rows:
        if r["household_type"] not in HTYPES:
            skipped["household type has no A23 column"] += 1
        elif not HTYPES[r["household_type"]][1] <= r["age"] <= HTYPES[r["household_type"]][2]:
            skipped["age outside 21-64"] += 1
        elif not r["occupation"] or r["occupation"][:3] not in ons["ashe"] or num(ons["ashe"][r["occupation"][:3]][1][3]) is None:
            skipped["no ASHE occupation median"] += 1
        else:
            pool.setdefault((r["region"], HTYPES[r["household_type"]][0]), []).append(r)
    usable = sum(len(v) for v in pool.values())
    rng = random.Random(SEED)
    regions = list(REGION_COL)
    chosen = []
    for k in range(n):
        reg, lap = regions[k % len(regions)], k // len(regions)
        for off in range(len(KEYS)):
            key = KEYS[(lap + off) % len(KEYS)]
            cell = pool.get((reg, key), [])
            if cell:
                chosen.append((key, cell.pop(rng.randrange(len(cell)))))
                break
        else:
            raise AssertionError(f"no usable persona left in {reg}")
    return chosen, skipped, usable


def net_monthly(gross, region="England"):
    # ponytail: 2025/26 income tax (Scottish bands for region Scotland, else rest-of-UK) and UK-wide employee NI; no pension,
    # student loan, tax code or personal-allowance taper. The statements fall in 2026/27, whose Scottish starter and basic
    # thresholds are higher. Ceiling: a payslip. Upgrade: per-persona tax code and the 2026/27 table.
    pa, basic = 12570, 50270
    if region == "Scotland":
        lo, tax = 0, 0.0
        for hi, rate in SCOT_BANDS:
            tax += rate * max(0, min(gross, hi) - lo)
            lo = hi
    else:
        tax = 0.2 * max(0, min(gross, basic) - pa) + 0.4 * max(0, min(gross, 125140) - basic)
    ni = 0.08 * max(0, min(gross, basic) - pa) + 0.02 * max(0, gross - basic)
    return round((gross - tax - ni) / 12, 2)


def decile(gross, ons):
    """Gross income decile (1 to 10) of a weekly gross income of gross/52, from the A4 lower boundaries."""
    bounds = [num(ons["a4"][A4_BOUND_ROW - 1][A4_DEC0 + k]) for k in range(1, 10)]
    assert all(b is not None for b in bounds)
    return 1 + sum(gross / 52 >= b for b in bounds)


def decile_ratio(dec, ons):
    """Category -> (this decile's weekly spending) / (all households), from A4. A suppressed category ('..': health,
    education) uses the ratio of total expenditure instead."""
    a4 = ons["a4"]
    tot = num(a4[A4_TOTAL_ROW - 1][A4_DEC0 + dec - 1]) / num(a4[A4_TOTAL_ROW - 1][A4_ALL])
    out = {}
    for c, r in CAT_A4.items():
        x, allh = num(a4[r - 1][A4_DEC0 + dec - 1]), num(a4[r - 1][A4_ALL])
        out[c] = x / allh if x is not None and allh else tot
    return out


def sample_tenure(age, ons, rng):
    """Tenure from EHS FA1201 (England, 2024-25) shares within the persona's age band, mortgagors removed and the other
    three shares renormalised (the mortgage payment is not in the ONS data without pooling; see spend_model)."""
    col = 1 + next(i for i, (lo, hi) in enumerate(EHS_BANDS) if lo <= age <= hi)
    w = {t: float(ons["ehs"].iloc[EHS_ROWS[t], col]) for t in EHS_ROWS if t != "Mortgage"}
    return rng.choices(list(w), weights=list(w.values()))[0]


def payday(y, m):
    d = dt.date(y, m, 28)
    return d - dt.timedelta(days=max(0, d.weekday() - 4))  # Saturday or Sunday -> Friday


def spend_model(key, tenure, region, ons, dec):
    """Weekly GBP per category pool (everyday card spending) and per regular debit, for the persona's share of the household."""
    col, persons, adults = A23_COLS[key]
    assert ons["a23"][18][col] == persons, "A23 column does not match the household composition"
    rc = REGION_COL[region][0]
    d = lambda k: num(ons["a35"][A35[k][0] - 1][rc]) or 0.0
    cat = {}
    for c in range(1, 13):
        sco = num(ons["a33"][CAT_A33[c] - 1][rc])
        assert sco is not None, (region, c)  # a suppressed regional category would need a fallback; none is used
        h, allh = num(ons["a23"][CAT_A23[c] - 1][col]), num(ons["a4"][CAT_A4[c] - 1][A4_ALL])
        cat[c] = (sco, h / allh if h is not None and allh else 1.0)  # suppressed cell ('..'): regional average, unscaled
    # ponytail: regional level x (household type / all households, A23) x (income decile / all households, A4); the decile
    # comes from the persona's own salary alone (a partner's income is not modelled), the account pays an equal share of the
    # household's spending, and the two ratios overlap (couples are richer), so some spending is double-counted.
    # Ceiling: averages, not this person. Rent, energy and water, and council tax are not decile-scaled.
    share = 1 / adults
    dr = decile_ratio(dec, ons)
    f = lambda c: cat[c][1] * dr[c]
    reg = {"energy": (d("energy") + d("water")) * share,
           # ponytail: ONS 13.1 pools council tax with mortgage interest, averaged over all households in the region
           "council_tax": d("council_tax") * share,
           "phone": (d("tel") + d("internet") + d("combined_tel")) * f(8) * share,
           "tv": d("tv") * f(9) * share, "sports": d("sports") * f(9) * share}
    if tenure != "Owned outright":
        # ponytail: rent = UK net housing cost (A32, category 4) for the tenure less regional maintenance, water and energy;
        # mixes UK and regional figures. Mortgagors are not modelled: ONS excludes mortgage interest from category 4 and pools
        # it with council tax in 13.1, so a payment cannot be separated from the regional council-tax figure without inventing one.
        reg["rent"] = max(0.0, num(ons["a32"][A32_ROW - 1][A32_TENURE[tenure]]) - d("maint") - d("water") - d("energy")) * share
    pool = {c: cat[c][0] * f(c) * share for c in range(1, 13)}
    pool[8] = max(0.0, pool[8] - reg["phone"])
    pool[9] = max(0.0, pool[9] - reg["tv"] - reg["sports"])  # package holidays (9.6) stay excluded: lumpy
    pool[7] = max(0.0, pool[7] - d("veh_purchase") * f(7) * share)  # vehicle purchases (7.1) excluded: lumpy
    pool[12] += pool.pop(10) + pool.pop(8)  # education and leftover communications fold into miscellaneous
    return pool, reg


RAIL = {"Scotland": "SCOTRAIL", "Wales": "TRANSPORT FOR WALES", "Northern Ireland": "TRANSLINK", "North East": "NORTHERN RAIL",
        "North West": "NORTHERN RAIL", "Yorkshire and The Humber": "NORTHERN RAIL", "East Midlands": "EAST MIDLANDS RAILWAY",
        "West Midlands": "WEST MIDLANDS RAILWAY", "East of England": "GREATER ANGLIA", "London": "TFL TRAVEL CHARGE",
        "South East": "SOUTHEASTERN", "South West": "GREAT WESTERN RAILWAY"}
MERCH = {1: (["TESCO STORES", "SAINSBURYS S/MKTS", "ASDA SUPERSTORE", "ALDI STORES", "CO-OP FOOD"], 12),
         2: (["TESCO STORES", "MORRISONS", "CENTRAL OFF LICENCE"], 4),
         3: (["PRIMARK", "NEXT RETAIL", "H&M", "SPORTS DIRECT"], 2),
         5: (["B&Q", "IKEA", "ARGOS", "HOME BARGAINS"], 2),
         6: (["BOOTS", "WELL PHARMACY"], 2),
         7: (["BP", "SHELL", "ESSO", "@RAIL@", "RINGGO PARKING", "NATIONAL EXPRESS"], 8),
         9: (["AMAZON", "STEAM GAMES", "CINEWORLD", "WATERSTONES", "PETS AT HOME"], 5),
         11: (["COSTA COFFEE", "GREGGS", "PIZZA EXPRESS", "DELIVEROO", "NANDOS", "WETHERSPOON"], 6),
         12: (["SUPERDRUG", "BARBERS", "ROYAL MAIL", "CURRYS"], 4)}
CLUBS = ["Celtic", "Rangers", "Hearts", "Hibernian", "Aberdeen", "Dundee United", "Dundee", "Motherwell", "St Mirren",
         "Kilmarnock", "Partick Thistle", "Raith Rovers", "Arsenal", "Chelsea", "Tottenham", "Liverpool", "Everton",
         "Manchester United", "Manchester City", "Newcastle", "Sunderland", "Leeds", "Sheffield", "Aston Villa", "West Ham",
         "Leicester", "Nottingham Forest", "Cardiff City", "Swansea", "Wrexham", "Linfield", "Glentoran", "Brighton", "Norwich"]
GYM = ("gym", "running", "cycling", "swimming", "yoga", "fitness", "hiking", "climbing")


def sports_item(p):
    """Light use of the lifestyle text: club tickets for a supporter, otherwise a gym or leisure membership."""
    t = (p["sports_persona"] + " " + p["hobbies_and_interests_list"]).lower()
    for c in CLUBS:
        if c.lower() in t and ("supporter" in t or "football" in t or "fan" in t):
            return "ticket", f"{c.upper()} FC TICKETS"
    if "football" in t:
        return "ticket", "FOOTBALL TICKETS ONLINE"
    return ("gym", "PUREGYM MEMBERSHIP") if any(g in t for g in GYM) else ("gym", "LEISURE CENTRE MEMBERSHIP")


def pence_split(total, weights):
    """Split total (GBP) into pence amounts proportional to weights, summing exactly to total."""
    p = round(total * 100)
    raw = [p * w / sum(weights) for w in weights]
    out = [int(x) for x in raw]
    for i in sorted(range(len(raw)), key=lambda i: raw[i] - out[i], reverse=True)[: p - sum(out)]:
        out[i] += 1
    return [x / 100 for x in out]


def build(idx, key, p, ons, tenure):
    region = p["region"]
    rng = random.Random(f"{SEED}-{idx}")
    gross = num(ons["ashe"][p["occupation"][:3]][1][3])
    net = net_monthly(gross, region)
    pool, reg = spend_model(key, tenure, region, ons, decile(gross, ons))
    merch = {c: ([m.replace("@RAIL@", RAIL[region]) for m in ms], n) for c, (ms, n) in MERCH.items()}
    town = p["municipality"].upper().replace("CITY OF ", "")[:14]
    skind, sname = sports_item(p)
    tx = []  # (date, type, description, debit, credit)
    for y, m in MONTHS:
        dim = calendar.monthrange(y, m)[1]
        D = lambda day: dt.date(y, m, min(day, dim))
        tx.append((payday(y, m), "BGC", "FAKE EMPLOYER LTD SALARY", 0.0, net))
        if "rent" in reg:
            tx.append((D(1), "SO", "RENT " + ("COUNCIL HOUSING" if tenure == "Social rented" else "LETTING AGENT"),
                       round(reg["rent"] * WK, 2), 0.0))
        tx.append((D(5), "DD", "ENERGY SUPPLIER AND WATER", round(reg["energy"] * WK, 2), 0.0))
        tx.append((D(15), "DD", p["municipality"].upper() + " COUNCIL TAX", round(reg["council_tax"] * WK, 2), 0.0))
        tx.append((D(12), "DD", "MOBILE AND BROADBAND", round(reg["phone"] * WK, 2), 0.0))
        tx.append((D(20), "DD", "STREAMING AND TV SUBSCRIPTION", round(reg["tv"] * WK, 2), 0.0))
        if skind == "gym":
            tx.append((D(3), "DD", sname, round(reg["sports"] * WK, 2), 0.0))
        else:
            for a, day in zip(pence_split(reg["sports"] * WK, [1.0, 1.0]), (8, 22)):
                tx.append((D(day), "DEB", f"{sname} {town} GB", a, 0.0))
        bnpl = {}  # category -> BNPL instalments this month, taken out of that category's card spending
        for name, c, first, step, n, frac in bnpl_plans(idx):
            for k in range(n):
                day = first + dt.timedelta(days=step * k)
                if (day.year, day.month) == (y, m) and day <= END:
                    amt = round(pool[c] * WK * frac, 2)
                    tx.append((day, "DEB", f"{name} {town} GB", amt, 0.0))
                    bnpl[c] = bnpl.get(c, 0.0) + amt
        for c, (merchants, n) in merch.items():
            total = max(0.0, pool[c] * WK * rng.uniform(0.9, 1.1) - bnpl.get(c, 0.0))
            for a in pence_split(total, [rng.lognormvariate(0, 0.6) for _ in range(n)]):
                tx.append((D(rng.randint(1, dim)), "DEB", f"{rng.choice(merchants)} {town} GB", a, 0.0))
    tx = [t for t in tx if t[0] <= END and t[3] + t[4] > 0]
    tx.sort(key=lambda t: (t[0], t[1] != "BGC", t[2], t[3]))
    bal, acct, rows = net, f"{idx + 1:08d}", []  # opening balance: one month's net pay (assumption)
    for d, ty, desc, db, cr in tx:
        bal = round(bal - db + cr, 2)
        rows.append([d.strftime(DATE_FMT), ty, SORT_CODE, acct, desc,
                     f"{db:.2f}" if db else "", f"{cr:.2f}" if cr else "", f"{bal:.2f}"])
    spend = {**{f"cat{c}": v * WK for c, v in pool.items()}, **{k: v * WK for k, v in reg.items()}}
    return rows, gross, net, spend


def generate(out, n=100):
    out.mkdir(parents=True, exist_ok=True)
    for old in list(out.glob("persona*.csv")) + [out / "personas.md"]:
        old.unlink(missing_ok=True)  # generated outputs only; stale files from an earlier N are removed
    ons = load_ons()
    rng = random.Random(SEED + 1)
    chosen, skipped, usable = choose_personas(ons, n)
    summ = []
    for i, (key, p) in enumerate(chosen):
        tenure = sample_tenure(int(p["age"]), ons, rng)
        rows, gross, net, spend = build(i, key, p, ons, tenure)
        name = f"persona{i + 1:03d}_{p['uuid'][:8]}.csv"
        with open(out / name, "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh, lineterminator=LINE_END)
            w.writerow(COLUMNS)
            w.writerows(rows)
        summ.append((name, p, tenure, gross, net, spend, bool(bnpl_plans(i)), rows))
    keys = ["cat1", "cat2", "cat3", "cat5", "cat6", "cat7", "cat9", "cat11", "cat12", "rent", "energy", "council_tax", "phone", "tv", "sports"]
    NL = "\n"
    with open(out / "personas.md", "w", encoding="utf-8", newline=NL) as fh:
        fh.write(f"# Mock-statement personas{NL}{NL}Generated by `mock_statements.py` (seed {SEED}, N = {n}). Personas: {n} chosen from "
                 f"{usable} usable rows of the 500 downloaded, stratified over the 12 regions and four household types; rows skipped: "
                 + ", ".join(f"{v} ({k})" for k, v in skipped.items()) + ". Salary: ONS ASHE Table 14.7a, 2025 revised, "
                 "sheet `All`, median annual gross pay (UK, all employee jobs) for the persona's 3-digit SOC 2020 code; the net monthly "
                 "credit follows a simple income-tax (Scottish bands for Scotland) and NI rule (see the `ponytail` comment in the code). "
                 "Spending: ONS Family Spending, April 2024 to March 2025, workbook 3 column of the persona's own region, scaled by the "
                 "household-type ratio (A23) and the gross-income-decile ratio (A4; decile from the persona's salary alone). Tenure is "
                 "sampled from English Housing Survey 2024-25 table FA1201 by age band (mortgagors excluded, shares renormalised) and "
                 f"is not in the persona data. Merchant names and BNPL plans are synthetic.{NL}{NL}"
                 "| No. | uuid8 | Age | Region | Household type | Occupation | Tenure (sampled) | Gross salary [GBP/yr] | "
                 f"Net monthly pay [GBP] | Modelled monthly spend [GBP] | BNPL | End balance [GBP] |{NL}"
                 f"|---|---|---|---|---|---|---|---|---|---|---|---|{NL}")
        for k, (nm, p, t, g, nt, s, b, rows) in enumerate(summ, 1):
            tot = sum(s.get(x, 0) for x in keys)
            fh.write(f"| {k} | {p['uuid'][:8]} | {p['age']} | {p['region']} | {p['household_type']} | {p['occupation']} | {t} | {g:.0f} | "
                     f"{nt:.2f} | {tot:.0f} | {'yes' if b else 'no'} | {rows[-1][7]} |{NL}")
        fh.write(f"{NL}## Modelled monthly spend by category [GBP/month, expectation]{NL}{NL}"
                 "catN is the ONS category number: 1 food, 2 alcohol and tobacco, 3 clothing, 5 household goods, 6 health, 7 transport "
                 "(vehicle purchase excluded), 9 recreation (package holidays, TV and sports subscriptions removed), 11 restaurants, "
                 "12 miscellaneous (with education and leftover communications). Category 4 housing is replaced by the regular debits "
                 "(rent, energy and water, council tax); maintenance and ONS categories 13 and 14 other than council tax are excluded. "
                 f"BNPL instalments are paid out of the named category's spending, so totals are unchanged.{NL}{NL}")
        fh.write("| No. | " + " | ".join(keys) + f" | Total |{NL}|---|" + "---|" * (len(keys) + 1) + NL)
        for k, (nm, p, t, g, nt, s, b, rows) in enumerate(summ, 1):
            fh.write(f"| {k} | " + " | ".join(f"{s.get(x, 0):.0f}" for x in keys) + f" | {sum(s.get(x, 0) for x in keys):.0f} |{NL}")
    return [s[0] for s in summ], summ


def end_balance(path):
    return list(csv.reader(open(path, encoding="utf-8")))[-1][7]


def check(n=100):
    with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
        names, summ = generate(Path(a), n)
        generate(Path(b), n)
        assert len(names) == n and len(set(names)) == n
        assert len({s[1]["region"] for s in summ}) == min(n, 12)
        for nm in names + ["personas.md"]:
            assert (Path(a) / nm).read_bytes() == (Path(b) / nm).read_bytes(), f"{nm} differs between runs"
        assert sum(s[2] != "Owned outright" for s in summ) >= n / 3, "fewer than a third rent"
        sc = [s for s in summ if s[1]["region"] == "Scotland"]
        assert sc and all(s[4] != net_monthly(s[3]) for s in sc if s[3] > 12570), "Scottish net pay equals rest-of-UK net pay"
        assert all(net_monthly(s[3], s[1]["region"]) == s[4] for s in summ)
        ends = sorted(float(end_balance(Path(a) / nm)) for nm in names)
        print(f"end balances: {sum(e < 0 for e in ends)} overdrawn, min {ends[0]:.2f}, median {ends[len(ends) // 2]:.2f}, max {ends[-1]:.2f}")
        print("tenure:", {t: sum(s[2] == t for s in summ) for t in A32_TENURE})
        bn = 0
        for nm in names:
            rows = list(csv.reader(open(Path(a) / nm, encoding="utf-8")))
            assert rows[0] == COLUMNS
            body = rows[1:]
            assert all(len(r) == 8 for r in body)
            prev = max(float(r[6]) for r in body if r[6])  # opening balance = one month's net pay
            paid = set()
            for r in body:
                assert r[1] in ("DEB", "DD", "SO", "BGC") and (r[5] == "") != (r[6] == "")
                prev = round(prev - float(r[5] or 0) + float(r[6] or 0), 2)
                assert abs(prev - float(r[7])) < 0.005, (nm, r)
                if r[1] == "BGC":
                    paid.add(r[0][3:])
            assert paid == {"08/2026", "09/2026", "10/2026"}, paid
            dates = [dt.datetime.strptime(r[0], DATE_FMT).date() for r in body]
            assert dates == sorted(dates) and dates[-1] <= END
            bn += any("KLARNA" in r[4] or "CLEARPAY" in r[4] or "PAYPAL*" in r[4] for r in body)
        assert abs(bn - n / 3) <= max(1, n * 0.07), f"BNPL personas {bn} of {n}"
    print("self-check passed")


if __name__ == "__main__":
    n = int(sys.argv[sys.argv.index("--n") + 1]) if "--n" in sys.argv else 100
    if "--check" in sys.argv:
        check(n)
    else:
        print("\n".join(generate(OUT, n)[0]))
