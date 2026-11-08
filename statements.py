"""Bank-statement parsing and detection: the part of the old engine kept for the simplified back end (task T29).

Reads a bank-statement CSV (Lloyds Banking Group export layout, as written by mock_statements.py, and as mock_bank.py
rebuilds it from Open Banking data) and detects the regular salary, the next payday, BNPL plans and committed payments
(direct debits, standing orders, recurring same-amount card payments). These are the "infer salary and regular payments"
steps of Andrew's model (model outline/). Standard library only.

Everything else of the old engine (verdict, pay options, card and pot interest, price catalogue, HTTP API, and the
Bayesian spending model it used) was archived on 7 November 2026: archive/affordability.py, archive/bayes.py.

    python statements.py --check     # self-check over every persona CSV
"""
import argparse, calendar, csv, datetime as dt, functools, io, math, re, statistics
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
STATEMENTS = HERE / "Analysis" / "mock_statements"
BANK_RATE = HERE / "data" / "boe_bank_rate_IUDBEDR_2026-11-07.csv"
COLUMNS = ["Transaction Date", "Transaction Type", "Sort Code", "Account Number", "Transaction Description",
           "Debit Amount", "Credit Amount", "Balance"]
BNPL = re.compile(r"KLARNA|CLEARPAY|PAYPAL\s*\*?\s*PAY\s*IN\s*3", re.I)
# ponytail: instalment count and spacing by provider when the statement shows only one instalment (Clearpay: 4 every
# 14 days; Klarna and PayPal Pay in 3: 3 about monthly). Other plans (pay in 30 days, financing) are not recognised;
# upgrade to a provider/plan table or the BNPL provider's API.
BNPL_PLAN = {"CLEARPAY": (4, 14)}
BNPL_DEFAULT = (3, 30)


class StatementError(ValueError):
    """The CSV is not a usable statement; the message says why and where."""


def money(x):
    return round(float(x) + 0.0, 2)


def add_months(d, n, day=None):
    y, m = divmod(d.month - 1 + n, 12)
    y, m = d.year + y, m + 1
    return dt.date(y, m, min(day or d.day, calendar.monthrange(y, m)[1]))


# ---------------------------------------------------------------- parsing (untrusted input)
def parse(text):
    """CSV text -> list of dicts (date, type, desc, debit, credit, balance), oldest first. Raises StatementError."""
    if not isinstance(text, str) or not text.strip():
        raise StatementError("The statement is empty.")
    try:
        rows = list(csv.reader(io.StringIO(text.lstrip("﻿")), strict=True))
    except csv.Error as e:
        raise StatementError(f"Invalid CSV: {e}.") from None
    if not rows:
        raise StatementError("The statement is empty.")
    head = [h.strip() for h in rows[0]]
    if head != COLUMNS:
        raise StatementError(f"Header must be exactly: {', '.join(COLUMNS)}; got: {', '.join(head)}.")
    tx = []
    for n, r in enumerate(rows[1:], start=2):
        if not any(c.strip() for c in r):
            continue
        if len(r) != len(COLUMNS):
            raise StatementError(f"Line {n}: expected {len(COLUMNS)} fields, found {len(r)}.")
        try:
            d = dt.datetime.strptime(r[0].strip(), "%d/%m/%Y").date()
        except ValueError:
            raise StatementError(f"Line {n}: date {r[0]!r} is not DD/MM/YYYY.") from None
        try:
            db, cr, bal = (float(x.replace(",", "")) if x.strip() else None for x in (r[5], r[6], r[7]))
        except ValueError:
            raise StatementError(f"Line {n}: an amount is not a number ({r[5]!r}, {r[6]!r}, {r[7]!r}).") from None
        if any(x is not None and not math.isfinite(x) for x in (db, cr, bal)):
            raise StatementError(f"Line {n}: amounts and balance must be finite numbers.")
        if (db is None) == (cr is None) or (db if db is not None else cr) < 0 or bal is None:
            raise StatementError(f"Line {n}: needs exactly one non-negative debit or credit amount, and a balance.")
        tx.append(dict(date=d, type=r[1].strip().upper(), desc=r[4].strip(), debit=db or 0.0, credit=cr or 0.0,
                       balance=bal))
    if not tx:
        raise StatementError("The statement has a header but no transactions.")
    if tx[0]["date"] > tx[-1]["date"]:
        tx.reverse()  # bank downloads are often newest first
    if any(a["date"] > b["date"] for a, b in zip(tx, tx[1:])):
        raise StatementError("Transaction dates are not in date order.")
    return tx


# ---------------------------------------------------------------- detection
def detect_income(tx):
    """Regular salary: the credit description seen in the most calendar months (at least 2), preferring BGC.
    monthly = its latest amount; nominal payday = its most common day of the month (ties: latest), paid on the previous
    Friday when that day is a weekend."""
    groups = defaultdict(list)
    for t in tx:
        if t["credit"] > 0:
            groups[t["desc"]].append(t)
    best = max(groups.values(), default=[],
               key=lambda g: (len({(t["date"].year, t["date"].month) for t in g}), g[0]["type"] == "BGC", len(g)))
    if len({(t["date"].year, t["date"].month) for t in best}) < 2:
        return None
    days = [t["date"].day for t in best]
    day = max(set(days), key=lambda x: (days.count(x), x))
    return dict(name=best[-1]["desc"], monthly=money(best[-1]["credit"]), day=day, lastPaid=best[-1]["date"])


def next_payday(income, after):
    """First predicted payday strictly after `after`. ponytail: weekends only; UK bank holidays are ignored."""
    for k in range(0, 3):
        d = add_months(after, k, income["day"])
        d -= dt.timedelta(days=max(0, d.weekday() - 4))
        if d > after:
            return d
    raise AssertionError("unreachable")


def detect_bnpl(tx):
    """BNPL plans: card rows whose description matches BNPL, grouped by description. Instalment count and spacing come
    from the provider (BNPL_PLAN); the spacing is the median observed gap when two or more instalments are visible.
    remaining = count - instalments seen (an instalment taken before the statement started is missed, which overstates
    remaining). Inconsistent amounts/cadence or more than one plan's worth of payments make the description ambiguous:
    remaining is None and schedule is empty (unknown, not debt-free)."""
    groups = defaultdict(list)
    for t in tx:
        if t["debit"] > 0 and BNPL.search(t["desc"]):
            groups[t["desc"]].append(t)
    plans = []
    for desc, g in groups.items():
        count, gap = next((v for k, v in BNPL_PLAN.items() if k in desc.upper()), BNPL_DEFAULT)
        dates = [t["date"] for t in g]
        gaps = [(b - a).days for a, b in zip(dates, dates[1:])]
        # ponytail: a CSV has no provider plan IDs. Accept only one consistent plan per description; otherwise require
        # confirmation instead of guessing how to partition debts. Upgrade to provider-confirmed plan schedules.
        ambiguous = (len(g) > count or any(abs(t["debit"] - g[-1]["debit"]) > 0.011 for t in g)
                     or any(abs(d - gap) > 3 for d in gaps))
        if ambiguous:
            plans.append(dict(name=desc, provider=BNPL.search(desc).group(0).upper(), instalment=None,
                              paid=len(g), remaining=None, schedule=[], uncertain=True,
                              note="Payments cannot be assigned to one BNPL plan; confirm outstanding instalments."))
            continue
        if len(dates) > 1:
            gap = statistics.median(gaps)
        left = max(0, count - len(g))
        due = [dates[-1] + dt.timedelta(days=gap * i) for i in range(1, left + 1)]
        plans.append(dict(name=desc, provider=BNPL.search(desc).group(0).upper(), instalment=money(g[-1]["debit"]),
                          paid=len(g), remaining=left, uncertain=False,
                          schedule=[dict(due=d.isoformat(), amount=money(g[-1]["debit"]))
                                                                 for d in due]))
    return plans


def detect_committed(tx, as_of):
    """Committed outgoings, one entry per payment expected in the month after asOf:
    - every direct debit (DD) and standing order (SO) description last seen within 35 days of asOf;
    - every card payment (not BNPL) with the same description and amount, the same number of times, in at least three
      calendar months, and last seen within 35 days of asOf (two months gave coincidental grocery matches).
    Each occurrence in the group's latest month repeats monthly on the same day; due = the first such date after asOf;
    amount = that occurrence's amount. ponytail: annual or irregular debits are treated as monthly, and card
    subscriptions younger than three months are missed; upgrade with a longer statement and a per-group cadence."""
    groups = defaultdict(list)
    for t in tx:
        if t["debit"] <= 0 or BNPL.search(t["desc"]):
            continue
        if t["type"] in ("DD", "SO"):
            groups[(t["type"], t["desc"])].append(t)
        else:
            groups[(t["type"], t["desc"], t["debit"])].append(t)
    out = []
    for key, g in groups.items():
        last = g[-1]["date"]
        per = defaultdict(int)
        for t in g:
            per[(t["date"].year, t["date"].month)] += 1
        if (as_of - last).days > 35 or key[0] not in ("DD", "SO") and (len(per) < 3 or len(set(per.values())) > 1):
            continue
        for t in (t for t in g if (t["date"].year, t["date"].month) == (last.year, last.month)):
            due = next(d for k in range(1, 4) if (d := add_months(t["date"], k, t["date"].day)) > as_of)
            out.append(dict(name=t["desc"], type=t["type"], amount=money(t["debit"]), due=due.isoformat()))
    return sorted(out, key=lambda c: (c["due"], c["name"]))


@functools.cache
def bank_rate():
    """[(date, Bank Rate in % a year)], oldest first, from the Bank of England CSV (DATE as '05 Nov 2026')."""
    with open(BANK_RATE, encoding="utf-8", newline="") as f:
        rows = list(csv.reader(f))[1:]
    return [(dt.datetime.strptime(d, "%d %b %Y").date(), float(v)) for d, v in rows if d.strip() and v.strip()]


def personas():
    """Persona ids and details from personas.md, matched to the CSV files present."""
    info = {}
    md = STATEMENTS / "personas.md"
    if md.exists():
        for line in md.read_text(encoding="utf-8").splitlines():
            c = [x.strip() for x in line.strip().strip("|").split("|")]
            if len(c) >= 7 and c[0].isdigit() and re.fullmatch(r"[0-9a-f]{8}", c[1]):  # persona table only
                info[f"persona{int(c[0]):03d}"] = dict(age=c[2], region=c[3], household=c[4], occupation=c[5],
                                                       tenure=c[6])
    out = []
    for f in sorted(STATEMENTS.glob("persona[0-9][0-9][0-9]_*.csv")):
        pid = f.name[:10]
        out.append(dict(id=pid, file=f.name, **info.get(pid, dict(region="unknown", household="unknown",
                                                                  occupation="unknown"))))
    return out


def load_persona(pid):
    if not isinstance(pid, str) or not re.fullmatch(r"persona\d{3}", pid):
        raise StatementError("persona must look like 'persona079'.")
    files = list(STATEMENTS.glob(f"{pid}_*.csv"))
    if len(files) != 1:
        raise StatementError(f"No statement for {pid}.")
    return files[0].read_text(encoding="utf-8")


# ---------------------------------------------------------------- self-check
def check():
    files = sorted(STATEMENTS.glob("persona[0-9][0-9][0-9]_*.csv"))
    assert files, f"no persona CSVs in {STATEMENTS}"
    for f in files:  # salary, committed payments, BNPL and payday against what the generator wrote
        text = f.read_text(encoding="utf-8")
        tx, rows = parse(text), list(csv.reader(io.StringIO(text)))[1:]
        last = tx[-1]["date"]
        income = detect_income(tx)
        assert income and {income["monthly"]} == {float(r[6]) for r in rows if r[1] == "BGC"}, (f.name, income)
        due_dd_so = {(r[4], float(r[5])) for r in rows if r[1] in ("DD", "SO")
                     and dt.datetime.strptime(r[0], "%d/%m/%Y").date().replace(day=1) == last.replace(day=1)}
        assert due_dd_so <= {(c["name"], c["amount"]) for c in detect_committed(tx, last)}, f.name
        assert bool(detect_bnpl(tx)) == any(BNPL.search(r[4]) for r in rows), f.name
        pay = next_payday(income, last)
        assert last < pay <= last + dt.timedelta(days=35) and pay.weekday() < 5, (f.name, pay)
    assert load_persona(files[0].name[:10]) == files[0].read_text(encoding="utf-8")
    assert len(personas()) == len(files) and all(p["region"] != "unknown" for p in personas())

    rows = [dict(date=dt.date(2026, m, d), type="DEB", desc="KLARNA", debit=50.0, credit=0.0, balance=1000.0)
            for m, d in ((8, 10), (9, 10), (10, 10), (10, 20))]
    assert detect_bnpl(rows[:3])[0]["remaining"] == 0  # a consistent completed plan is still recognised
    for group in (rows, rows[-2:], [rows[0], dict(rows[1], debit=100.0)]):  # ambiguous: unknown, not debt-free
        plan = detect_bnpl(group)[0]
        assert plan["uncertain"] and plan["remaining"] is None and plan["instalment"] is None
    assert [p["remaining"] for p in detect_bnpl(rows[:3] + [dict(rows[-1], desc="KLARNA NEW ORDER")])] == [0, 2]

    header = ",".join(COLUMNS) + "\n"
    for db, cr in (("0", ""), ("", "0")):
        zero = parse(header + f"01/11/2026,DEB,0,0,SHOP,{db},{cr},-10\n")
        assert zero[0]["debit"] == zero[0]["credit"] == 0 and zero[0]["balance"] == -10
    malformed = ["", "a,b\n1,2\n", header, "﻿", header + '"unfinished', header + "01/11/2026,DEB,0,0,SHOP,-1,,5\n",
                 header + "31/02/2026,DEB,0,0,X,1.00,,5.00\n", header + "01/02/2026,DEB,0,0,X,1.00,2.00,5.00\n",
                 header + "01/02/2026,DEB,0,0,X,abc,,5.00\n",
                 header + "01/02/2026,DEB,0,0,X,1.00,,5.00\n03/02/2026,DEB,0,0,X,1.00,,4.00\n02/02/2026,DEB,0,0,X,1,,3\n"]
    for value in ("NaN", "Infinity", "-Infinity", "1e309"):
        for column in (5, 6, 7):
            row = ["01/11/2026", "DEB", "0", "0", "SHOP", "1", "", "5"]
            if column == 6:
                row[5] = ""
            row[column] = value
            malformed.append(header + ",".join(row) + "\n")
    for bad in malformed:
        try:
            parse(bad)
        except StatementError as e:
            assert str(e)
        else:
            raise AssertionError(f"accepted malformed CSV {bad!r}")
    assert bank_rate()[-1][0] >= dt.date(2026, 10, 1) and all(0 <= r < 20 for _, r in bank_rate())
    print(f"statements.py self-check passed on {len(files)} statements.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true", help="run the self-check")
    if ap.parse_args().check:
        check()
    else:
        ap.print_help()
