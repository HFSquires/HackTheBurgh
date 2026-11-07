"""Mock bank and Open Banking client (task T18).

The mock bank serves the persona statements in Analysis/mock_statements/ through UK Open Banking Read/Write API v3.1
account-information (AISP) endpoints. The client (`fetch`) reads one current account from such an endpoint and converts
it into exactly the transaction list that affordability.parse gives for a statement CSV.

MOCK ONLY. POST /mock/consent hands out a bearer token for any persona without authenticating anyone: it shows the data
flow, not secure banking. Real account access needs an FCA-authorised account information service provider (AISP) and
the customer's explicit consent, given to their own bank through the Open Banking (OAuth 2.0 / FAPI) redirect flow.

    python mock_bank.py --serve [--port 8766]   # mock bank on 127.0.0.1
    python mock_bank.py --check                 # self-check
"""
import argparse, datetime as dt, functools, http.client, json, os, re, secrets, statistics, sys, threading, time
import urllib.error, urllib.parse, urllib.request
from decimal import Decimal
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import affordability as af
from affordability import StatementError

API = "/open-banking/v3.1/aisp"
PAGE = 100  # transactions per page
TOKEN_LIFE = 3600  # seconds
MAX_RESPONSE = 5_000_000  # bytes the client reads from one bank response
FETCH_SECONDS, FETCH_BYTES, MAX_PAGES = 30, 20_000_000, 200  # limits on one whole fetch (all requests together)
DEFAULT_BANKS = ("http://127.0.0.1:8766", "http://localhost:8766")  # the mock bank's default --serve port
# ponytail: descriptive ISO 20022 BankTransactionCode names for the four statement types, not checked against the OB
# code list; the client trusts ProprietaryBankTransactionCode first. Upgrade with the bank's own code mapping.
ISO = {"BGC": ("ReceivedCreditTransfers", "DomesticCreditTransfer"), "DD": ("IssuedDirectDebits", "DirectDebitPayment"),
       "SO": ("IssuedCreditTransfers", "StandingOrder"), "DEB": ("CustomerCardTransactions", "PointOfSalePaymentDebitCard")}
ISO_TYPE = {v: k for k, v in ISO.items()}
PARAMS = {"fromBookingDateTime", "toBookingDateTime", "page"}
AMOUNT = re.compile(r"\d{1,13}(\.\d{1,5})?")


def amount(x):
    return {"Amount": f"{abs(x):.2f}", "Currency": "GBP"}


def stamp(d):
    return f"{d.isoformat()}T00:00:00+00:00"


# ---------------------------------------------------------------- mock bank
@functools.cache
def statement(pid):
    """(AccountId, sort code and account number, transactions) for a persona. Raises StatementError for an id not of
    the form persona000 or without exactly one statement (affordability.load_persona), so no path is built from input."""
    text = af.load_persona(pid)
    fields = text.lstrip("﻿").splitlines()[1].split(",")
    acc = next(af.STATEMENTS.glob(f"{pid}_*.csv")).stem[11:]  # the file's uuid8 is the AccountId
    return acc, re.sub(r"\D", "", fields[2]) + fields[3], af.parse(text)


def ob_transaction(acc, i, t):
    when = stamp(t["date"])
    code = {"BankTransactionCode": dict(zip(("Code", "SubCode"), ISO[t["type"]]))} if t["type"] in ISO else {}
    return {"AccountId": acc, "TransactionId": f"{acc}-{i:05d}", "CreditDebitIndicator": "Credit" if t["credit"] else "Debit",
            "Status": "Booked", "BookingDateTime": when, "ValueDateTime": when, "TransactionInformation": t["desc"],
            "Amount": amount(t["credit"] or t["debit"]), **code,
            "ProprietaryBankTransactionCode": {"Code": t["type"], "Issuer": "MockBank"},
            "Balance": {"Amount": amount(t["balance"]), "CreditDebitIndicator": "Credit" if t["balance"] >= 0 else "Debit",
                        "Type": "InterimBooked"}}


def mandates(acc, tx, kind):
    """Direct debits (kind DD) or standing orders (SO), one per description among that type's debits. Active = paid in
    the 35 days before the statement's last transaction. Standing orders: weekly when the median gap between payments
    is at most 10 days, otherwise monthly on the day of the most recent payment; next payment = most recent + 7 days
    or + 1 month, same amount. ponytail: the statement shows payments, not mandates, so first and final payment dates
    and payee accounts are unknown and omitted; annual orders are read as monthly."""
    groups = {}
    for t in tx:
        if t["type"] == kind and t["debit"] > 0:
            groups.setdefault(t["desc"], []).append(t)
    out = []
    for n, (name, g) in enumerate(groups.items(), start=1):
        last, ident = g[-1], f"{acc}-{kind}{n:02d}"
        status = "Active" if (tx[-1]["date"] - last["date"]).days <= 35 else "Inactive"
        if kind == "DD":
            out.append({"AccountId": acc, "DirectDebitId": ident, "MandateIdentification": f"MOCK{ident.upper()}",
                        "DirectDebitStatusCode": status, "Name": name, "PreviousPaymentDateTime": stamp(last["date"]),
                        "PreviousPaymentAmount": amount(last["debit"])})
            continue
        gaps = [(b["date"] - a["date"]).days for a, b in zip(g, g[1:])]
        weekly = bool(gaps) and statistics.median(gaps) <= 10
        so = {"AccountId": acc, "StandingOrderId": ident, "Reference": name, "StandingOrderStatusCode": status,
              "Frequency": f"IntrvlWkDay:01:{last['date'].isoweekday():02d}" if weekly
              else f"IntrvlMnthDay:01:{last['date'].day:02d}",
              "SupplementaryData": {"PreviousPaymentDateTime": stamp(last["date"]),
                                    "PreviousPaymentAmount": amount(last["debit"])}}
        if status == "Active":
            nxt = last["date"] + dt.timedelta(days=7) if weekly else af.add_months(last["date"], 1)
            so |= {"NextPaymentDateTime": stamp(nxt), "NextPaymentAmount": amount(last["debit"])}
        out.append(so)
    return out


def when(v, name):
    """Query date-time -> aware datetime (naive values are read as UTC)."""
    try:
        d = dt.datetime.fromisoformat(v)
    except ValueError:
        raise StatementError(f"{name} must be an ISO 8601 date-time such as 2026-09-01T00:00:00 (encode + as %2B).") from None
    return d if d.tzinfo else d.replace(tzinfo=dt.timezone.utc)


class Handler(BaseHTTPRequestHandler):
    def send(self, code, obj, extra=()):
        body = json.dumps(obj, indent=1).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        for k, v in extra:
            self.send_header(k, v)
        self.cors()
        self.end_headers()
        self.wfile.write(body)

    def fail(self, code, err, msg):
        """Open Banking error response (OBErrorResponse1)."""
        self.send(code, {"Code": f"{code} {HTTPStatus(code).phrase}", "Id": secrets.token_hex(8), "Message": msg,
                         "Errors": [{"ErrorCode": err, "Message": msg}]},
                  [("WWW-Authenticate", "Bearer")] if code == 401 else ())

    def cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")

    def do_OPTIONS(self):  # CORS preflight from the extension
        self.send_response(204)
        self.cors()
        self.end_headers()

    def do_POST(self):
        if self.path != "/mock/consent":
            return self.fail(404, "UK.OBIE.Resource.NotFound", "Unknown path; POST /mock/consent.")
        try:
            size = self.headers.get("Content-Length", "")
            size = int(size) if size.isdigit() else 0
            if not 0 < size <= 1000:
                raise StatementError("Send a JSON body of at most 1000 bytes.")
            try:
                req = json.loads(self.rfile.read(size))
            except (json.JSONDecodeError, UnicodeDecodeError, RecursionError):
                raise StatementError("The body is not valid JSON.") from None
            if not isinstance(req, dict) or set(req) != {"persona"}:
                raise StatementError('Send {"persona": "persona050"}.')
            acc = statement(req["persona"])[0]
        except StatementError as e:
            return self.fail(400, "UK.OBIE.Field.Invalid", str(e))
        token, now = secrets.token_urlsafe(32), time.time()
        with self.server.lock:
            self.server.tokens = {k: v for k, v in self.server.tokens.items() if v[1] > now}
            self.server.tokens[token] = (req["persona"], now + TOKEN_LIFE)
        self.send(201, {"access_token": token, "token_type": "Bearer", "expires_in": TOKEN_LIFE, "accountId": acc,
                        "note": "Mock consent: no customer authentication. Real access needs an FCA-authorised AISP "
                                "and the customer's consent through their bank."})

    def do_GET(self):
        url = urllib.parse.urlsplit(self.path)
        m = re.fullmatch(re.escape(API) + r"/accounts(?:/([^/]+)(?:/(balances|transactions|direct-debits|standing-orders))?)?",
                         url.path)
        if not m:
            return self.fail(404, "UK.OBIE.Resource.NotFound", f"Unknown path; use {API}/accounts[/{{AccountId}}[/...]].")
        auth = self.headers.get("Authorization")
        tok = re.fullmatch(r"Bearer ([A-Za-z0-9_-]{20,100})", auth or "")
        with self.server.lock:
            entry = self.server.tokens.get(tok[1]) if tok else None
        if not entry or entry[1] <= time.time():
            return self.fail(401, "UK.OBIE.Header.Missing" if auth is None else "UK.OBIE.Header.Invalid",
                             "Send Authorization: Bearer <token> from POST /mock/consent (tokens expire after an hour).")
        acc, ident, tx = statement(entry[0])
        if m[1] is not None and m[1] != acc:
            if not re.fullmatch(r"[0-9a-f]{8}", m[1]):
                return self.fail(400, "UK.OBIE.Field.Invalid", "AccountId must be 8 lower-case hexadecimal characters.")
            return self.fail(403, "UK.OBIE.Resource.ConsentMismatch", "This token does not cover that account.")
        if url.query and m[2] != "transactions":
            return self.fail(400, "UK.OBIE.Field.Unexpected", "This endpoint takes no query parameters.")
        host = self.headers.get("Host", "")
        if not re.fullmatch(r"(127\.0\.0\.1|localhost)(:\d{1,5})?", host):
            host = f"127.0.0.1:{self.server.server_port}"
        links, meta = {"Self": f"http://{host}{self.path}"}, {"TotalPages": 1}
        if m[2] is None:
            data = {"Account": [{"AccountId": acc, "Status": "Enabled", "Currency": "GBP", "AccountType": "Personal",
                                 "AccountSubType": "CurrentAccount", "Nickname": f"Mock current account ({entry[0]})",
                                 "Account": [{"SchemeName": "UK.OBIE.SortCodeAccountNumber", "Identification": ident,
                                              "Name": entry[0]}]}]}
        elif m[2] == "balances":
            b = tx[-1]["balance"]
            data = {"Balance": [{"AccountId": acc, "Amount": amount(b), "CreditDebitIndicator": "Credit" if b >= 0 else
                                 "Debit", "Type": "InterimBooked", "DateTime": stamp(tx[-1]["date"])}]}
        elif m[2] == "direct-debits":
            data = {"DirectDebit": mandates(acc, tx, "DD")}
        elif m[2] == "standing-orders":
            data = {"StandingOrder": mandates(acc, tx, "SO")}
        else:
            try:
                q = urllib.parse.parse_qs(url.query, keep_blank_values=True, max_num_fields=10)
                if set(q) - PARAMS or any(len(v) > 1 for v in q.values()):
                    raise StatementError(f"Query parameters allowed once each: {', '.join(sorted(PARAMS))}.")
                q = {k: v[0] for k, v in q.items()}
                lo = when(q["fromBookingDateTime"], "fromBookingDateTime") if "fromBookingDateTime" in q else None
                hi = when(q["toBookingDateTime"], "toBookingDateTime") if "toBookingDateTime" in q else None
                if lo and hi and lo > hi:
                    raise StatementError("fromBookingDateTime is after toBookingDateTime.")
                rows = [ob_transaction(acc, i, t) for i, t in enumerate(tx, start=1)]
                rows = [r for r in reversed(rows)  # newest first, as many banks return them
                        if (not lo or lo <= dt.datetime.fromisoformat(r["BookingDateTime"]))
                        and (not hi or dt.datetime.fromisoformat(r["BookingDateTime"]) <= hi)]
                pages = max(1, -(-len(rows) // PAGE))
                page = q.get("page", "1")
                if not re.fullmatch(r"[1-9]\d{0,5}", page) or int(page) > pages:
                    raise StatementError(f"page must be a whole number from 1 to {pages}.")
            except (StatementError, ValueError) as e:
                return self.fail(400, "UK.OBIE.Field.Invalid", str(e))
            page = int(page)
            data = {"Transaction": rows[(page - 1) * PAGE:page * PAGE]}
            link = lambda p: f"http://{host}{url.path}?" + urllib.parse.urlencode({**q, "page": p})
            links = {"Self": link(page), "First": link(1), "Last": link(pages),
                     **({"Prev": link(page - 1)} if page > 1 else {}), **({"Next": link(page + 1)} if page < pages else {})}
            meta = {"TotalPages": pages, "FirstAvailableDateTime": stamp(tx[0]["date"]),
                    "LastAvailableDateTime": stamp(tx[-1]["date"])}
        self.send(200, {"Data": data, "Links": links, "Meta": meta})

    def log_message(self, *a):
        pass


def serve(port, quiet=False):
    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    srv.tokens, srv.lock = {}, threading.Lock()  # token -> (persona, expiry); in memory, lost on restart
    if not quiet:
        print(f"Mock bank (Open Banking v3.1 AISP shapes, NOT a real bank) on http://127.0.0.1:{srv.server_port}"
              f"{API} (Ctrl+C to stop)")
    return srv


# ---------------------------------------------------------------- client
class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a):  # a redirect becomes an error, so a bank response cannot send us to another host
        return None


OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect)


def origin(url):
    """(origin 'scheme://host:port', in lower case with an explicit port, and the urlsplit parts) of an http(s) URL made
    only of printable ASCII, without userinfo or fragment; None for anything else. Validating the raw string matters:
    urlsplit silently drops tabs and newlines that urllib would then reject."""
    if not isinstance(url, str) or not re.fullmatch(r"[\x21-\x7e]{1,4096}", url):
        return None
    try:
        u = urllib.parse.urlsplit(url)
        port = u.port or {"http": 80, "https": 443}.get(u.scheme)
    except ValueError:
        return None
    if u.scheme not in ("http", "https") or not u.hostname or not port or "@" in u.netloc or u.fragment:
        return None
    host = f"[{u.hostname}]" if ":" in u.hostname else u.hostname
    return f"{u.scheme}://{host}:{port}", u


def bank_url(base):
    """The bank's normalised origin, 'scheme://host:port'. Only exact origins are allowed: DEFAULT_BANKS (the mock bank
    on port 8766) and the comma-separated origins in the environment variable BANK_ALLOWED_HOSTS (for example
    'http://127.0.0.1:9000,https://bank.example:443'); no path, query or other port.
    ponytail: a demo allow-list. In production the back end talks only to an FCA-authorised AISP such as TrueLayer,
    with OAuth consent and tokens held server-side, never a URL or token sent by the browser."""
    allowed = {o[0] for h in (*DEFAULT_BANKS, *os.environ.get("BANK_ALLOWED_HOSTS", "").split(",")) if (o := origin(h.strip()))}
    o = origin(base)
    if not o or o[1].path not in ("", "/") or o[1].query or o[0] not in allowed:
        raise StatementError(f"bank.baseUrl must be an allowed bank origin with no path, such as {DEFAULT_BANKS[0]} "
                             "(others only when listed in BANK_ALLOWED_HOSTS).")
    return o[0]


class Budget:
    """Time and bytes left for one whole fetch, shared by all its requests."""
    def __init__(self, seconds=FETCH_SECONDS, size=FETCH_BYTES):
        self.end, self.left = time.monotonic() + seconds, size

    def timeout(self):
        """Seconds for the next socket operation (at most 10); raises once the fetch has run out of time."""
        t = self.end - time.monotonic()
        if t <= 0:
            raise StatementError("The bank took too long to respond.")
        return min(10.0, t)

    def take(self, n):
        self.left -= n
        if self.left < 0:
            raise StatementError("The bank sent more data than expected.")
        self.timeout()


def call(url, token=None, body=None, budget=None):
    """GET (or POST `body`) one JSON resource within `budget` (default: a fresh Budget); every failure becomes a
    StatementError whose message holds the HTTP status at most, never text from the bank."""
    budget = budget or Budget()
    head = {"Accept": "application/json"} | ({"Authorization": f"Bearer {token}"} if token else {}) | (
        {"Content-Type": "application/json"} if body else {})
    try:
        with OPENER.open(urllib.request.Request(url, data=body, headers=head), timeout=budget.timeout()) as r:
            chunks, size = [], 0
            while chunk := r.read1(65536):  # one socket read at a time, so the budget's deadline is checked often
                chunks.append(chunk)
                size += len(chunk)
                budget.take(len(chunk))
                if size > MAX_RESPONSE:
                    raise StatementError("A bank response was larger than expected.")
    except StatementError:
        raise
    except urllib.error.HTTPError as e:
        e.close()
        raise StatementError(f"The bank returned HTTP {e.code}.") from None
    except (urllib.error.URLError, OSError, http.client.HTTPException, ValueError):
        raise StatementError("Could not read a response from the bank.") from None
    try:
        return json.loads(b"".join(chunks))
    except (ValueError, RecursionError):
        raise StatementError("A bank response was not JSON.") from None


def pennies(a):
    """OB amount string -> whole pence (raises on a malformed or sub-penny amount)."""
    if not isinstance(a, str) or not AMOUNT.fullmatch(a) or (Decimal(a) * 100) % 1:
        raise ValueError(f"bad amount {a!r}")
    return int(Decimal(a) * 100)


def signed(b):
    if b["CreditDebitIndicator"] not in ("Credit", "Debit"):
        raise ValueError("bad CreditDebitIndicator")
    return pennies(b["Amount"]["Amount"]) * (-1 if b["CreditDebitIndicator"] == "Debit" else 1)


def read_account(base, token, budget=None):
    """(transactions, balances, direct debits, standing orders) of the token's one current account; follows Links.Next
    across at most MAX_PAGES transaction pages, only to the origin `base` (from bank_url) and never to a page already
    read, all within one Budget."""
    budget, api = budget or Budget(), base + API
    accounts = [a for a in call(api + "/accounts", token, budget=budget)["Data"]["Account"]
                if a.get("AccountSubType") == "CurrentAccount"]
    if len(accounts) != 1:  # ponytail: one current account per consent; upgrade by letting the user pick an AccountId
        raise StatementError(f"Expected one current account, found {len(accounts)}.")
    acc = f"{api}/accounts/{urllib.parse.quote(str(accounts[0]['AccountId']), safe='')}"
    rows, url, seen = [], acc + "/transactions", set()
    for _ in range(MAX_PAGES):
        seen.add(url)
        page = call(url, token, budget=budget)
        rows += page["Data"].get("Transaction", [])
        url = (page.get("Links") or {}).get("Next")
        if not url:
            break
        if (origin(url) or [None])[0] != base:
            raise StatementError("A transactions page linked outside the bank's base URL.")
        if url in seen:
            raise StatementError("The bank's transaction pages link back to a page already read.")
    else:
        raise StatementError("Too many transaction pages.")
    return (rows, call(acc + "/balances", token, budget=budget)["Data"]["Balance"],
            call(acc + "/direct-debits", token, budget=budget)["Data"].get("DirectDebit", []),
            call(acc + "/standing-orders", token, budget=budget)["Data"].get("StandingOrder", []))


def to_transactions(rows, balances, direct_debits=(), standing_orders=()):
    """Booked OB transactions -> the affordability.parse transaction list (date, type, desc, debit, credit, balance),
    oldest first. type = ProprietaryBankTransactionCode.Code, else the statement type of the ISO BankTransactionCode,
    else DD or SO when the description names a direct debit or standing order, else DEB for a debit and BGC for a
    credit. Running balances are rebuilt backwards from the InterimBooked (else ClosingBooked) balance; any balance the
    bank gives per transaction must agree to the penny. Order: a list whose first row is dated after its last is
    reversed; when every row has the same date, the order (newest first, as the mock bank sends it, or as given) that
    reconciles with the per-transaction balances is used, newest first when there are none. ponytail: pending
    transactions are ignored, and same-day order is otherwise the bank's; upgrade with the provider's own ordering key."""
    try:
        names = {d["Name"]: "DD" for d in direct_debits} | {s["Reference"]: "SO" for s in standing_orders if "Reference" in s}
        closing = next((b for kind in ("InterimBooked", "ClosingBooked") for b in balances if b["Type"] == kind), None)
        if closing is None:
            raise StatementError("The bank gave no InterimBooked or ClosingBooked balance.")
        tx = []
        for r in rows:
            if r["Status"] != "Booked":
                continue
            p, debit = pennies(r["Amount"]["Amount"]), r["CreditDebitIndicator"] == "Debit"
            if r["CreditDebitIndicator"] not in ("Credit", "Debit"):
                raise ValueError("bad CreditDebitIndicator")
            desc = str(r.get("TransactionInformation", "")).strip()
            code = ((r.get("ProprietaryBankTransactionCode") or {}).get("Code")
                    or ISO_TYPE.get(tuple((r.get("BankTransactionCode") or {}).get(k) for k in ("Code", "SubCode")))
                    or (names.get(desc) if debit else None) or ("DEB" if debit else "BGC"))
            tx.append(dict(date=dt.datetime.fromisoformat(r["BookingDateTime"]).date(), type=str(code).strip().upper(),
                           desc=desc, debit=p / 100 if debit else 0.0, credit=0.0 if debit else p / 100,
                           balance=signed(r["Balance"]) if r.get("Balance") else None, change=-p if debit else p))
        bal = signed(closing)
    except (KeyError, TypeError, ValueError, AttributeError) as e:
        raise StatementError(f"The bank's data are not in the expected Open Banking shape ({e}).") from None
    if not tx:
        raise StatementError("The bank returned no booked transactions.")
    first, last = tx[0]["date"], tx[-1]["date"]
    for order in [tx[::-1]] if first > last else [tx] if first < last else [tx[::-1], tx]:
        try:
            return rebuild(order, bal)
        except StatementError as e:
            err = e
    raise err


def rebuild(tx, bal):
    """`tx` sorted by date (stable: same-day order kept), with running balances rebuilt backwards from the closing
    balance `bal` [pence]; raises when a per-transaction balance disagrees."""
    out = []
    for t in reversed(sorted(tx, key=lambda t: t["date"])):
        if t["balance"] is not None and t["balance"] != bal:
            raise StatementError(f"The bank's running balance on {t['date']} does not reconcile with its closing balance "
                                 "and transactions.")
        out.append({k: v for k, v in t.items() if k != "change"} | {"balance": bal / 100})
        bal -= t["change"]
    return out[::-1]


def fetch(base_url, token=None, persona=None):
    """Transactions of the one current account behind `token`, or behind a mock consent for `persona`, from the Open
    Banking AISP API at `base_url`, as affordability.parse would give them from the CSV."""
    base, budget = bank_url(base_url), Budget()
    if (token is None) == (persona is None):
        raise StatementError('bank needs "baseUrl" and exactly one of "token" or "persona".')
    if persona is not None:
        if not isinstance(persona, str) or not re.fullmatch(r"persona\d{3}", persona):
            raise StatementError("bank.persona must look like 'persona079'.")
        consent = call(base + "/mock/consent", body=json.dumps({"persona": persona}).encode(), budget=budget)
        token = consent.get("access_token") if isinstance(consent, dict) else None
    if not isinstance(token, str) or not re.fullmatch(r"[\x21-\x7e]{1,4096}", token):
        raise StatementError("bank.token must be a printable bearer token.")
    try:
        account = read_account(base, token, budget)
    except (KeyError, TypeError, AttributeError, IndexError) as e:
        raise StatementError(f"The bank's data are not in the expected Open Banking shape ({e!r}).") from None
    return to_transactions(*account)


# ---------------------------------------------------------------- self-check
def check_t23(base):
    """T23 review regressions, against the running mock bank at `base` and a misbehaving local server."""
    def fails(f, *a, **k):
        try:
            f(*a, **k)
        except StatementError as e:
            return str(e)
        raise AssertionError(f"{f.__name__} accepted {a} {k}")

    # Exact allow-listed origins only (default: the mock bank on 8766), normalised; no path, no other port.
    env = os.environ.pop("BANK_ALLOWED_HOSTS")
    try:
        assert bank_url("HTTP://LOCALHOST:8766/") == "http://localhost:8766" and bank_url(DEFAULT_BANKS[0]) == DEFAULT_BANKS[0]
        for u in ("http://127.0.0.1:8765", "http://127.0.0.1:8766/internal/admin", "http://127.0.0.1", base,
                  "http://127.0.0.1:8766/?x", "http://[::1]:8766"):
            fails(bank_url, u)
        os.environ["BANK_ALLOWED_HOSTS"] = "https://Bank.Example, http://127.0.0.1:9000, not a url"
        assert bank_url("https://bank.example") == "https://bank.example:443" == bank_url("https://BANK.example:443/")
        assert bank_url("http://127.0.0.1:9000") == "http://127.0.0.1:9000"
        fails(bank_url, "http://bank.example:443")
    finally:
        os.environ["BANK_ALLOWED_HOSTS"] = env

    # Case: an upper-case scheme or host is the same origin, so a second transactions page is followed. (The scheme is
    # tested live because "localhost" costs about 2 s per connection on Windows: ::1 is tried first, the mock is IPv4.)
    assert fetch(base.replace("http", "HTTP"), persona="persona050") == af.parse(af.load_persona("persona050"))
    assert bank_url(base.replace("127.0.0.1", "LOCALHOST")) == base.replace("127.0.0.1", "localhost")

    # Same-day feed (one date only, newest first from the mock): order chosen by the per-transaction balances.
    c = call(base + "/mock/consent", body=b'{"persona": "persona001"}')
    acc, tok = c["accountId"], c["access_token"]
    rows = call(f"{base}{API}/accounts/{acc}/transactions?fromBookingDateTime=2026-10-31T00:00:00", tok)["Data"]["Transaction"]
    bal = call(f"{base}{API}/accounts/{acc}/balances", tok)["Data"]["Balance"]
    want = [t for t in af.parse(af.load_persona("persona001")) if t["date"] == dt.date(2026, 10, 31)]
    assert len(rows) == len(want) >= 2 and len({t["desc"] for t in want}) == len(want)
    bare = [{k: v for k, v in r.items() if k != "Balance"} for r in rows]
    assert to_transactions(rows, bal) == want == to_transactions(rows[::-1], bal) == to_transactions(bare, bal)

    # A misbehaving server: looping pages, a slow drip, bad framing, deep nesting, an error banner.
    hits = []

    class Bad(BaseHTTPRequestHandler):
        def do_GET(self):
            hits.append(self.path)
            try:
                if self.path == "/drip":  # one byte every 0.25 s
                    self.send_response(200)
                    self.send_header("Content-Length", "20")
                    self.end_headers()
                    for _ in range(20):
                        time.sleep(0.25)
                        self.wfile.write(b" ")
                        self.wfile.flush()
                    return
                if self.path == "/chunked":
                    self.send_response(200)
                    self.send_header("Transfer-Encoding", "chunked")
                    self.end_headers()
                    return self.wfile.write(b"zz\r\nabc")
                code, body = 200, b"[" * 200_000
                if self.path.endswith("/accounts"):
                    body = json.dumps({"Data": {"Account": [{"AccountId": "a", "AccountSubType": "CurrentAccount"}]}})
                elif self.path.endswith("/transactions"):  # Next points back at this page
                    body = json.dumps({"Data": {"Transaction": []},
                                       "Links": {"Next": f"http://127.0.0.1:{self.server.server_port}{self.path}"}})
                elif self.path == "/secret":
                    code, body = 403, json.dumps({"Message": "SECRET-internal-banner"})
                body = body.encode() if isinstance(body, str) else body
                self.send_response(code)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            except OSError:
                pass  # the client gave up

        def log_message(self, *a):
            pass

    bad_srv = ThreadingHTTPServer(("127.0.0.1", 0), Bad)
    threading.Thread(target=bad_srv.serve_forever, daemon=True).start()
    bad = f"http://127.0.0.1:{bad_srv.server_port}"
    try:
        assert "already read" in fails(read_account, bad, "t" * 30) and len(hits) == 2, hits
        t0 = time.monotonic()
        assert "too long" in fails(call, bad + "/drip", budget=Budget(seconds=1)) and time.monotonic() - t0 < 3
        assert "more data" in fails(call, bad + "/deep", budget=Budget(size=1000))
        assert "not JSON" in fails(call, bad + "/deep")  # RecursionError inside json.loads
        fails(call, bad + "/chunked")                    # http.client.IncompleteRead
        fails(call, bad + "/a b")                        # http.client.InvalidURL
        msg = fails(call, bad + "/secret")
        assert msg == "The bank returned HTTP 403." and "SECRET" not in msg
        assert fails(call, "http://127.0.0.1:1/x") == "Could not read a response from the bank."
    finally:
        bad_srv.shutdown()


def check():
    srv = serve(0, quiet=True)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_port}"
    os.environ["BANK_ALLOWED_HOSTS"] = f"{base},http://localhost:{srv.server_port}"  # the check's ephemeral port

    def status(path, token=None, body=None):
        try:
            call(base + path, token, body)
        except StatementError as e:
            return int(re.search(r"returned HTTP (\d+)", str(e))[1]) if "returned" in str(e) else str(e)
        return 200

    try:
        check_t23(base)
        pids = [p["id"] for p in af.personas()]
        assert len(pids) >= 10
        multi = 0
        for pid in pids:  # every persona: API -> engine transactions equal the CSV parse exactly
            assert fetch(base, persona=pid) == af.parse(af.load_persona(pid)), pid
        for pid in pids[::10]:  # a sparse feed: no per-transaction balances or bank codes, oldest first
            token = call(base + "/mock/consent", body=json.dumps({"persona": pid}).encode())["access_token"]
            rows, bal, dds, sos = read_account(base, token)
            multi += call(f"{base}{API}/accounts/{rows[0]['AccountId']}/transactions", token)["Meta"]["TotalPages"] > 1
            bare = [{k: v for k, v in r.items() if k not in ("Balance", "BankTransactionCode",
                                                            "ProprietaryBankTransactionCode")} for r in reversed(rows)]
            assert to_transactions(bare, bal, dds, sos) == af.parse(af.load_persona(pid)), pid
            rows[5] = rows[5] | {"Balance": rows[5]["Balance"] | {"Amount": amount(1e6)}}
            try:
                to_transactions(rows, bal, dds, sos)
            except StatementError as e:
                assert "reconcile" in str(e)
            else:
                raise AssertionError("accepted an unreconciled balance")
        assert multi, "no persona needed a second transactions page"

        # Derived mandates (persona050: rent by standing order on the 1st, five monthly direct debits).
        a = call(base + "/mock/consent", body=b'{"persona": "persona050"}')
        b = call(base + "/mock/consent", body=b'{"persona": "persona051"}')
        acc, tok = a["accountId"], a["access_token"]
        accounts = call(f"{base}{API}/accounts", tok)
        assert [x["AccountId"] for x in accounts["Data"]["Account"]] == [acc] and accounts["Meta"]["TotalPages"] == 1
        so = call(f"{base}{API}/accounts/{acc}/standing-orders", tok)["Data"]["StandingOrder"]
        assert [(s["Reference"], s["Frequency"], s["NextPaymentDateTime"][:10], s["NextPaymentAmount"]["Amount"])
                for s in so] == [("RENT LETTING AGENT", "IntrvlMnthDay:01:01", "2026-11-01", "1001.86")], so
        dd = call(f"{base}{API}/accounts/{acc}/direct-debits", tok)["Data"]["DirectDebit"]
        assert {d["Name"] for d in dd} == {t["desc"] for t in statement("persona050")[2] if t["type"] == "DD"}
        assert all(d["DirectDebitStatusCode"] == "Active" and d["PreviousPaymentDateTime"].startswith("2026-10") for d in dd)
        bal = call(f"{base}{API}/accounts/{acc}/balances", tok)["Data"]["Balance"][0]
        assert bal["Type"] == "InterimBooked" and float(bal["Amount"]["Amount"]) == abs(statement("persona050")[2][-1]["balance"])

        # Date filters, inclusive, across the month of September.
        tx = statement("persona050")[2]
        sept = call(f"{base}{API}/accounts/{acc}/transactions?fromBookingDateTime=2026-09-01T00:00:00"
                    "&toBookingDateTime=2026-09-30T23:59:59", tok)
        got = [r["BookingDateTime"][:10] for r in sept["Data"]["Transaction"]]
        assert got and all("2026-09-01" <= d <= "2026-09-30" for d in got) and "Next" not in sept["Links"]
        assert len(got) == sum(t["date"].month == 9 for t in tx)
        late = call(f"{base}{API}/accounts/{acc}/transactions?fromBookingDateTime=2026-10-25T00:00:00Z", tok)
        assert len(late["Data"]["Transaction"]) == sum(t["date"] >= dt.date(2026, 10, 25) for t in tx)

        # Authentication, isolation and validation.
        acc_b, path = b["accountId"], f"{API}/accounts/{acc}/transactions"
        assert status(path) == 401 and status(path, "x" * 40) == 401
        assert status(f"{API}/accounts/{acc_b}", tok) == 403 == status(f"{API}/accounts/{acc_b}/transactions", tok)
        assert [x["AccountId"] for x in call(f"{base}{API}/accounts", b["access_token"])["Data"]["Account"]] == [acc_b]
        with srv.lock:
            srv.tokens[tok] = (srv.tokens[tok][0], time.time() - 1)  # expire persona050's token
        assert status(path, tok) == 401
        tok = call(base + "/mock/consent", body=b'{"persona": "persona050"}')["access_token"]
        req = urllib.request.Request(base + path, headers={"Authorization": f"Basic {tok}"})
        try:
            OPENER.open(req)
        except urllib.error.HTTPError as e:
            err = json.load(e)
            assert e.code == 401 and err["Errors"][0]["ErrorCode"] == "UK.OBIE.Header.Invalid"
            assert e.headers["Access-Control-Allow-Origin"] == "*"
        else:
            raise AssertionError("accepted a Basic token")
        for body in (b'{"persona": "persona05"}', b'{"persona": "../persona050"}', b'{"persona": "persona999"}',
                     b'{"persona": "persona050/../persona051"}', b'{"persona": 50}', b"not json",
                     b'{"persona": "persona050", "x": 1}', b'{"persona": "persona*"}'):
            assert status("/mock/consent", body=body) == 400, body
        for p in (f"{API}/accounts/../../../../etc/passwd", f"{API}/accounts/%2e%2e%2f{acc_b}",
                  f"{API}/accounts/{acc}/../{acc_b}/transactions", f"{API}/accounts/{acc}/transactions/../../{acc_b}",
                  f"{API}/accounts/{acc}/", "/../Analysis/mock_statements/personas.md", f"{API}/accounts/ABCDEF12"):
            assert status(p, tok) in (400, 403, 404), p
        for q in ("fromBookingDateTime=2026-13-01", "page=0", "page=9", "toBookingDateTime=x", "foo=1",
                  "page=1&page=2", "fromBookingDateTime=2026-10-01&toBookingDateTime=2026-09-01"):
            assert status(f"{path}?{q}", tok) == 400, q
        assert status(f"{API}/accounts/{acc}/balances?page=1", tok) == 400
        for url in ("http://example.com", "https://127.0.0.1:1", "file:///etc/passwd", "http://127.0.0.1@example.com",
                    "http://localhost:99999", None, 5, base + "?x=1", "http://127.0.0.1:1", base + "/internal/admin",
                    base + "/a b", base[:-2] + "\n" + base[-2:], base + "#x", f"http://user@127.0.0.1:{srv.server_port}"):
            try:
                fetch(url, persona="persona050")
            except StatementError:
                pass
            else:
                raise AssertionError(f"accepted base URL {url!r}")
        for kw in (dict(), dict(token=tok, persona="persona050"), dict(persona="x"), dict(token="bad token")):
            try:
                fetch(base, **kw)
            except StatementError:
                pass
            else:
                raise AssertionError(f"accepted {kw}")
        assert fetch(base.replace("127.0.0.1", "localhost"), token=tok) == af.parse(af.load_persona("persona050"))
    finally:
        srv.shutdown()
    print(f"Mock bank self-check passed: {len(pids)} personas read through the Open Banking API match their CSVs.")


if __name__ == "__main__":
    sys.modules["mock_bank"] = sys.modules[__name__]  # affordability imports mock_bank; keep one copy
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--serve", action="store_true", help="run the mock bank on 127.0.0.1")
    ap.add_argument("--port", type=int, default=8766, help="port for --serve (default 8766)")
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
