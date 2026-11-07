"""Affordability engine and local HTTP API for the checkout extension (task T07).

Reads a bank-statement CSV (Lloyds Banking Group export layout, as written by mock_statements.py) and answers, for a
purchase at price P: what is safe to spend before the next payday, and the facts of each way to pay (pay now, BNPL with a
set-aside pot, plain BNPL, a 0% card). Guidance, not advice: options are described and marked cheapest / most left until
payday, never recommended.

    python affordability.py --serve [--port 8765]   # JSON API on 127.0.0.1
    python affordability.py --check                 # self-check over every persona CSV
Standard library only.
"""
import argparse, calendar, csv, datetime as dt, io, json, re, statistics, sys, threading, urllib.request
from collections import defaultdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
STATEMENTS = HERE / "Analysis" / "mock_statements"
COLUMNS = ["Transaction Date", "Transaction Type", "Sort Code", "Account Number", "Transaction Description",
           "Debit Amount", "Credit Amount", "Balance"]
MAX_BODY = 2_000_000  # bytes; a three-month statement is about 20 kB
BNPL = re.compile(r"KLARNA|CLEARPAY|PAYPAL\s*\*?\s*PAY\s*IN\s*3", re.I)
# ponytail: instalment count and spacing by provider when the statement shows only one instalment (Clearpay: 4 every
# 14 days; Klarna and PayPal Pay in 3: 3 about monthly). Other plans (pay in 30 days, financing) are not recognised;
# upgrade to a provider/plan table or the BNPL provider's API.
BNPL_PLAN = {"CLEARPAY": (4, 14)}
BNPL_DEFAULT = (3, 30)
# UK sale events (dates as given by Harrison's brief to T07; no price statistics are claimed).
SALES = [(dt.date(2026, 11, 27), "Black Friday"), (dt.date(2026, 11, 30), "Cyber Monday"),
         (dt.date(2026, 12, 26), "Boxing Day and the January sales")]
SALE_TEXT = ("Sale prices are not always lower than the prices charged earlier in the year; the item's price history "
             "shows whether a sale price is a real reduction.")
SAFE_DEF = ("safeToSpend = balance (after the statement's last transaction, on asOf) minus every committed payment "
            "(recurring direct debit, standing order or same-amount card payment) and every BNPL instalment predicted "
            "after asOf and before nextPayday. Everyday spending such as food, and any card spending between asOf and today, is not deducted.")


class StatementError(ValueError):
    """The CSV is not a usable statement; the message says why and where."""


def money(x):
    return round(x + 0.0, 2)


def add_months(d, n, day=None):
    y, m = divmod(d.month - 1 + n, 12)
    y, m = d.year + y, m + 1
    return dt.date(y, m, min(day or d.day, calendar.monthrange(y, m)[1]))


# ---------------------------------------------------------------- parsing (untrusted input)
def parse(text):
    """CSV text -> list of dicts (date, type, desc, debit, credit, balance), oldest first. Raises StatementError."""
    if not isinstance(text, str) or not text.strip():
        raise StatementError("The statement is empty.")
    rows = list(csv.reader(io.StringIO(text.lstrip("﻿"))))
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
        if (db is None) == (cr is None) or (db or cr) < 0 or bal is None:
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
    remaining)."""
    groups = defaultdict(list)
    for t in tx:
        if t["debit"] > 0 and BNPL.search(t["desc"]):
            groups[t["desc"]].append(t)
    plans = []
    for desc, g in groups.items():
        count, gap = next((v for k, v in BNPL_PLAN.items() if k in desc.upper()), BNPL_DEFAULT)
        dates = [t["date"] for t in g]
        if len(dates) > 1:
            gap = statistics.median((b - a).days for a, b in zip(dates, dates[1:]))
        left = max(0, count - len(g))
        due = [dates[-1] + dt.timedelta(days=gap * i) for i in range(1, left + 1)]
        plans.append(dict(name=desc, provider=BNPL.search(desc).group(0).upper(), instalment=money(g[-1]["debit"]),
                          paid=len(g), remaining=left, schedule=[dict(due=d.isoformat(), amount=money(g[-1]["debit"]))
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


def card_spend(tx, committed):
    """Monthly everyday card spending: DEB rows that are neither BNPL nor committed, per calendar month that the
    statement covers (first transaction on or before day 7, last on or after day 24; ponytail: rough coverage rule)."""
    fixed = {(c["name"], c["amount"]) for c in committed}
    first, last, per = tx[0]["date"], tx[-1]["date"], defaultdict(float)
    for t in tx:
        if t["type"] == "DEB" and t["debit"] > 0 and not BNPL.search(t["desc"]) and (t["desc"], t["debit"]) not in fixed:
            per[(t["date"].year, t["date"].month)] += t["debit"]
    full = [v for (y, m), v in per.items()
            if not ((y, m) == (first.year, first.month) and first.day > 7)
            and not ((y, m) == (last.year, last.month) and last.day < 24)]
    return full


# ---------------------------------------------------------------- assessment
def assess(tx, price, today=None, merchant=None):
    if not isinstance(price, (int, float)) or isinstance(price, bool) or not 0 < price < 1e7:
        raise StatementError("price must be a number of pounds greater than 0.")
    as_of, balance = tx[-1]["date"], money(tx[-1]["balance"])
    today = today or as_of + dt.timedelta(days=1)
    if today <= as_of:
        raise StatementError(f"today ({today}) must be after the statement's last transaction ({as_of}).")
    income = detect_income(tx)
    payday = next_payday(income, as_of) if income else None
    if payday and payday < today:
        raise StatementError(f"A payday ({payday}) has passed since the statement's last transaction ({as_of}); "
                             "use a newer statement.")
    horizon = payday or add_months(as_of, 1)  # no salary detected: look one month ahead
    committed = detect_committed(tx, as_of)
    plans = detect_bnpl(tx)
    before = lambda d: as_of < dt.date.fromisoformat(d) < horizon
    committed_due = money(sum(c["amount"] for c in committed if before(c["due"])))
    bnpl_due = money(sum(s["amount"] for p in plans for s in p["schedule"] if before(s["due"])))
    safe = money(balance - committed_due - bnpl_due)

    # Monthly view: one month after asOf.
    month_end = add_months(as_of, 1)
    spend = card_spend(tx, committed)
    monthly = dict(
        income=income["monthly"] if income else 0.0,
        committed=money(sum(c["amount"] for c in committed)),
        bnpl=money(sum(s["amount"] for p in plans for s in p["schedule"]
                       if as_of < dt.date.fromisoformat(s["due"]) <= month_end)),
        typicalCardSpending=money(statistics.median(spend)) if spend else 0.0,
        monthsUsed=len(spend))
    monthly["afterCommitted"] = money(monthly["income"] - monthly["committed"] - monthly["bnpl"])
    monthly["leftOver"] = money(monthly["afterCommitted"] - monthly["typicalCardSpending"])
    monthly["definition"] = ("afterCommitted = income (latest salary credit) - committed (one month of recurring "
                             "payments) - bnpl (existing BNPL instalments due in the month after asOf); leftOver = "
                             "afterCommitted - typicalCardSpending (median monthly everyday card spending over the full "
                             "months in the statement, excluding BNPL and committed card payments).")

    # Payment options: facts only. cost = extra cost over the price, if every payment is made on time.
    days_left = (horizon - today).days
    daily = monthly["typicalCardSpending"] / 30.44
    left_now = money(safe - price)
    third = money(price / 3)
    sched = [dict(due=add_months(today, i).isoformat(), amount=money(price - 2 * third) if i == 0 else third)
             for i in range(3)]
    due_now = money(sum(s["amount"] for s in sched if dt.date.fromisoformat(s["due"]) < horizon))
    left_plain = money(safe - due_now)
    spend_note = (f"Typical everyday card spending over the {days_left} days to "
                  f"{'payday' if payday else 'the same date next month'} is about £{daily * days_left:,.0f} "
                  "and is not deducted here.")
    options = [
        dict(kind="payNow", label="Pay now", affordable=left_now >= 0, leftAfter=left_now, cost=0.0,
             notes=[f"£{price:,.2f} leaves the account today.", spend_note]),
        dict(kind="bnplPot", label="Pay in 3, with the full price set aside in a pot", affordable=left_now >= 0,
             leftAfter=left_now, cost=0.0, schedule=sched,
             notes=["The full price moves into an easy-access cash pot now and each instalment is paid from it, so the "
                    "instalments are always covered.",
                    "The pot takes the same money as paying now, so it is affordable exactly when paying now is.",
                    "Any interest earned on the pot depends on its rate and is not counted here.", spend_note]),
        dict(kind="bnplPlain", label="Pay in 3, without a pot", affordable=left_plain >= 0
             and monthly["afterCommitted"] - third >= 0, leftAfter=left_plain, cost=0.0, schedule=sched,
             notes=[f"£{due_now:,.2f} is due before {'payday' if payday else 'the same date next month'}; the later "
                    "instalments come from future income.",
                    f"Each later instalment is £{third:,.2f}. A month's income less committed payments and existing "
                    f"BNPL is £{monthly['afterCommitted']:,.2f}; after typical everyday spending it is "
                    f"£{monthly['leftOver']:,.2f}.",
                    "A missed instalment can bring a late fee from the provider.", spend_note]),
        dict(kind="card0", label="0% purchase credit card", affordable=None, leftAfter=None, cost=None,
             notes=["We have no data on your cards: this depends on whether you hold a card with a 0% purchase "
                    "period, its limit and how long the period lasts.",
                    "Interest is charged on any balance left when the 0% period ends.",
                    "Minimum payments are still due each month."]),
    ]
    ok = [o for o in options if o["affordable"]]
    cheapest = [o["kind"] for o in ok if o["cost"] == min(x["cost"] for x in ok)] if ok else []
    most = [o["kind"] for o in ok if o["leftAfter"] == max(x["leftAfter"] for x in ok)] if ok else []

    sale = next(((d, n) for d, n in SALES if 0 <= (d - today).days <= 60), None)
    return dict(
        asOf=as_of.isoformat(), today=today.isoformat(), price=money(price), merchant=merchant,
        income=dict(name=income["name"], monthly=income["monthly"], nextPayday=payday.isoformat(),
                    lastPaid=income["lastPaid"].isoformat()) if income else None,
        committed=committed, committedDueBeforePayday=committed_due,
        bnplPlans=plans, bnplActive=[p for p in plans if p["remaining"]], bnplDueBeforePayday=bnpl_due,
        balance=balance, safeToSpend=safe, safeToSpendDefinition=SAFE_DEF + ("" if payday else
                                                                              " No salary was detected, so the window is one month after asOf."),
        monthly=monthly, options=options, cheapest=cheapest, mostLeftUntilPayday=most,
        saleNote=dict(event=sale[1], date=sale[0].isoformat(), daysToGo=(sale[0] - today).days, note=SALE_TEXT)
        if sale else None,
        betterPrice=None,  # ponytail: no price catalogue yet (T09, awaiting Harrison's decision); fill from it when ready
    )


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


# ---------------------------------------------------------------- HTTP API
class Handler(BaseHTTPRequestHandler):
    def send(self, code, obj):
        body = json.dumps(obj, indent=1).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.cors()
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):  # CORS preflight from the extension
        self.send_response(204)
        self.cors()
        self.end_headers()

    def cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def do_GET(self):
        if self.path == "/health":
            return self.send(200, dict(status="ok"))
        if self.path == "/personas":
            return self.send(200, personas())
        self.send(404, dict(error=f"Unknown path {self.path}; use /health, /personas or POST /assess."))

    def do_POST(self):
        if self.path != "/assess":
            return self.send(404, dict(error="Unknown path; POST /assess."))
        try:
            size = self.headers.get("Content-Length", "")
            size = int(size) if size.isdigit() else 0
            if not 0 < size <= MAX_BODY:
                raise StatementError(f"Send a JSON body of at most {MAX_BODY} bytes.")
            try:
                req = json.loads(self.rfile.read(size))
            except (json.JSONDecodeError, UnicodeDecodeError):
                raise StatementError("The body is not valid JSON.") from None
            if not isinstance(req, dict) or ("persona" in req) == ("csv" in req):
                raise StatementError('Send an object with exactly one of "persona" or "csv", plus "price".')
            text = load_persona(req["persona"]) if "persona" in req else req["csv"]
            try:
                today = dt.date.fromisoformat(req["today"]) if req.get("today") else None
            except (TypeError, ValueError):
                raise StatementError("today must be YYYY-MM-DD.") from None
            merchant = req.get("merchant")
            if merchant is not None and not isinstance(merchant, str):
                raise StatementError("merchant must be a string.")
            out = assess(parse(text), req.get("price"), today, merchant)
            out["persona"] = req.get("persona")
            self.send(200, out)
        except StatementError as e:
            self.send(400, dict(error=str(e)))
        except Exception as e:  # never leave the extension hanging
            self.send(500, dict(error=f"Internal error: {type(e).__name__}: {e}"))

    def log_message(self, *a):
        pass  # keep the console quiet; errors are returned to the caller


def serve(port, quiet=False):
    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    if not quiet:
        print(f"Affordability API on http://127.0.0.1:{srv.server_port} (Ctrl+C to stop)")
    return srv


# ---------------------------------------------------------------- self-check
def check():
    files = sorted(STATEMENTS.glob("persona[0-9][0-9][0-9]_*.csv"))
    assert files, f"no persona CSVs in {STATEMENTS}"
    prices, tally = (50, 300, 1200), {p: [0, 0, 0] for p in (50, 300, 1200)}
    for f in files:
        text = f.read_text(encoding="utf-8")
        tx = parse(text)
        rows = list(csv.reader(io.StringIO(text)))[1:]
        bgc = {float(r[6]) for r in rows if r[1] == "BGC"}
        has_bnpl = any(BNPL.search(r[4]) for r in rows)
        last = tx[-1]["date"]
        last_month = {(r[4], float(r[5])) for r in rows if r[1] in ("DD", "SO")
                      and dt.datetime.strptime(r[0], "%d/%m/%Y").date().replace(day=1) == last.replace(day=1)}
        for p in prices:
            a = assess(tx, p)
            assert a["income"] and {a["income"]["monthly"]} == bgc, (f.name, a["income"], bgc)
            assert last_month <= {(c["name"], c["amount"]) for c in a["committed"]}, f.name
            assert bool(a["bnplPlans"]) == has_bnpl, f.name
            pay = dt.date.fromisoformat(a["income"]["nextPayday"])
            assert last < pay <= last + dt.timedelta(days=35) and pay.weekday() < 5, (f.name, pay)
            due = sum(c["amount"] for c in a["committed"] if dt.date.fromisoformat(c["due"]) < pay) + sum(
                s["amount"] for b in a["bnplPlans"] for s in b["schedule"] if dt.date.fromisoformat(s["due"]) < pay)
            assert abs(a["safeToSpend"] - (float(rows[-1][7]) - due)) < 0.005, f.name
            o = {x["kind"]: x for x in a["options"]}
            assert sum(s["amount"] for s in o["bnplPot"]["schedule"]) == p or abs(
                sum(s["amount"] for s in o["bnplPot"]["schedule"]) - p) < 0.005
            assert o["payNow"]["affordable"] == o["bnplPot"]["affordable"] == (a["safeToSpend"] >= p)
            tally[p][0 if o["payNow"]["affordable"] else 1 if o["bnplPlain"]["affordable"] else 2] += 1
    bad = ["", "a,b\n1,2\n", ",".join(COLUMNS) + "\n",
           ",".join(COLUMNS) + "\n31/02/2026,DEB,0,0,X,1.00,,5.00\n",
           ",".join(COLUMNS) + "\n01/02/2026,DEB,0,0,X,1.00,2.00,5.00\n",
           ",".join(COLUMNS) + "\n01/02/2026,DEB,0,0,X,abc,,5.00\n",
           ",".join(COLUMNS) + "\n01/02/2026,DEB,0,0,X,1.00,,5.00\n03/02/2026,DEB,0,0,X,1.00,,4.00\n02/02/2026,DEB,0,0,X,1,,3\n"]
    for b in bad:
        try:
            parse(b)
        except StatementError as e:
            assert str(e)
        else:
            raise AssertionError(f"accepted malformed CSV {b!r}")
    a = assess(parse(files[0].read_text(encoding="utf-8")), 300, dt.date(2026, 11, 7))
    assert a["saleNote"] and a["saleNote"]["event"] == "Black Friday" and a["saleNote"]["daysToGo"] == 20
    assert a["betterPrice"] is None

    srv = serve(0, quiet=True)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{srv.server_port}"
    post = lambda body: urllib.request.urlopen(urllib.request.Request(url + "/assess", data=body,
                                                                      headers={"Content-Type": "application/json"}))
    try:
        with urllib.request.urlopen(url + "/health") as r:
            assert json.load(r) == {"status": "ok"} and r.headers["Access-Control-Allow-Origin"] == "*"
        pid = files[0].name[:10]
        with post(json.dumps(dict(persona=pid, price=300, merchant="Test")).encode()) as r:
            out = json.load(r)
            assert out["persona"] == pid and out["price"] == 300 and len(out["options"]) == 4
        with post(json.dumps(dict(csv=files[0].read_text(encoding="utf-8"), price=50)).encode()) as r:
            assert json.load(r)["income"]
        with urllib.request.urlopen(url + "/personas") as r:
            ps = json.load(r)
            assert len(ps) == len(files) and all(x["region"] != "unknown" for x in ps)
        for body in (b"not json", b'{"persona": "persona079"}', b'{"persona": "x", "price": 3}',
                     json.dumps(dict(csv="garbage", price=3)).encode(), b'{"persona": "persona001", "price": -1}'):
            try:
                post(body)
            except urllib.error.HTTPError as e:
                assert e.code == 400 and json.load(e)["error"], body
            else:
                raise AssertionError(f"accepted {body!r}")
    finally:
        srv.shutdown()
    print(f"Self-check passed on {len(files)} statements.")
    print("Price [GBP] | can pay now (and with the BNPL pot) | only with plain BNPL | neither")
    for p in prices:
        print(f"{p} | {tally[p][0]} | {tally[p][1]} | {tally[p][2]}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--serve", action="store_true", help="run the JSON API on 127.0.0.1")
    ap.add_argument("--port", type=int, default=8765, help="port for --serve (default 8765)")
    ap.add_argument("--check", action="store_true", help="run the self-check")
    args = ap.parse_args()
    if args.check:
        check()
    elif args.serve:
        try:
            serve(args.port).serve_forever()
        except KeyboardInterrupt:
            pass
    else:
        ap.print_help()
