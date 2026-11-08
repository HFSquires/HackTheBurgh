"""Andrew's model (task T30): forecast this month's everyday spending and decide whether a purchase keeps the customer
on their net-worth goal. Design: model outline/HackTheBurgh.md (Andrew), MODEL_OUTLINE.md and IMPLEMENTATION.md.

Input is a customer picture from an Open Banking aggregator (mock_bank.fetch_customer; here the v2 mock bank serving the
synthetic data of ob_generator.py). Steps, as in Andrew's outline:
  1. everyday ("random") spending r_n per calendar month: card purchases (rows with a merchant category code) on every
     account, less regular card payments (same description and amount, statements.detect_committed) and one-offs
     (package holidays, MCC 4722, and any single purchase of ONE_OFF_GBP or more);
  2. salary s_n (statements.detect_income on the main account), other income i_n (credits that are neither salary nor
     transfers between the customer's own accounts) and regular payments reg_n (direct debits, standing orders and
     regular card payments, less own-account transfers; a joint account's at JOINT_SHARE);
  3. forecast r_hat_n = f_m(n) * mean over the last k months of r_j / f_m(j), with f_m the ONS retail-sales seasonal
     factor (mean 1), and the remainder max(0, r_hat_n - spent so far this month);
  4. net worth W (all balances, joint at JOINT_SHARE, cards negative, less outstanding BNPL), the month's goal
     W* = W_prev + monthlySavings (default GBP 0). An explicit legacy goalRate is also accepted;
  5. daily main-current-account cash flow through month end or next payday, whichever is later. Red for a
     projected overdraft; amber for missing the savings target; green when both checks pass. Usual spending is
     not reduced by the savings target. Suggested daily budget = max(0, forecastMonth - monthlySavings) / days.

T33 (8 November 2026): monthly savings and overdraft-first warnings requested by the user.
The original spending-classification defaults remain proposals. Guidance, not advice.

    python -X utf8 model.py                   # backtest: writes Analysis/model/ and Figures/model/
    python -X utf8 model.py --serve [--port 8765]   # POST /decide, GET /health on 127.0.0.1 (needs a mock bank)
    python -X utf8 model.py --check           # self-check (starts its own mock bank); writes nothing
"""
import argparse, calendar, csv, datetime as dt, functools, json, math, os, random, statistics, sys, threading
import urllib.error, urllib.request
from collections import defaultdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import market_data
import mock_bank
import statements as st

HERE = Path(__file__).resolve().parent
OB = HERE / "Analysis" / "open_banking"
ANALYSIS, FIGURES = HERE / "Analysis" / "model", HERE / "Figures" / "model"

# Proposed defaults (IMPLEMENTATION.md section 2); each is one parameter so the team can change it in one line.
K = 3                  # months averaged (decision 3)
ONE_OFF_GBP = 250.0    # a single card purchase at or above this is a one-off, not everyday spending
ONE_OFF_MCC = {4722}   # travel agencies and tour operators (package holidays)
JOINT_SHARE = 0.5      # ponytail: the customer's share of a joint account; upgrade: ask, or infer from paying-in
SEED, PERMUTATIONS = 20261107, 20000
MAX_BODY = 20_000
NOT_ADVICE = "Guidance, not financial advice: these are forecasts from your past transactions, not guarantees."


def ym(d):
    return (d.year, d.month)


def month_end(y, m):
    return dt.date(y, m, calendar.monthrange(y, m)[1])


def label(y_m):
    return f"{y_m[0]}-{y_m[1]:02d}"


@functools.cache
def season():
    """Month of the year -> ONS retail-sales seasonal factor f_m (mean 1): the mean over market_data.YEARS of each
    month's value with each year scaled to mean 100, divided by 100. The synthetic data use the same profile."""
    scaled = market_data.seasonality()[0]
    return {m: statistics.mean(scaled[y][m - 1] for y in scaled) / 100 for m in range(1, 13)}


# ------------------------------------------------------------------------------------------------ step 1: everyday
def own_transfers(picture):
    """{(accountId, index)} of booked transactions that move money between the customer's own accounts: a debit on
    one account and a credit of the same amount on another of them within one day, matched one to one.
    ponytail: amount-and-date matching; a real feed's counterparty account or reference would make it exact."""
    credits = defaultdict(list)
    for a in picture["accounts"]:
        for i, t in enumerate(a["transactions"]):
            if t["credit"] > 0:
                credits[round(t["credit"], 2)].append((t["date"], a["accountId"], i))
    out, used = set(), set()
    for a in picture["accounts"]:
        for i, t in enumerate(a["transactions"]):
            if t["debit"] <= 0:
                continue
            for d, acc, j in credits.get(round(t["debit"], 2), ()):
                if acc != a["accountId"] and abs((d - t["date"]).days) <= 1 and (acc, j) not in used:
                    used.add((acc, j))
                    out |= {(a["accountId"], i), (acc, j)}
                    break
    return out


def own_debits(picture, own=None):
    """{(accountId, description)} of debits that are own-account transfers (savings, card repayments, top-ups)."""
    own = own_transfers(picture) if own is None else own
    by_id = {a["accountId"]: a for a in picture["accounts"]}
    return {(acc, by_id[acc]["transactions"][i]["desc"]) for acc, i in own if by_id[acc]["transactions"][i]["debit"] > 0}


def booked_upto(a, as_of):
    return [t for t in a["transactions"] if t["date"] <= as_of]


def regular_card(picture, as_of):
    """{(accountId, description, amount)} of regular card payments seen up to as_of (statements.detect_committed on
    each account's card rows: same description and amount, the same number of times, in at least three months)."""
    out = set()
    for a in picture["accounts"]:
        rows = [t for t in booked_upto(a, as_of) if t["type"] not in ("DD", "SO")]
        out |= {(a["accountId"], c["name"], c["amount"]) for c in st.detect_committed(rows, as_of) if rows}
    return out


def purchases(picture, as_of, pending_until=None):
    """Card purchases (booked up to as_of, plus pending ones dated up to pending_until) as dicts with date, amount,
    merchant, mcc, account and kind ('everyday', 'regular', 'bnpl' or 'oneoff')."""
    regular, out = regular_card(picture, as_of), []
    for a in picture["accounts"]:
        rows = [(t, d) for t, d in zip(a["transactions"], a["transactionDetails"]) if t["date"] <= as_of]
        if pending_until:
            rows += [(p, p) for p in a["pending"] if p["date"] <= pending_until]
        for t, d in rows:
            if not d.get("mcc") or t["debit"] <= 0:
                continue
            mcc = int(d["mcc"])
            kind = ("bnpl" if st.BNPL.search(t["desc"]) else  # an instalment: a regular payment, owed since purchase
                    "regular" if (a["accountId"], t["desc"], st.money(t["debit"])) in regular else
                    "oneoff" if mcc in ONE_OFF_MCC or t["debit"] >= ONE_OFF_GBP else "everyday")
            out.append(dict(date=t["date"], amount=t["debit"], merchant=d.get("merchant"), mcc=mcc,
                            account=a["accountId"], kind=kind, pending=t is d))
    return out


def monthly_everyday(picture, as_of, kind="everyday"):
    """{(year, month): card purchases of this kind [GBP]} for every full calendar month that ends on or before as_of."""
    per = defaultdict(float)
    for p in purchases(picture, as_of):
        if p["kind"] == kind and month_end(*ym(p["date"])) <= as_of:
            per[ym(p["date"])] += p["amount"]
    first = min((t["date"] for a in picture["accounts"] for t in a["transactions"]), default=as_of)
    months, y_m = {}, ym(first)
    while month_end(*y_m) <= as_of:
        if not (y_m == ym(first) and first.day > 7):  # ponytail: a month joined after day 7 is treated as partial
            months[y_m] = st.money(per[y_m])
        y_m = (y_m[0] + (y_m[1] == 12), y_m[1] % 12 + 1)
    return months


# ------------------------------------------------------------------------------------------------ step 2: income, regular
def income_and_regular(picture, as_of):
    """Salary (main account), other income by description (monthly mean over the full months seen) and regular
    payments due in the month after as_of on current accounts, without own-account transfers."""
    main, own = mock_bank.main_account(picture), own_transfers(picture)
    salary = st.detect_income(booked_upto(main, as_of)) if main else None
    other, months = defaultdict(float), set()
    for a in picture["accounts"]:
        for i, t in enumerate(a["transactions"]):
            if t["date"] > as_of:
                continue
            months.add(ym(t["date"]))
            if t["credit"] > 0 and (a["accountId"], i) not in own and not (
                    salary and a is main and t["desc"] == salary["name"]):
                other[t["desc"]] += t["credit"]
    n_months = max(1, len(months))
    other = {k: st.money(v / n_months) for k, v in sorted(other.items(), key=lambda kv: -kv[1])}
    own_desc = own_debits(picture, own)
    regular = []
    for a in picture["accounts"]:
        if a["type"] not in ("current", "jointCurrent"):
            continue
        share = JOINT_SHARE if a["type"] == "jointCurrent" else 1.0
        to_own = {s["reference"] for s in a["standingOrders"] if s.get("toOwnAccountId")}
        for c in st.detect_committed(booked_upto(a, as_of), as_of):
            if c["name"] in to_own or (a["accountId"], c["name"]) in own_desc:
                continue
            regular.append(dict(c, account=a["accountId"], share=share, amount=st.money(c["amount"] * share)))
    return salary, other, regular


# ------------------------------------------------------------------------------------------------ step 3: forecast
def forecast(totals, month, k=K, seasonal=True):
    """r_hat for `month` from the last min(k, available) full months before it: f_month * mean(r_j / f_j); with
    seasonal=False, the plain mean (k=1: last month). None without history."""
    past = sorted(m for m in totals if m < month)[-k:]
    if not past:
        return None
    f = season() if seasonal else defaultdict(lambda: 1.0)
    return f[month[1]] * statistics.mean(totals[m] / f[m[1]] for m in past)


# ------------------------------------------------------------------------------------------------ step 4: net worth, decision
def net_worth(picture, at):
    """Net worth at the end of day `at`: every account's booked balance less its booked transactions after `at`
    (a joint account at JOINT_SHARE; cards negative when owed), less BNPL scheduled payments due after `at`."""
    w = 0.0
    for a in picture["accounts"]:
        later = sum(t["credit"] - t["debit"] for t in a["transactions"] if t["date"] > at)
        share = JOINT_SHARE if a["type"] == "jointCurrent" else 1.0
        bnpl = sum(p["amount"] for p in a["scheduledPayments"] if p["date"] > at)
        w += share * (a["balances"]["booked"] - later) - bnpl
    return w


def purchase_payments(price, today, plan):
    """Illustrative interest-free monthly schedule, rounded to pennies with the remainder in the last payment."""
    if plan not in ("pay_now", "pay_in_3"):
        raise ValueError("paymentPlan must be pay_now or pay_in_3.")
    pennies = round(price * 100)
    count = 3 if plan == "pay_in_3" else 1
    amounts = [pennies // count] * (count - 1) + [pennies - (pennies // count) * (count - 1)]
    return [dict(date=st.add_months(today, i), amount=amount / 100) for i, amount in enumerate(amounts)]


def cash_flow(picture, price, today, salary, k=K, payments=None, horizon=None):
    """Daily main-current-account projection through month end or next payday, whichever is later.

    Savings and credit limits are not spendable cash here. Own-account transfers and card repayments
    remain cash outgoings. Other income without a reliable payment date is not assumed to arrive.
    ponytail: monthly recurring payments and even daily everyday spending; intraday ordering and
    irregular future purchases need a richer forecast. This is a projection, not a probability.
    """
    main = mock_bank.main_account(picture)
    payday = st.next_payday(salary, today)
    end = max(month_end(*ym(today)), payday, horizon or today)
    payments = payments or purchase_payments(price, today, "pay_now")
    purchase_due = defaultdict(float)
    for p in payments:
        purchase_due[p["date"]] += p["amount"]
    single = dict(picture, accounts=[main])
    totals = monthly_everyday(single, today)
    events = defaultdict(float)
    pending = main["pending"]
    balance = main["balances"]["booked"] + sum(p["credit"] - p["debit"] for p in pending if p["date"] <= today)
    for p in pending:
        if today < p["date"] <= end:
            events[p["date"]] += p["credit"] - p["debit"]
    last_booked = max((t["date"] for t in booked_upto(main, today)), default=today)
    for c in st.detect_committed(booked_upto(main, today), last_booked):
        due = dt.date.fromisoformat(c["due"])
        day = due.day
        while due <= end:
            # Pending bank entries take precedence over the same predicted payment.
            if not any(p["desc"] == c["name"] and abs(p["debit"] - c["amount"]) < .01
                       and abs((p["date"] - due).days) <= 3 for p in pending):
                events[max(today, due)] -= c["amount"]
            due = st.add_months(due, 1, day)
    for p in main["scheduledPayments"]:
        if today < p["date"] <= end and not any(
                t["desc"] == p["reference"] and abs(t["debit"] - p["amount"]) < .01
                and abs((t["date"] - p["date"]).days) <= 3 for t in pending):
            events[p["date"]] -= p["amount"]
    pay = payday
    while pay <= end:
        if not any(p["desc"] == salary["name"] and p["credit"] > 0
                   and abs((p["date"] - pay).days) <= 3 for p in pending):
            events[pay] += salary["monthly"]
        pay = st.next_payday(salary, pay)
    daily = {}
    m = ym(today)
    while month_end(*m).replace(day=1) <= end:
        month_last = month_end(*m)
        first = max(today + dt.timedelta(days=1), month_last.replace(day=1))
        spent = sum(p["amount"] for p in purchases(single, today, pending_until=month_last)
                    if ym(p["date"]) == m and p["kind"] == "everyday")
        amount = max(0, (forecast(totals, m, k) or 0) - spent)
        n = (month_last - first).days + 1
        daily[m] = amount / n if n > 0 else 0
        m = (m[0] + (m[1] == 12), m[1] % 12 + 1)
    balance += events[today]  # Include expected bills due since the last booked transaction.
    paid = purchase_due[today]
    low, low_day = balance - paid, today
    low_without = balance
    running = balance
    month_balance = balance - paid
    d = today + dt.timedelta(days=1)
    while d <= end:
        running += events[d] - daily[ym(d)]
        paid += purchase_due[d]
        low_without = min(low_without, running)
        if running - paid < low:
            low, low_day = running - paid, d
        if d == month_end(*ym(today)):
            month_balance = running - paid
        d += dt.timedelta(days=1)
    return dict(accountId=main["accountId"], accountName=main.get("nickname") or "Main current account",
                balanceNow=st.money(balance), lowestWithoutPurchase=st.money(low_without),
                lowestWithPurchase=st.money(low), lowestDate=low_day.isoformat(),
                forecastMonthEnd=st.money(month_balance), horizon=end.isoformat(), nextPayday=payday.isoformat(),
                overdrawn=low < -.005, alreadyAtRisk=low_without < -.005,
                basis="Main current account; selected repayment schedule; usual spending; end-of-day balances. Savings are not automatically transferred.")


def money_str(x):
    return f"£{abs(x):,.2f}"


def decide(picture, price, today=None, goal_rate=None, k=K, monthly_savings=None, payment_plan="pay_now"):
    """The checkout decision for a purchase at `price` [GBP] on `today` (default: the date of the bank's balances).
    Returns a JSON-ready verdict, cash-flow minimum, monthly savings forecast and suggested daily budget."""
    if not (isinstance(price, (int, float)) and not isinstance(price, bool) and math.isfinite(price) and 0.01 <= price <= 1e6):
        raise ValueError("price must be a number of pounds from 0.01 to 1,000,000.")
    if monthly_savings is not None and goal_rate is not None:
        raise ValueError("Choose monthlySavings or goalRate, not both.")
    if monthly_savings is not None and not (isinstance(monthly_savings, (int, float))
            and not isinstance(monthly_savings, bool) and math.isfinite(monthly_savings) and 0 <= monthly_savings <= 1e6):
        raise ValueError("monthlySavings must be a number of pounds between 0 and 1,000,000.")
    if goal_rate is not None and not (isinstance(goal_rate, (int, float)) and not isinstance(goal_rate, bool)
            and math.isfinite(goal_rate) and -.5 <= goal_rate <= 1):
        raise ValueError("goalRate must be between -0.5 and 1.")
    if not isinstance(k, int) or isinstance(k, bool) or not 1 <= k <= 12:
        raise ValueError("k must be a whole number between 1 and 12.")
    main = mock_bank.main_account(picture)
    if main is None:
        raise ValueError("The bank showed no current account in the customer's sole name.")
    as_of = main["balances"]["asOf"].date()
    today = today or as_of
    last = max((t["date"] for a in picture["accounts"] for t in a["transactions"] if t["date"] <= today), default=today)
    if today != as_of:
        raise ValueError(f"today must match the date of the bank's balances: "
                         f"{as_of.isoformat()}.")
    price = st.money(price)
    payments = purchase_payments(price, today, payment_plan)
    g = goal_rate if goal_rate is not None else 0.0
    month, end = ym(today), month_end(*ym(today))
    days = end.day
    totals = monthly_everyday(picture, today)
    r_hat = forecast(totals, month, k)
    spent_rows = [p for p in purchases(picture, today, pending_until=today) if ym(p["date"]) == month and p["kind"] == "everyday"]
    spent = sum(p["amount"] for p in spent_rows)
    salary, other, regular = income_and_regular(picture, last)
    w_prev = net_worth(picture, month_end(*ym(today.replace(day=1) - dt.timedelta(1))))
    pending = sum((JOINT_SHARE if a["type"] == "jointCurrent" else 1.0) * (p["debit"] - p["credit"])
                  for a in picture["accounts"] for p in a["pending"] if p["date"] <= today)
    w_now = net_worth(picture, today) - pending
    target = (max(w_prev, 0.0) * ((1 + g) ** (1 / 12) - 1) if goal_rate is not None
              else monthly_savings or 0.0)
    goal = w_prev + target
    base = dict(price=st.money(price), today=today.isoformat(), month=label(month), assumptions=dict(
        k=k, oneOffGBP=ONE_OFF_GBP, oneOffMCC=sorted(ONE_OFF_MCC), jointShare=JOINT_SHARE,
        goalRate=round(g, 6), goalRateSource="given" if goal_rate is not None else "monthly savings target",
        monthlySavings=st.money(target),
        seasonalFactor=round(season()[month[1]], 6)), notAdvice=NOT_ADVICE)
    if salary is None or r_hat is None:
        why = "No regular salary was found in the account history." if salary is None else "There is no full month of history to forecast from."
        return base | dict(verdict="neutral", title="Not enough history", message=why + " No verdict is given.",
                           netWorth=dict(now=st.money(w_now), startOfMonth=st.money(w_prev), goal=st.money(goal)))
    payday = st.next_payday(salary, today)
    salary_due = salary["monthly"] if payday <= end else 0.0
    due = [c for c in regular if last < dt.date.fromisoformat(c["due"]) <= end]
    # Pending entries already reduce w_now, so do not deduct the same expected bill again.
    due = [c for c in due if not any(p["desc"] == c["name"] and abs(p["debit"] * c["share"] - c["amount"]) < .01
           and abs((p["date"] - dt.date.fromisoformat(c["due"])).days) <= 3
           for a in picture["accounts"] if a["accountId"] == c["account"] for p in a["pending"] if p["date"] <= today)]
    committed_due = sum(c["amount"] for c in due)
    remainder = max(0.0, r_hat - spent)
    w_without = w_now + salary_due - committed_due - remainder
    w_with = w_without - price
    headroom, surplus = w_with - goal, w_without - goal
    mname = f"{calendar.month_name[month[1]]} {month[0]}"
    horizon = None
    if payment_plan == "pay_in_3":
        final = payments[-1]["date"]
        horizon = max(month_end(*ym(final)), st.next_payday(salary, final))
    cash = cash_flow(picture, price, today, salary, k, payments, horizon)
    comparison = None
    if payment_plan == "pay_in_3":
        comparison = dict(payNow=cash_flow(picture, price, today, salary, k, horizon=horizon), payIn3=cash,
                          note="Both options use the same forecast horizon. Pay in 3 changes cash timing, not the full purchase cost or savings goal.")
    risk = "overdraft" if cash["overdrawn"] else "savings" if headroom < -.005 else "none"
    if risk == "overdraft":
        verdict, title = "reconsider", "You’re projected to go overdrawn"
        msg = (f"If you make this purchase and keep spending as usual, your main current account is projected "
               f"to reach −{money_str(cash['lowestWithPurchase'])} on {cash['lowestDate']}. "
               + ("You were already on track to go overdrawn; this purchase would make the shortfall larger. "
                  if cash["alreadyAtRisk"] else "")
               + "Consider pausing this purchase.")
    elif risk == "savings":
        verdict, title = "caution", "Your savings goal is at risk"
        msg = (f"At your usual spending rate, this purchase would leave you {money_str(headroom)} short "
               f"of your {money_str(target)} savings goal for {mname}.")
    else:
        verdict, title = "good", "Fits your goal"
        msg = f"After this purchase your net worth is forecast to end {mname} {money_str(headroom)} above your goal."
    if payment_plan == "pay_in_3":
        title = "Pay in 3: " + title[0].lower() + title[1:]
        msg += (" This includes all three monthly payments through " + cash["horizon"]
                + ". Spreading payments does not reduce the purchase cost or the debt counted against your savings goal.")
    return base | dict(
        verdict=verdict, title=title, message=msg, daysToAfford=None, risk=risk,
        cashFlow=cash, comparison=comparison,
        paymentPlan=payment_plan,
        payments=[dict(date=p["date"].isoformat(), amount=p["amount"]) for p in payments],
        paymentAssumption="Illustrative, interest-free: first payment now, then one and two calendar months later. Check the retailer’s actual dates, eligibility and fees.",
        savings=dict(monthlyTarget=st.money(target), forecastSaved=st.money(w_with - w_prev),
                     shortfall=st.money(max(0, -headroom)),
                     usualDailySpending=st.money(r_hat / days),
                     suggestedDailyBudget=st.money(max(0, (r_hat - target) / days)),
                     dailyReductionNeeded=st.money(target / days)),
        income=dict(salary=salary["monthly"], salaryName=salary["name"], nextPayday=payday.isoformat(),
                    salaryDueThisMonth=st.money(salary_due), otherMonthly=dict(list(other.items())[:5])),
        regularDueThisMonth=[dict(name=c["name"], type=c["type"], due=c["due"], amount=c["amount"]) for c in due],
        everyday=dict(forecastMonth=st.money(r_hat), spentSoFar=st.money(spent), remainder=st.money(remainder),
                      linearRemainder=st.money((days - today.day) / days * r_hat),
                      history={label(m): v for m, v in sorted(totals.items())[-k:]}),
        netWorth=dict(now=st.money(w_now), startOfMonth=st.money(w_prev), goal=st.money(goal),
                      forecastEndWithout=st.money(w_without), forecastEndWith=st.money(w_with),
                      headroom=st.money(headroom), surplusWithout=st.money(surplus)))


# ------------------------------------------------------------------------------------------------ data access
def start_bank():
    """An in-process v2 mock bank on a free port, allow-listed for this process; returns (server, base URL)."""
    srv = mock_bank.serve(0, quiet=True, source="v2")
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_port}"
    os.environ["BANK_ALLOWED_HOSTS"] = ",".join(filter(None, [os.environ.get("BANK_ALLOWED_HOSTS"), base]))
    return srv, base


def personas():
    files = sorted(OB.glob("persona[0-9][0-9][0-9]_*.json"))
    assert len(files) == 100, f"{len(files)} persona files in {OB}: run ob_generator.py first"
    return [f.name[:10] for f in files]


def truth():
    """Ground truth used only for scoring: {persona: row of ground_truth.csv}, {(persona, (y, m)): booked GBP}."""
    with open(OB / "ground_truth.csv", encoding="utf-8", newline="") as f:
        rows = {r["persona"]: r for r in csv.DictReader(f)}
    booked = defaultdict(float)
    with open(OB / "ground_truth_monthly.csv", encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            booked[(r["persona"], (int(r["month"][:4]), int(r["month"][5:])))] += float(r["booked"])
    return rows, dict(booked)


def lumpy_below(gt_row):
    """{(y, m): [(date, merchant)]} of the generator's lumpy purchases for one persona (ground_truth.csv gives dates and
    merchants, not amounts; validate looks the amounts up in the transactions)."""
    out = defaultdict(list)
    for item in filter(None, (gt_row.get("lumpy_purchases") or "").split(";")):
        d, merchant = item.split(" ", 1)
        out[ym(dt.date.fromisoformat(d))].append((dt.date.fromisoformat(d), merchant))
    return out


# ------------------------------------------------------------------------------------------------ validation and backtest
def validate(pictures, gt, booked):
    """Steps 1 and 2 against ground truth. Returns a dict of counts and the unexplained differences."""
    end = dt.date(2026, 10, 31)
    exact = explained = 0
    unexplained, salary_bad, mandate_missing = [], [], []
    for pid, pic in pictures.items():
        totals, bnpl = monthly_everyday(pic, end), monthly_everyday(pic, end, "bnpl")
        rows = purchases(pic, end)
        lumpy = lumpy_below(gt[pid])
        for m, v in totals.items():
            diff = st.money(v - booked[(pid, m)])
            if abs(diff) < 0.01:
                exact += 1
                continue
            # Known definitional differences: a lumpy purchase below ONE_OFF_GBP is everyday to the model but a
            # one-off to the generator; a BNPL instalment is a regular payment to the model but everyday to the generator.
            small = sum(max((p["amount"] for p in rows if p["date"] == d and p["merchant"] == merch
                             and p["kind"] == "everyday"), default=0.0) for d, merch in lumpy.get(m, ()))
            if abs(diff - small + bnpl.get(m, 0.0)) < 0.01:
                explained += 1
            else:
                unexplained.append((pid, label(m), diff, st.money(small), st.money(bnpl.get(m, 0.0))))
        salary, _, regular = income_and_regular(pic, end)
        if not salary or abs(salary["monthly"] - float(gt[pid]["net_monthly"])) > 0.005:
            salary_bad.append((pid, salary and salary["monthly"], gt[pid]["net_monthly"]))
        names, own_desc = {(c["account"], c["name"]) for c in regular}, own_debits(pic)
        for a in pic["accounts"]:
            if a["type"] not in ("current", "jointCurrent"):
                continue
            to_own = {s["reference"] for s in a["standingOrders"] if s.get("toOwnAccountId")}
            live = [(m["name"], m["lastDate"]) for m in a["directDebits"]] + [
                (s["reference"], s["lastDate"]) for s in a["standingOrders"] if s["reference"] not in to_own]
            for name, lastd in live:  # every mandate paid in the last 35 days is regular, unless it is an own transfer
                if lastd and (end - lastd).days <= 35 and (a["accountId"], name) not in names | own_desc:
                    mandate_missing.append((pid, a["accountId"], name))
    return dict(months=exact + explained + len(unexplained), exact=exact, explained=explained,
                unexplained=unexplained, salary_bad=salary_bad, mandate_missing=mandate_missing)


def backtest(pictures, booked, ks=range(1, 7)):
    """Rolling origin: for target months 4 to 12 (February to October 2026), fit on the months before only and
    forecast; actual = the generator's booked everyday spending. Returns rows (persona, month, actual, predictions)."""
    months = [(2025, 11), (2025, 12)] + [(2026, m) for m in range(1, 11)]
    rows = []
    end = dt.date(2026, 10, 31)
    for pid, pic in pictures.items():
        bnpl = monthly_everyday(pic, end, "bnpl")  # observed instalments, removed from the generator's everyday total
        for target in months[3:]:
            origin = month_end(*target).replace(day=1) - dt.timedelta(1)
            totals = monthly_everyday(pic, origin)
            r = dict(persona=pid, month=label(target), actual=st.money(booked[(pid, target)] - bnpl.get(target, 0.0)))
            for k in ks:
                r[f"seasonal_k{k}"] = forecast(totals, target, k, True)
                r[f"plain_k{k}"] = forecast(totals, target, k, False)
            rows.append(r)
    return rows


def summarise(rows, ks=range(1, 7)):
    """Per model: per-person MAE (mean over the 9 target months), then mean and SE across persons."""
    persons = sorted({r["persona"] for r in rows})
    per = {}
    for name in [f"{s}_k{k}" for s in ("seasonal", "plain") for k in ks]:
        per[name] = [statistics.mean(abs(r[name] - r["actual"]) for r in rows if r["persona"] == p) for p in persons]
    stats = {n: (statistics.mean(v), statistics.stdev(v) / math.sqrt(len(v)), len(v)) for n, v in per.items()}
    return per, stats


def sign_flip(d, seed=SEED, n=PERMUTATIONS):
    """Two-sided paired sign-flip permutation test of mean(d) = 0; p = (1 + #|mean*| >= |mean|) / (n + 1)."""
    rng, obs = random.Random(seed), abs(statistics.mean(d))
    hits = sum(abs(statistics.mean(x if rng.random() < 0.5 else -x for x in d)) >= obs - 1e-12 for _ in range(n))
    return (1 + hits) / (n + 1)


def holm(ps):
    order = sorted(range(len(ps)), key=lambda i: ps[i])
    out, run = [0.0] * len(ps), 0.0
    for rank, i in enumerate(order):
        run = max(run, min(1.0, (len(ps) - rank) * ps[i]))
        out[i] = run
    return out


def comparisons(per):
    pairs = [("seasonal_k3", "plain_k1"), ("seasonal_k3", "plain_k3")]
    res = []
    for a, b in pairs:
        d = [x - y for x, y in zip(per[a], per[b])]
        res.append(dict(a=a, b=b, mean=statistics.mean(d), se=statistics.stdev(d) / math.sqrt(len(d)), n=len(d), p=sign_flip(d)))
    for r, ph in zip(res, holm([r["p"] for r in res])):
        r["p_holm"] = ph
    return res


def load_pictures():
    srv, base = start_bank()
    try:
        return {pid: mock_bank.fetch_customer(base, persona=pid) for pid in personas()}
    finally:
        srv.shutdown()


NAMES = {"seasonal": "Deseasonalised mean (Andrew, corrected)", "plain": "Plain mean (k = 1: last month)"}


def write_outputs(rows, per, stats, comp, val, ks=range(1, 7)):
    import subprocess
    import matplotlib.pyplot as plt
    import figstyle as tf
    ANALYSIS.mkdir(parents=True, exist_ok=True)
    FIGURES.mkdir(parents=True, exist_ok=True)
    cols = ["persona", "month", "actual"] + [f"{s}_k{k}" for s in ("seasonal", "plain") for k in ks]
    with open(ANALYSIS / "backtest.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(cols)
        for r in rows:
            w.writerow([r[c] if isinstance(r[c], str) else f"{r[c]:.6f}" for c in cols])
    tf.use()
    fig, ax = plt.subplots(figsize=(12, 6.75))
    show = [("Simple average of the last 3 months", "plain_k3", tf.tint(tf.MUTED, 0.45)),
            ("Copy last month", "plain_k1", tf.tint(tf.C1, 0.45)),
            ("Our forecast (3 months, adjusted for the season)", "seasonal_k3", tf.C1)]
    bars = tf.bar(ax, range(3), [stats[k][0] for _, k, _ in show], [c for _, _, c in show], width=0.7)
    ax.bar_label(bars, labels=[f"£{stats[k][0]:.0f}" for _, k, _ in show], padding=4, color=tf.INK, fontsize=16,
                 fontweight="semibold")
    ax.set_xticks(range(3), [n.replace(" (", "\n(") for n, _, _ in show])
    ax.set_yticks([])
    ax.set_ylim(0, max(stats[k][0] for _, k, _ in show) * 1.2)
    tf.clean(ax, grid=None)
    saving = stats["plain_k3"][0] - stats["seasonal_k3"][0]
    tf.headline(fig, f"Adjusting for the season cuts forecast error by about £{saving:.0f} a month",
                "Average gap between forecast and actual monthly spending (lower is better), 100 test customers")
    for ext in ("pdf", "svg"):
        fig.savefig(FIGURES / f"forecast_errors.{ext}", bbox_inches="tight",
                    metadata={"pdf": {"CreationDate": None}, "svg": {"Date": None}}[ext])
    plt.close(fig)
    commit = subprocess.run(["git", "log", "-1", "--format=%h", "--", "model.py"], cwd=HERE, capture_output=True,
                            text=True).stdout.strip() or "uncommitted"
    gen = subprocess.run(["git", "log", "-1", "--format=%h", "--", "ob_generator.py"], cwd=HERE, capture_output=True,
                         text=True).stdout.strip() or "unknown"
    n = stats["seasonal_k3"][2]
    tab = "\n".join(["| k | " + " | ".join(f"{NAMES[s]}: MAE ± SE [GBP]" for s in ("seasonal", "plain")) + " | n |",
                     "|---|---|---|---|"] + [f"| {k} | " + " | ".join(
                         f"{stats[f'{s}_k{k}'][0]:.2f} ± {stats[f'{s}_k{k}'][1]:.2f}" for s in ("seasonal", "plain"))
                                             + f" | {n} |" for k in ks])
    ctab = "\n".join(["| Comparison (A minus B) | Mean paired difference ± SE [GBP] | n | p (sign-flip) | p (Holm) |",
                      "|---|---|---|---|---|"] + [f"| {c['a']} minus {c['b']} | {c['mean']:+.2f} ± {c['se']:.2f} | {c['n']} | "
                                                 f"{c['p']:.2g} | {c['p_holm']:.2g} |" for c in comp])
    best = min(stats, key=lambda x: stats[x][0])
    lines = [f"# Forecast error of everyday spending by months averaged",
             "", "Files: `forecast_errors.pdf`, `forecast_errors.svg` (this file: `forecast_errors.md`), written by `model.py` (task T30).",
             "", "**The data are synthetic** (`ob_generator.py`), so these errors describe how well the model recovers the generator's process, not real customers.",
             "", "## Source data", "",
             f"The 100 customer pictures read through the v2 mock bank (`mock_bank.fetch_customer`) from `Analysis/open_banking/persona*.json` "
             f"(written by `ob_generator.py`, commit `{gen}`), scored against `Analysis/open_banking/ground_truth_monthly.csv` (`booked`, summed over "
             f"categories). Code: `model.py` (commit `{commit}`). Every forecast and actual value: [`Analysis/model/backtest.csv`](../../Analysis/model/backtest.csv).",
             "", "## Filters, transformations and units", "",
             f"Everyday spending per person and calendar month [GBP]: card purchases (rows with a merchant category code) on every account, less regular card "
             f"payments detected at the forecast origin (same description and amount, the same number of times, in at least three months) and one-offs "
             f"(merchant category {sorted(ONE_OFF_MCC)} or a single purchase of GBP {ONE_OFF_GBP:.0f} or more). Rolling origin: each target month from "
             "February to October 2026 (9 months) is forecast from the full months before it only; with fewer than k months available, all are used. "
             "Deseasonalised mean: f_target × mean(r_j / f_j) over the last k months, f the ONS retail-sales seasonal factor (`market_data.seasonality`, "
             "mean over 2021 to 2025, mean 1). Plain mean: mean of the last k months (k = 1 is last month). Actual: the generator's booked everyday "
             "spending (`ground_truth_monthly.csv`) less the BNPL instalments booked that month, which the model treats as regular payments.",
             "", "## Plotted data", "",
             "Per person, the absolute error is averaged over the 9 target months (one value per person); the plot shows the mean of these across "
             "persons. The figure, drawn for a general audience, shows three of these at a glance as bars (plain mean k = 3, last month, "
             "deseasonalised mean k = 3) with no error bars; the full table with ± SE = s / sqrt(n), ddof = 1, is below.", "", tab,
             "", "## Sample size", "", f"n = {n} persons for every point; 9 target months each ({len(rows)} person-months).",
             "", "## Statistics and tests", "", ctab, "",
             f"Test: two-sided paired sign-flip permutation test on the per-person differences in MAE ({PERMUTATIONS} random sign assignments, "
             f"seed {SEED}); p = (1 + count) / ({PERMUTATIONS} + 1). Holm correction over the two comparisons.",
             "", "## Validation of steps 1 and 2 (same run)", "",
             f"Everyday totals for the 12 months to 31 October 2026 against the generator's booked spending: {val['exact']} of {val['months']} person-months "
             f"equal to the penny; {val['explained']} differ only by lumpy purchases below GBP {ONE_OFF_GBP:.0f} (everyday to the model, one-off to the "
             f"generator) and BNPL instalments (regular payments to the model, everyday to the generator); {len(val['unexplained'])} unexplained. Salary equal to `ground_truth.csv` `net_monthly`: {100 - len(val['salary_bad'])} of 100.",
             "", "## Seed and parameters", "", f"Permutation seed {SEED}; K = {K} is the proposed default; ONE_OFF_GBP = {ONE_OFF_GBP:.0f}. No other random numbers.",
             "", "## Interpretation", "",
             f"The lowest mean absolute error among the models plotted is the {NAMES[best.split('_')[0]].split(' (')[0].lower()} with k = {best[-1]} "
             f"({stats[best][0]:.2f} ± {stats[best][1]:.2f} GBP). Across k = 1 to 6 the deseasonalised mean ranges from "
             f"{min(stats[f'seasonal_k{k}'][0] for k in ks):.2f} to {max(stats[f'seasonal_k{k}'][0] for k in ks):.2f} GBP and the plain mean "
             f"from {min(stats[f'plain_k{k}'][0] for k in ks):.2f} to {max(stats[f'plain_k{k}'][0] for k in ks):.2f} GBP; differences between "
             "values of k were not tested. "
             f"The deseasonalised mean with k = 3 differs from last month by {comp[0]['mean']:+.2f} ± {comp[0]['se']:.2f} GBP (Holm p = {comp[0]['p_holm']:.2g}) "
             f"and from the plain 3-month mean by {comp[1]['mean']:+.2f} ± {comp[1]['se']:.2f} GBP (Holm p = {comp[1]['p_holm']:.2g}). "
             "The seasonal factors are the same ONS profile the generator used to make the data, so the seasonal model's advantage shows what knowing "
             "the season is worth, not that the model learnt it; on real data the factors would come from the same public ONS series, independent of "
             "the customer."]
    (FIGURES / "forecast_errors.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (ANALYSIS / "validation.md").write_text(
        f"# Validation of model steps 1 and 2\n\nWritten by `model.py` (commit `{commit}`). Synthetic data.\n\n"
        f"Everyday totals, 12 months to 31 October 2026: {val['exact']} of {val['months']} person-months exact; {val['explained']} explained by lumpy "
        f"purchases below GBP {ONE_OFF_GBP:.0f} and BNPL instalments; {len(val['unexplained'])} unexplained"
        + ("" if not val["unexplained"] else ": " + "; ".join(f"{p} {m} diff {d} (lumpy {s}, BNPL {b})" for p, m, d, s, b in val["unexplained"]))
        + f".\n\nSalary mismatches: {len(val['salary_bad'])}" + ("" if not val["salary_bad"] else f" {val['salary_bad']}")
        + f".\n\nRecent monthly mandates missing from regular payments: {len(val['mandate_missing'])}"
        + ("" if not val["mandate_missing"] else f" {val['mandate_missing'][:20]}") + ".\n", encoding="utf-8")


def run():
    pictures = load_pictures()
    gt, booked = truth()
    val = validate(pictures, gt, booked)
    rows = backtest(pictures, booked)
    per, stats = summarise(rows)
    comp = comparisons(per)
    write_outputs(rows, per, stats, comp, val)
    print(f"validation: {val['exact']} exact, {val['explained']} explained, {len(val['unexplained'])} unexplained of "
          f"{val['months']}; salary mismatches {len(val['salary_bad'])}; mandates missing {len(val['mandate_missing'])}")
    for name in ("seasonal_k3", "plain_k3", "plain_k1"):
        print(f"{name}: MAE {stats[name][0]:.2f} ± {stats[name][1]:.2f} GBP")
    for c in comp:
        print(f"{c['a']} - {c['b']}: {c['mean']:+.2f} ± {c['se']:.2f} GBP, Holm p = {c['p_holm']:.2g}")


# ------------------------------------------------------------------------------------------------ HTTP API
def read_request(body):
    """Validated POST /decide body -> (bank args, price, today, legacy goal rate, monthly savings). Raises ValueError."""
    if not isinstance(body, dict) or not set(body) <= {"bank", "price", "today", "goalRate", "monthlySavings", "paymentPlan"} or "bank" not in body:
        raise ValueError('Body must be {"bank": {"baseUrl": ..., "persona" or "tokens": ...}, "price": ..., '
                         'optional "today": "YYYY-MM-DD", optional "monthlySavings": pounds (or legacy "goalRate": fraction a year)}.')
    bank = body["bank"]
    if not isinstance(bank, dict) or not set(bank) <= {"baseUrl", "persona", "tokens"}:
        raise ValueError('bank must be {"baseUrl": ..., "persona": ...} or {"baseUrl": ..., "tokens": {provider: token}}.')
    today = body.get("today")
    if today is not None:
        try:
            today = dt.date.fromisoformat(today) if isinstance(today, str) and len(today) == 10 else None
        except ValueError:
            today = None
        if today is None:
            raise ValueError("today must be a date as YYYY-MM-DD.")
    g = body.get("goalRate")
    if g is not None and not (isinstance(g, (int, float)) and not isinstance(g, bool) and math.isfinite(g) and -0.5 <= g <= 1):
        raise ValueError("goalRate must be a fraction a year between -0.5 and 1 (0.03 for 3%).")
    return bank, body.get("price"), today, g, body.get("monthlySavings"), body.get("paymentPlan", "pay_now")


class Handler(BaseHTTPRequestHandler):
    def send(self, code, obj):
        data = json.dumps(obj, allow_nan=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        self.send(200, {"status": "ok"}) if self.path == "/health" else self.send(404, {"error": "Not found."})

    def do_POST(self):
        if self.path != "/decide":
            return self.send(404, {"error": "Not found."})
        if (self.headers.get("Content-Type") or "").split(";")[0].strip().lower() != "application/json":
            return self.send(415, {"error": "Content-Type must be application/json."})
        try:
            n = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            n = -1
        if not 0 < n <= MAX_BODY:
            return self.send(400, {"error": f"The body must be JSON of at most {MAX_BODY} bytes."})
        try:
            body = json.loads(self.rfile.read(n))
            bank, price, today, g, savings, plan = read_request(body)
            picture = mock_bank.fetch_customer(bank.get("baseUrl"), bank.get("persona"), bank.get("tokens"))
            out = decide(picture, price, today, g, monthly_savings=savings, payment_plan=plan)
        except (ValueError, RecursionError, st.StatementError) as e:  # JSONDecodeError is a ValueError
            msg = str(e) if isinstance(e, (st.StatementError,)) or not isinstance(e, (json.JSONDecodeError, RecursionError)) else "The body is not valid JSON."
            return self.send(400, {"error": msg})
        except Exception:
            return self.send(500, {"error": "Internal error."})
        self.send(200, out)

    def log_message(self, *a):
        if not getattr(self.server, "quiet", False):
            super().log_message(*a)


def serve(port, quiet=False):
    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    srv.quiet = quiet
    return srv


# ------------------------------------------------------------------------------------------------ self-check
def check():
    # Step 3 by hand: totals 100, 200, 300 in Aug to Oct with factors f; November forecast.
    f = season()
    tot = {(2026, 8): 100.0, (2026, 9): 200.0, (2026, 10): 300.0}
    want = f[11] * (100 / f[8] + 200 / f[9] + 300 / f[10]) / 3
    assert abs(forecast(tot, (2026, 11), 3) - want) < 1e-9 and forecast(tot, (2026, 11), 1, False) == 300.0
    assert forecast(tot, (2026, 8), 3) is None and abs(statistics.mean(f.values()) - 1) < 1e-9
    assert forecast(tot | {(2026, 11): 1e9}, (2026, 11), 3) == forecast(tot, (2026, 11), 3)  # target month unused
    assert holm([0.01, 0.04]) == [0.02, 0.04] and holm([0.04, 0.01]) == [0.04, 0.02]
    assert sign_flip([1.0] * 12, n=2000) < 0.01 and sign_flip([1.0, -1.0] * 6, n=2000) > 0.5

    srv, base = start_bank()
    api = serve(0, quiet=True)
    threading.Thread(target=api.serve_forever, daemon=True).start()
    try:
        pics = {pid: mock_bank.fetch_customer(base, persona=pid) for pid in personas()}
        gt, booked = truth()
        val = validate(pics, gt, booked)
        assert not val["unexplained"], val["unexplained"][:5]  # step 1
        assert not val["salary_bad"], val["salary_bad"][:5]      # step 2
        assert not val["mandate_missing"], val["mandate_missing"][:5]
        # No look-ahead in the backtest: corrupting the target month's transactions changes no forecast.
        pid = "persona072"
        pic = pics[pid]
        spoilt = {**pic, "accounts": [{**a, "transactions": [dict(t, debit=t["debit"] * 7) if ym(t["date"]) == (2026, 6)
                                                            else t for t in a["transactions"]]} for a in pic["accounts"]]}
        r1, r2 = backtest({pid: pic}, booked), backtest({pid: spoilt}, booked)
        for a, b in zip(r1, r2):
            if a["month"] <= "2026-06":
                assert all(a[k] == b[k] for k in a if k != "actual"), a["month"]
        # Step 5: verdicts never improve with price; neutral without salary; strict JSON.
        rank = {"good": 0, "caution": 1, "reconsider": 2}
        seen = defaultdict(int)
        for pid, pic in pics.items():
            vs = [decide(pic, p)["verdict"] for p in (10, 100, 300, 1000, 3000, 30000)]
            seen[vs[2]] += 1
            assert all(rank[a] <= rank[b] for a, b in zip(vs, vs[1:])), (pid, vs)
            json.dumps(decide(pic, 300), allow_nan=False)
        for pid, r in gt.items():
            if int(r["unarranged_overdraft_days"] or 0) > 0:
                assert decide(pics[pid], 300)["verdict"] == "reconsider", pid
        main = mock_bank.main_account(pics["persona001"])
        name = st.detect_income(main["transactions"])["name"]
        nosal = {**pics["persona001"], "accounts": [{**a, "transactions": [t for t in a["transactions"] if t["desc"] != name]}
                                                     if a is main else a for a in pics["persona001"]["accounts"]]}
        nosal["mainAccountId"] = main["accountId"]
        assert decide(nosal, 50)["verdict"] == "neutral"
        d = decide(pics["persona001"], 50)
        nw = d["netWorth"]
        assert abs(nw["forecastEndWith"] - (nw["forecastEndWithout"] - 50)) < 0.011 and d["daysToAfford"] is None
        for bad_price in (0, -1, float("nan"), True, "10", 2e6):
            try:
                decide(pics["persona001"], bad_price)
            except ValueError:
                pass
            else:
                raise AssertionError(f"accepted price {bad_price!r}")
        # Step 6: the endpoint.
        url = f"http://127.0.0.1:{api.server_port}"

        def post(body, ctype="application/json"):
            req = urllib.request.Request(url + "/decide", data=body if isinstance(body, bytes) else json.dumps(body).encode(),
                                         headers={"Content-Type": ctype} if ctype else {})
            try:
                with urllib.request.urlopen(req) as r:
                    return r.status, json.load(r)
            except urllib.error.HTTPError as e:
                return e.code, json.load(e)
        with urllib.request.urlopen(url + "/health") as r:
            assert json.load(r) == {"status": "ok"}
        verdicts = {}
        for pid in ("persona038", "persona004", "persona055"):
            code, out = post({"bank": {"baseUrl": base, "persona": pid}, "price": 409})
            assert code == 200 and out == json.loads(json.dumps(decide(pics[pid], 409))), pid
            verdicts[pid] = out["verdict"]
        for body, code in ((b"not json", 400), ({"bank": {"baseUrl": base, "persona": "persona001"}}, 400),
                           ({"bank": {"baseUrl": base, "persona": "x"}, "price": 5}, 400),
                           ({"bank": {"baseUrl": "http://example.com", "persona": "persona001"}, "price": 5}, 400),
                           ({"bank": {"baseUrl": base, "persona": "persona001"}, "price": 5, "today": "2026-10-01"}, 400),
                           ({"bank": {"baseUrl": base, "persona": "persona001"}, "price": 5, "goalRate": 9}, 400),
                           ({"bank": {"baseUrl": base, "persona": "persona001", "x": 1}, "price": 5}, 400),
                           (b"[" * 5000 + b"]" * 5000, 400)):
            got, out = post(body)
            assert got == code and out["error"] and "SECRET" not in out["error"], (body, got, out)
        assert post({"bank": {}, "price": 1}, "text/plain")[0] == 415
    finally:
        api.shutdown()
        srv.shutdown()
    print(f"model.py self-check passed: steps 1 and 2 on 100 personas ({val['exact']} of {val['months']} person-months exact, "
          f"{val['explained']} explained by lumpy purchases below GBP {ONE_OFF_GBP:.0f} and BNPL instalments); verdicts at GBP 300: {dict(seen)}; "
          f"endpoint verdicts at GBP 409: {verdicts}.")


if __name__ == "__main__":
    sys.modules["model"] = sys.modules[__name__]
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--serve", action="store_true", help="run POST /decide and GET /health on 127.0.0.1")
    ap.add_argument("--port", type=int, default=8765, help="port for --serve (default 8765)")
    ap.add_argument("--check", action="store_true", help="run the self-check (writes nothing)")
    args = ap.parse_args()
    if args.check:
        check()
    elif args.serve:
        try:
            serve(args.port).serve_forever()
        except KeyboardInterrupt:
            pass
    else:
        run()
