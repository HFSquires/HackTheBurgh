"""Mock bank and Open Banking client (tasks T18 and T21).

The mock bank serves synthetic persona data through UK Open Banking Read/Write API v3.1 account-information (AISP)
endpoints, from one of two sources (--source):

  v1 (default): the statement CSVs in Analysis/mock_statements/, one current account per persona, under
      /open-banking/v3.1/aisp. The client `fetch` reads that one current account and converts it into exactly the
      transaction list that statements.parse gives for the CSV.
  v2: the generation-2 data in Analysis/open_banking/*.json (ob_generator.py, task T20): 1 to 7 accounts per persona
      at the fictional providers MockBank, MockDigital and MockCards, each provider's API under
      /providers/{Provider}/open-banking/v3.1/aisp, as an aggregator presents several banks. The generator's objects
      are served as they are. The client `fetch_customer` reads every account at every provider into a customer
      picture (account types, balances and credit lines, product rates, mandates, scheduled and pending payments, and
      booked transactions in statements.parse's format); `from_request` validates a request's "bank" object and
      fetches accordingly (the old engine's POST /assess was archived on 7 November 2026, task T29).

MOCK ONLY. POST /mock/consent hands out bearer tokens for any persona without authenticating anyone: it shows the data
flow, not secure banking. Each token covers one persona at one provider (v2: one token per provider, as each bank
authorises access to its own accounts). Real account access needs an FCA-authorised account information service
provider (AISP) and the customer's explicit consent, given to each bank through the Open Banking (OAuth 2.0 / FAPI)
redirect flow.

    python mock_bank.py --serve [--port 8766] [--source v1|v2]   # mock bank on 127.0.0.1
    python mock_bank.py --check [--source v1|v2]                 # self-check (default: both sources)
"""
import argparse, csv, datetime as dt, functools, http.client, json, os, re, secrets, statistics, sys, threading, time
import urllib.error, urllib.parse, urllib.request
from decimal import Decimal
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import statements as af
from statements import StatementError

API = "/open-banking/v3.1/aisp"
OB_DIR = af.HERE / "Analysis" / "open_banking"  # v2 data, written by ob_generator.py
PROVIDERS = ("MockBank", "MockDigital", "MockCards")  # v2's fictional providers (ob_generator.ACCOUNTS)
ROUTE = re.compile(r"(?:/providers/([^/]+))?" + re.escape(API) + r"/accounts(?:/([^/]+)(?:/([a-z-]+))?)?")
RESOURCES = {"balances": "Balance", "transactions": "Transaction", "direct-debits": "DirectDebit",
             "standing-orders": "StandingOrder", "scheduled-payments": "ScheduledPayment", "product": "Product"}
V1_RESOURCES = {"balances", "transactions", "direct-debits", "standing-orders"}
PAGE = 100  # transactions per page
TOKEN_LIFE = 3600  # seconds
MAX_RESPONSE = 5_000_000  # bytes the client reads from one bank response
FETCH_SECONDS, FETCH_BYTES, MAX_PAGES = 30, 20_000_000, 200  # limits on one whole fetch (all requests together)
MAX_PROVIDERS = 10  # providers in one customer fetch
DEFAULT_BANKS = ("http://127.0.0.1:8766", "http://localhost:8766")  # the mock bank's default --serve port
# ponytail: descriptive ISO 20022 BankTransactionCode names for the four statement types, not checked against the OB
# code list; the client trusts ProprietaryBankTransactionCode first. Upgrade with the bank's own code mapping.
ISO = {"BGC": ("ReceivedCreditTransfers", "DomesticCreditTransfer"), "DD": ("IssuedDirectDebits", "DirectDebitPayment"),
       "SO": ("IssuedCreditTransfers", "StandingOrder"), "DEB": ("CustomerCardTransactions", "PointOfSalePaymentDebitCard")}
ISO_TYPE = {v: k for k, v in ISO.items()}
PARAMS = {"fromBookingDateTime", "toBookingDateTime", "page"}
AMOUNT = re.compile(r"\d{1,13}(\.\d{1,5})?")
PERSONA = re.compile(r"persona\d{3}")
PROVIDER = re.compile(r"[A-Za-z][A-Za-z0-9]{0,39}")  # a provider name the client may put in a URL path
TOKEN = re.compile(r"[\x21-\x7e]{1,4096}")
NOTE = ("Mock consent: no customer authentication. Real access needs an FCA-authorised AISP and the customer's consent "
        "through their bank.")


def amount(x):
    return {"Amount": f"{abs(x):.2f}", "Currency": "GBP"}


def stamp(d):
    return f"{d.isoformat()}T00:00:00+00:00"


# ---------------------------------------------------------------- mock bank
@functools.cache
def statement(pid):
    """(AccountId, sort code and account number, transactions) for a persona. Raises StatementError for an id not of
    the form persona000 or without exactly one statement (statements.load_persona), so no path is built from input."""
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


@functools.cache
def v1_data(pid):
    """v1 source: ({None: OB Data}, Meta) for a persona's statement CSV: one current account at one unnamed provider,
    with its balance, direct debits and standing orders derived from the statement."""
    acc, ident, tx = statement(pid)
    b = tx[-1]["balance"]
    data = {"Account": [{"AccountId": acc, "Status": "Enabled", "Currency": "GBP", "AccountType": "Personal",
                         "AccountSubType": "CurrentAccount", "Nickname": f"Mock current account ({pid})",
                         "Account": [{"SchemeName": "UK.OBIE.SortCodeAccountNumber", "Identification": ident,
                                      "Name": pid}]}],
            "Balance": [{"AccountId": acc, "Amount": amount(b), "CreditDebitIndicator": "Credit" if b >= 0 else "Debit",
                         "Type": "InterimBooked", "DateTime": stamp(tx[-1]["date"])}],
            "DirectDebit": mandates(acc, tx, "DD"), "StandingOrder": mandates(acc, tx, "SO"),
            "Transaction": [ob_transaction(acc, i, t) for i, t in enumerate(tx, start=1)]}
    return {None: data}, {"FirstAvailableDateTime": stamp(tx[0]["date"]), "LastAvailableDateTime": stamp(tx[-1]["date"])}


@functools.lru_cache(maxsize=16)  # about 0.5 MB of JSON per persona
def v2_data(pid):
    """v2 source: ({provider: OB Data}, Meta) for a persona, exactly as ob_generator.py wrote them. Raises StatementError
    for an id not of the form persona000 or without exactly one file, so no path is built from input."""
    if not isinstance(pid, str) or not PERSONA.fullmatch(pid):
        raise StatementError("persona must look like 'persona079'.")
    files = list(OB_DIR.glob(f"{pid}_*.json"))
    if len(files) != 1:
        raise StatementError(f"No Open Banking data for {pid}.")
    doc = json.loads(files[0].read_text(encoding="utf-8"))
    return {b["Provider"]: b["Data"] for b in doc["Providers"]}, doc["Meta"]


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
            v2 = self.server.v2
            if not isinstance(req, dict) or "persona" not in req or not set(req) <= {"persona", *(["provider"] if v2 else [])}:
                raise StatementError('Send {"persona": "persona050"}' + (', optionally with "provider".' if v2 else "."))
            pid = req["persona"]
            if not isinstance(pid, str) or not PERSONA.fullmatch(pid):
                raise StatementError("persona must look like 'persona079'.")
            held = self.server.data(pid)[0]  # {provider: OB Data}; v1: {None: ...}
            chosen = list(held)
            if "provider" in req:
                if not isinstance(req["provider"], str) or req["provider"] not in held:
                    raise StatementError(f"{pid} holds accounts only at {', '.join(held)}.")
                chosen = [req["provider"]]
        except StatementError as e:
            return self.fail(400, "UK.OBIE.Field.Invalid", str(e))
        now = time.time()
        issued = [(p, secrets.token_urlsafe(32)) for p in chosen]
        with self.server.lock:
            self.server.tokens = {k: v for k, v in self.server.tokens.items() if v[2] > now}
            self.server.tokens.update((t, (pid, p, now + TOKEN_LIFE)) for p, t in issued)
        if not v2:
            return self.send(201, {"access_token": issued[0][1], "token_type": "Bearer", "expires_in": TOKEN_LIFE,
                                   "accountId": held[None]["Account"][0]["AccountId"], "note": NOTE})
        self.send(201, {"consents": [{"provider": p, "access_token": t, "token_type": "Bearer", "expires_in": TOKEN_LIFE,
                                      "accountIds": [a["AccountId"] for a in held[p]["Account"]]} for p, t in issued],
                        "note": NOTE + " One token per provider: each bank authorises access to its own accounts."})

    def do_GET(self):
        url, srv = urllib.parse.urlsplit(self.path), self.server
        m = ROUTE.fullmatch(url.path)  # (provider, AccountId, resource); v1 has no provider prefix, v2 needs one
        if not m or (m[1] is not None) != srv.v2 or (m[3] is not None and m[3] not in srv.resources):
            return self.fail(404, "UK.OBIE.Resource.NotFound", "Unknown path; use " + "/providers/{Provider}" * srv.v2 +
                             f"{API}/accounts[/{{AccountId}}[/{'|'.join(sorted(srv.resources))}]].")
        if srv.v2 and m[1] not in PROVIDERS:
            return self.fail(404, "UK.OBIE.Resource.NotFound", f"Unknown provider; use one of {', '.join(PROVIDERS)}.")
        auth = self.headers.get("Authorization")
        tok = re.fullmatch(r"Bearer ([A-Za-z0-9_-]{20,100})", auth or "")
        with srv.lock:
            entry = srv.tokens.get(tok[1]) if tok else None  # (persona, provider, expiry)
        if not entry or entry[2] <= time.time() or entry[1] != m[1]:  # a token works only where it was issued
            return self.fail(401, "UK.OBIE.Header.Missing" if auth is None else "UK.OBIE.Header.Invalid",
                             "Send Authorization: Bearer <token> from POST /mock/consent (tokens expire after an hour "
                             "and work only at the provider that issued them).")
        held, info = srv.data(entry[0])
        data = held[entry[1]]
        accounts = {a["AccountId"]: a for a in data["Account"]}
        if m[2] is not None and m[2] not in accounts:
            if not re.fullmatch(r"[0-9a-f]{8}", m[2]):
                return self.fail(400, "UK.OBIE.Field.Invalid", "AccountId must be 8 lower-case hexadecimal characters.")
            return self.fail(403, "UK.OBIE.Resource.ConsentMismatch", "This token does not cover that account.")
        if url.query and m[3] != "transactions":
            return self.fail(400, "UK.OBIE.Field.Unexpected", "This endpoint takes no query parameters.")
        host = self.headers.get("Host", "")
        if not re.fullmatch(r"(127\.0\.0\.1|localhost)(:\d{1,5})?", host):
            host = f"127.0.0.1:{srv.server_port}"
        links, meta = {"Self": f"http://{host}{self.path}"}, {"TotalPages": 1}
        if m[3] is None:
            data = {"Account": list(accounts.values()) if m[2] is None else [accounts[m[2]]]}
        elif m[3] != "transactions":
            kind = RESOURCES[m[3]]
            data = {kind: [x for x in data.get(kind, []) if x["AccountId"] == m[2]]}
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
                rows = [r for r in reversed(data["Transaction"])  # newest first, as many banks return them
                        if r["AccountId"] == m[2]
                        and (not lo or lo <= dt.datetime.fromisoformat(r["BookingDateTime"]))
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
            meta = {"TotalPages": pages, "FirstAvailableDateTime": info["FirstAvailableDateTime"],
                    "LastAvailableDateTime": info["LastAvailableDateTime"]}
        self.send(200, {"Data": data, "Links": links, "Meta": meta})

    def log_message(self, *a):
        pass


def serve(port, quiet=False, source="v1"):
    """The mock bank on 127.0.0.1:`port` (0: any free port), serving `source` "v1" or "v2" (module docstring)."""
    if source not in ("v1", "v2"):
        raise ValueError("source must be 'v1' or 'v2'")
    n = len(list(OB_DIR.glob("persona[0-9][0-9][0-9]_*.json"))) if source == "v2" else None
    if n == 0:
        raise SystemExit(f"No Open Banking data in {OB_DIR}: run ob_generator.py first (see USER_GUIDE.md).")
    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    srv.tokens, srv.lock = {}, threading.Lock()  # token -> (persona, provider (v1: None), expiry); lost on restart
    srv.v2, srv.data = source == "v2", v2_data if source == "v2" else v1_data
    srv.resources = set(RESOURCES) if srv.v2 else V1_RESOURCES
    if not quiet:
        where = f"/providers/{{{'|'.join(PROVIDERS)}}}{API} ({n} personas)" if srv.v2 else API
        print(f"Mock bank {source} (Open Banking v3.1 AISP shapes, NOT a real bank) on "
              f"http://127.0.0.1:{srv.server_port}{where} (Ctrl+C to stop)")
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
    """Time, bytes and transaction pages left for one whole fetch, shared by all its requests."""
    def __init__(self, seconds=FETCH_SECONDS, size=FETCH_BYTES, pages=MAX_PAGES):
        self.end, self.left, self.pages = time.monotonic() + seconds, size, pages

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
            if r.length:  # read1 returns b"" at an early close instead of raising
                raise StatementError("A bank response was cut short.")
            budget.timeout()  # a response that finished after the deadline also fails (worst case: deadline + 10 s)
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


def read_pages(url, token, base, budget):
    """Every row of one transactions resource: follows Links.Next only to the origin `base` (from bank_url), never to
    a page already read, and reads at most budget.pages pages in the whole fetch."""
    rows, seen = [], set()
    while url:
        if url in seen:
            raise StatementError("The bank's transaction pages link back to a page already read.")
        if budget.pages <= 0:
            raise StatementError("Too many transaction pages.")
        budget.pages -= 1
        seen.add(url)
        page = call(url, token, budget=budget)
        rows += page["Data"].get("Transaction", [])
        url = (page.get("Links") or {}).get("Next")
        if url and (origin(url) or [None])[0] != base:
            raise StatementError("A transactions page linked outside the bank's base URL.")
    return rows


def read_account(base, token, budget=None):
    """(transactions, balances, direct debits, standing orders) of the token's one current account (v1 layout), all
    within one Budget."""
    budget, api = budget or Budget(), base + API
    accounts = [a for a in call(api + "/accounts", token, budget=budget)["Data"]["Account"]
                if a.get("AccountSubType") == "CurrentAccount"]
    if len(accounts) != 1:  # ponytail: one current account per consent; upgrade by letting the user pick an AccountId
        raise StatementError(f"Expected one current account, found {len(accounts)}.")
    acc = f"{api}/accounts/{urllib.parse.quote(str(accounts[0]['AccountId']), safe='')}"
    return (read_pages(acc + "/transactions", token, base, budget),
            call(acc + "/balances", token, budget=budget)["Data"]["Balance"],
            call(acc + "/direct-debits", token, budget=budget)["Data"].get("DirectDebit", []),
            call(acc + "/standing-orders", token, budget=budget)["Data"].get("StandingOrder", []))


def mandate_names(direct_debits, standing_orders):
    return {d["Name"]: "DD" for d in direct_debits} | {s["Reference"]: "SO" for s in standing_orders if "Reference" in s}


def ob_row(r, names):
    """One OB transaction -> dict(date, type, desc, debit, credit, balance [pence] or None, change [pence]).
    type = ProprietaryBankTransactionCode.Code, else the statement type of the ISO BankTransactionCode, else DD or SO
    when the description is in `names` (mandate_names), else DEB for a debit and BGC for a credit. Raises KeyError,
    TypeError, ValueError or AttributeError for a malformed row."""
    if r["CreditDebitIndicator"] not in ("Credit", "Debit"):
        raise ValueError("bad CreditDebitIndicator")
    p, debit = pennies(r["Amount"]["Amount"]), r["CreditDebitIndicator"] == "Debit"
    desc = str(r.get("TransactionInformation", "")).strip()
    code = ((r.get("ProprietaryBankTransactionCode") or {}).get("Code")
            or ISO_TYPE.get(tuple((r.get("BankTransactionCode") or {}).get(k) for k in ("Code", "SubCode")))
            or (names.get(desc) if debit else None) or ("DEB" if debit else "BGC"))
    return dict(date=dt.datetime.fromisoformat(r["BookingDateTime"]).date(), type=str(code).strip().upper(), desc=desc,
                debit=p / 100 if debit else 0.0, credit=0.0 if debit else p / 100,
                balance=signed(r["Balance"]) if r.get("Balance") else None, change=-p if debit else p)


def to_transactions(rows, balances, direct_debits=(), standing_orders=(), keep=False):
    """Booked OB transactions -> the statements.parse transaction list (date, type, desc, debit, credit, balance),
    oldest first; types as in ob_row. Running balances are rebuilt backwards from the InterimBooked (else ClosingBooked)
    balance; any balance the bank gives per transaction must agree to the penny. Order: a list whose first row is
    dated after its last is reversed; when every row has the same date, the order (newest first, as the mock bank sends
    it, or as given) that reconciles with the per-transaction balances is used, newest first when there are none.
    keep=True adds each source OB row under "row". ponytail: pending transactions are ignored, and same-day order is
    otherwise the bank's; upgrade with the provider's own ordering key."""
    try:
        names = mandate_names(direct_debits, standing_orders)
        closing = next((b for kind in ("InterimBooked", "ClosingBooked") for b in balances if b["Type"] == kind), None)
        if closing is None:
            raise StatementError("The bank gave no InterimBooked or ClosingBooked balance.")
        tx = [ob_row(r, names) | {"row": r} for r in rows if r["Status"] == "Booked"]
        bal = signed(closing)
    except (KeyError, TypeError, ValueError, AttributeError) as e:
        raise StatementError(f"The bank's data are not in the expected Open Banking shape ({e}).") from None
    if not tx:
        raise StatementError("The bank returned no booked transactions.")
    first, last = tx[0]["date"], tx[-1]["date"]
    for order in [tx[::-1]] if first > last else [tx] if first < last else [tx[::-1], tx]:
        try:
            out = rebuild(order, bal)
            return out if keep else [{k: v for k, v in t.items() if k != "row"} for t in out]
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
    Banking AISP API at `base_url`, as statements.parse would give them from the CSV."""
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


# ---------------------------------------------------------------- client: every account at every provider (v2, T21)
KINDS = {"CurrentAccount": "current", "Savings": "savings", "CreditCard": "creditCard"}
RATES = {"OverdraftEAR": "overdraftEAR", "InterestRateAER": "interestAER", "PurchaseAPR": "purchaseAPR"}  # per cent


def text(x):
    return x if isinstance(x, str) else None


def day(s):
    return dt.datetime.fromisoformat(s).date()


def gbp(a):
    return pennies(a["Amount"]) / 100


def opt(o, k, f):
    return f(o[k]) if o.get(k) is not None else None


def rate(s):
    """A rate string such as "39.90" [per cent] -> float; raises ValueError for anything else (no NaN or infinity)."""
    if not isinstance(s, str) or not AMOUNT.fullmatch(s):
        raise ValueError("bad rate")
    return float(s)


def whole(x, lo, hi):
    return x if isinstance(x, int) and not isinstance(x, bool) and lo <= x <= hi else None


def detail(r):
    """What the engine's transaction format drops: the OB id and time and the merchant (name, ISO 18245 code)."""
    md = r.get("MerchantDetails") or {}
    mcc = md.get("MerchantCategoryCode")
    return {"id": text(r.get("TransactionId")), "time": r["BookingDateTime"], "merchant": text(md.get("MerchantName")),
            "mcc": mcc if isinstance(mcc, str) and re.fullmatch(r"\d{4}", mcc) else None}


def account_picture(provider, api, token, a, base, budget):
    """One account of the customer picture, from every resource its provider's API serves for it."""
    acc = str(a["AccountId"])
    url = f"{api}/accounts/{urllib.parse.quote(acc, safe='')}"
    get = lambda res, key: call(f"{url}/{res}", token, budget=budget)["Data"].get(key, [])
    rows, bal = read_pages(url + "/transactions", token, base, budget), get("balances", "Balance")
    dds, sos = get("direct-debits", "DirectDebit"), get("standing-orders", "StandingOrder")
    sps, prod = get("scheduled-payments", "ScheduledPayment"), (get("product", "Product") or [{}])[0]
    sd = prod.get("SupplementaryData") or {}
    kind = KINDS.get(a.get("AccountSubType"), "other")
    # ponytail: joint and ISA come from the mock's product data (SupplementaryData.JointAccount, OtherProductType);
    # a real provider shows joint holders through /accounts/{id}/parties (PartyType "Joint") and its own product codes.
    if kind == "current" and sd.get("JointAccount") is True:
        kind = "jointCurrent"
    if kind == "savings" and (prod.get("OtherProductType") or {}).get("Name") == "CashISA":
        kind = "cashIsa"
    b = {x["Type"]: x for x in bal}
    booked = b.get("InterimBooked") or b.get("ClosingBooked")
    if booked is None:
        raise StatementError("The bank gave no InterimBooked or ClosingBooked balance.")
    gbp_of = lambda kind: signed(b[kind]) / 100 if kind in b else None
    tx = to_transactions(rows, bal, dds, sos, keep=True) if any(r["Status"] == "Booked" for r in rows) else []
    names = mandate_names(dds, sos)
    pending = sorted(({k: v for k, v in ob_row(r, names).items() if k not in ("balance", "change")} | detail(r)
                      for r in rows if r["Status"] == "Pending"), key=lambda t: dt.datetime.fromisoformat(t["time"]))
    return {"provider": provider, "accountId": acc, "type": kind, "subType": text(a.get("AccountSubType")),
            "nickname": text(a.get("Nickname")), "identification": text((a.get("Account") or [{}])[0].get("Identification")),
            "balances": {"booked": signed(booked) / 100, "available": gbp_of("InterimAvailable"),
                         "opening": gbp_of("OpeningBooked"), "asOf": dt.datetime.fromisoformat(booked["DateTime"])},
            "creditLines": [{"type": text(c.get("Type")), "amount": gbp(c["Amount"]), "included": c.get("Included") is True}
                            for c in booked.get("CreditLine") or []],
            "product": {"id": text(prod.get("ProductId")), "name": text(prod.get("ProductName")),
                        "type": text((prod.get("OtherProductType") or {}).get("Name") or prod.get("ProductType")),
                        "rates": {v: rate(sd[k]) for k, v in RATES.items() if k in sd},
                        "statementDay": whole(sd.get("StatementDay"), 1, 31),
                        "paymentDueDays": whole(sd.get("PaymentDueDaysAfterStatement"), 0, 60)} if prod else None,
            "directDebits": [{"name": text(d.get("Name")), "status": text(d.get("DirectDebitStatusCode")),
                              "frequency": text(d.get("Frequency")), "lastDate": opt(d, "PreviousPaymentDateTime", day),
                              "lastAmount": opt(d, "PreviousPaymentAmount", gbp)} for d in dds],
            "standingOrders": [{"reference": text(s.get("Reference")), "status": text(s.get("StandingOrderStatusCode")),
                                "frequency": text(s.get("Frequency")),
                                **{f"{w.lower()}Date": opt(s, f"{w}PaymentDateTime", day) for w in ("First", "Next", "Last", "Final")},
                                **{f"{w.lower()}Amount": opt(s, f"{w}PaymentAmount", gbp) for w in ("First", "Next", "Last", "Final")},
                                "toAccount": text((s.get("CreditorAccount") or {}).get("Identification"))} for s in sos],
            "scheduledPayments": [{"date": day(p["ScheduledPaymentDateTime"]), "reference": text(p.get("Reference")),
                                   "amount": gbp(p["InstructedAmount"]),
                                   "instalment": text((p.get("SupplementaryData") or {}).get("Instalment"))} for p in sps],
            "pending": pending,
            "transactions": [{k: v for k, v in t.items() if k != "row"} for t in tx],
            "transactionDetails": [detail(t["row"]) for t in tx]}


def fetch_customer(base_url, persona=None, tokens=None):
    """The customer picture across providers, from a --source v2 mock bank (or any API with one Open Banking v3.1 AISP
    API per provider under /providers/{provider}): with `tokens` ({provider: bearer token}, one consent per provider),
    or with a mock consent for `persona`. Returns {"providers", "mainAccountId", "accounts"}; each account has its
    provider, AccountId, type (current, jointCurrent, savings, cashIsa, creditCard or other), balances (booked,
    available, opening [GBP, negative = owed], asOf), creditLines (arranged overdraft or card limit), product (rates in
    per cent), directDebits, standingOrders (toOwnAccountId when paid to one of these accounts), scheduledPayments,
    pending (engine fields without balance, plus detail), transactions (booked, exactly the engine's format, oldest
    first) and transactionDetails (aligned with transactions: id, time, merchant, mcc). Dates are datetime.date.
    mainAccountId: the sole-name current account with the largest regular income (statements.detect_income); ties
    and no income: the first. Same allow-list and limits as fetch; one Budget covers the whole customer."""
    base, budget = bank_url(base_url), Budget()
    if (persona is None) == (tokens is None):
        raise StatementError('bank needs "baseUrl" and exactly one of "persona" or "tokens" ({provider: bearer token}).')
    if persona is not None:
        if not isinstance(persona, str) or not PERSONA.fullmatch(persona):
            raise StatementError("bank.persona must look like 'persona079'.")
        consent = call(base + "/mock/consent", body=json.dumps({"persona": persona}).encode(), budget=budget)
        try:
            tokens = {c["provider"]: c["access_token"] for c in consent["consents"]}
        except (KeyError, TypeError, AttributeError):
            raise StatementError("The bank's consent response is not in the expected shape.") from None
    if not (isinstance(tokens, dict) and 0 < len(tokens) <= MAX_PROVIDERS and all(
            isinstance(p, str) and PROVIDER.fullmatch(p) and isinstance(t, str) and TOKEN.fullmatch(t)
            for p, t in tokens.items())):
        raise StatementError(f"bank.tokens must map 1 to {MAX_PROVIDERS} provider names (a letter, then letters or "
                             "digits) to printable bearer tokens.")
    try:
        accounts = [account_picture(p, f"{base}/providers/{p}{API}", t, a, base, budget) for p, t in tokens.items()
                    for a in call(f"{base}/providers/{p}{API}/accounts", t, budget=budget)["Data"]["Account"]]
        ids = [a["accountId"] for a in accounts]
        if len(set(ids)) != len(ids):  # ponytail: ids are unique within a provider only; upgrade: key on (provider, id)
            raise StatementError("Two of the customer's accounts share an AccountId.")
        own = {a["identification"]: a["accountId"] for a in accounts if a["identification"]}
        for a in accounts:
            for s in a["standingOrders"]:
                s["toOwnAccountId"] = own.get(s["toAccount"])
        income = lambda a: (af.detect_income(a["transactions"]) or {}).get("monthly", 0)
        main = max((a for a in accounts if a["type"] == "current"), key=income, default=None)
    except StatementError:
        raise
    except (KeyError, TypeError, ValueError, AttributeError, IndexError):
        raise StatementError("The bank's data are not in the expected Open Banking shape.") from None
    return {"providers": list(tokens), "mainAccountId": main and main["accountId"], "accounts": accounts}


def main_account(customer):
    """The main current account's entry in a fetch_customer picture, or None."""
    return next((a for a in customer["accounts"] if a["accountId"] == customer["mainAccountId"]), None)


def customer_json(customer):
    """The picture as JSON-ready data for an API response: booked transaction lists replaced by their count."""
    slim = customer | {"accounts": [{k: v for k, v in a.items() if k not in ("transactions", "transactionDetails")}
                                    | {"bookedTransactions": len(a["transactions"])} for a in customer["accounts"]]}
    return json.loads(json.dumps(slim, allow_nan=False, default=lambda d: d.isoformat()))


def from_request(bank):
    """A request's "bank" object (untrusted; the shape the archived POST /assess took) -> (main-account transactions,
    customer picture or None).
    {"baseUrl", "token" | "persona"}: the one current account (fetch, v1 layout). With "allAccounts": true and
    "persona" | "tokens": every account at every provider (fetch_customer); the main current account is assessed."""
    if not isinstance(bank, dict) or not set(bank) <= {"baseUrl", "token", "persona", "tokens", "allAccounts"}:
        raise StatementError('bank must be {"baseUrl": ..., "token": ...} or {"baseUrl": ..., "persona": ...}, or '
                             'with "allAccounts": true, {"baseUrl": ..., "persona" or "tokens": {provider: token}}.')
    every = bank.get("allAccounts", False)
    if not isinstance(every, bool) or ("tokens" in bank) > every or ("token" in bank and every):
        raise StatementError('bank.allAccounts must be true or false; true takes "persona" or "tokens", false '
                             '"persona" or "token".')
    if not every:
        return fetch(bank.get("baseUrl"), bank.get("token"), bank.get("persona")), None
    customer = fetch_customer(bank.get("baseUrl"), bank.get("persona"), bank.get("tokens"))
    main = main_account(customer)
    if main is None:
        raise StatementError("The bank showed no current account in the customer's sole name.")
    return main["transactions"], customer_json(customer)


# ---------------------------------------------------------------- self-check
def fails(f, *a, **k):
    """The StatementError message of f(*a, **k); AssertionError when it succeeds."""
    try:
        f(*a, **k)
    except StatementError as e:
        return str(e)
    raise AssertionError(f"{f.__name__} accepted {a} {k}")


def http_status(url, token=None, body=None):
    """HTTP status of one request through the client (200 on success), or the client's message when there is none."""
    try:
        call(url, token, body)
    except StatementError as e:
        return int(re.search(r"returned HTTP (\d+)", str(e))[1]) if "returned" in str(e) else str(e)
    return 200


def check_t23(base):
    """T23 review regressions, against the running mock bank at `base` and a misbehaving local server."""
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
                if self.path == "/short":  # promises 20 bytes, sends 7, closes
                    self.send_response(200)
                    self.send_header("Content-Length", "20")
                    self.end_headers()
                    self.wfile.write(b'{"a":1}')
                    self.close_connection = True
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
        assert "cut short" in fails(call, bad + "/short")
        fails(call, bad + "/chunked")                    # http.client.IncompleteRead
        fails(call, bad + "/a b")                        # http.client.InvalidURL
        msg = fails(call, bad + "/secret")
        assert msg == "The bank returned HTTP 403." and "SECRET" not in msg
        assert fails(call, "http://127.0.0.1:1/x") == "Could not read a response from the bank."
    finally:
        bad_srv.shutdown()


def check_v1():
    srv = serve(0, quiet=True)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_port}"
    os.environ["BANK_ALLOWED_HOSTS"] = f"{base},http://localhost:{srv.server_port}"  # the check's ephemeral port
    status = lambda path, token=None, body=None: http_status(base + path, token, body)
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
                for s in so] == [("RENT LETTING AGENT", "IntrvlMnthDay:01:01", "2026-11-01", "781.17")], so
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
            srv.tokens[tok] = srv.tokens[tok][:2] + (time.time() - 1,)  # expire persona050's token
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
                     b'{"persona": "persona050", "x": 1}', b'{"persona": "persona*"}', b'{"persona": ["persona050"]}',
                     b'{"persona": "persona050", "provider": "MockBank"}'):
            assert status("/mock/consent", body=body) == 400, body
        for p in (f"{API}/accounts/../../../../etc/passwd", f"{API}/accounts/%2e%2e%2f{acc_b}",
                  f"{API}/accounts/{acc}/../{acc_b}/transactions", f"{API}/accounts/{acc}/transactions/../../{acc_b}",
                  f"{API}/accounts/{acc}/", "/../Analysis/mock_statements/personas.md", f"{API}/accounts/ABCDEF12"):
            assert status(p, tok) in (400, 403, 404), p
        for p in (f"/providers/MockBank{API}/accounts", f"{API}/accounts/{acc}/product",
                  f"{API}/accounts/{acc}/scheduled-payments"):  # v2 paths and resources only
            assert status(p, tok) == 404, p
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
    print(f"Mock bank v1 self-check passed: {len(pids)} personas read through the Open Banking API match their CSVs.")


def check_v2():
    """v2: every persona's customer picture, read through the API, against the JSON files, ground_truth.csv and the
    main-account CSVs; token scope, consent, paths, limits and the allAccounts flag."""
    from collections import Counter
    import ob_generator as og  # ACCOUNTS: account key -> (AccountSubType, provider, ...)
    kind_of = {"ca": "current", "ca2": "current", "joint": "jointCurrent", "sv": "savings", "isa": "cashIsa",
               "cc1": "creditCard", "cc2": "creditCard"}
    with open(OB_DIR / "ground_truth.csv", encoding="utf-8", newline="") as fh:
        truth = list(csv.DictReader(fh))
    found = len(list(OB_DIR.glob("persona[0-9][0-9][0-9]_*.json")))
    if found != len(truth):
        raise SystemExit(f"The v2 check needs all {len(truth)} persona JSON files in {OB_DIR} (found {found}): "
                         "run ob_generator.py first.")
    srv = serve(0, quiet=True, source="v2")
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_port}"
    os.environ["BANK_ALLOWED_HOSTS"] = base  # the check's ephemeral port
    P = lambda provider: f"{base}/providers/{provider}{API}"
    csv_text = lambda pid: next((OB_DIR / "csv").glob(f"{pid}_*.csv")).read_text(encoding="utf-8")
    n = Counter()
    try:
        for row in truth:  # every persona, every provider, every account
            pid, uid = row["persona"], row["uuid8"]
            c = fetch_customer(base, persona=pid)
            doc = json.loads(next(OB_DIR.glob(f"{pid}_*.json")).read_text(encoding="utf-8"))
            keys = row["account_keys"].split(";")
            assert sorted((a["provider"], a["type"]) for a in c["accounts"]) == sorted(
                (og.ACCOUNTS[k][1], kind_of[k]) for k in keys) and len(keys) == int(row["n_accounts"]), pid
            assert c["providers"] == [b["Provider"] for b in doc["Providers"]] and c["mainAccountId"] == uid, pid
            assert main_account(c)["transactions"] == af.parse(csv_text(pid)), pid
            got = {a["accountId"]: a for a in c["accounts"]}
            own = {x["Account"][0]["Identification"]: x["AccountId"] for b in doc["Providers"] for x in b["Data"]["Account"]}
            for blk in doc["Providers"]:
                D = blk["Data"]
                for acc in (x["AccountId"] for x in D["Account"]):
                    a, mine = got[acc], lambda k: [x for x in D[k] if x["AccountId"] == acc]
                    bal = {x["Type"]: x for x in mine("Balance")}
                    booked = [x for x in mine("Transaction") if x["Status"] == "Booked"]
                    pend = sorted((x for x in mine("Transaction") if x["Status"] == "Pending"),
                                  key=lambda x: dt.datetime.fromisoformat(x["BookingDateTime"]))
                    assert a["provider"] == blk["Provider"], acc
                    assert [a["balances"][k] for k in ("booked", "available", "opening")] == [
                        signed(bal[t]) / 100 for t in ("InterimBooked", "InterimAvailable", "OpeningBooked")], acc
                    assert [(x["type"], x["amount"]) for x in a["creditLines"]] == [
                        (x["Type"], gbp(x["Amount"])) for x in bal["InterimBooked"].get("CreditLine", [])], acc
                    assert [(t["id"], t["credit"] - t["debit"], t["merchant"], t["date"]) for t in a["pending"]] == [
                        (x["TransactionId"], signed(x) / 100, (x.get("MerchantDetails") or {}).get("MerchantName"), day(x["BookingDateTime"]))
                        for x in pend], acc
                    assert [(d["id"], d["mcc"]) for d in a["transactionDetails"]] == [
                        (x["TransactionId"], (x.get("MerchantDetails") or {}).get("MerchantCategoryCode")) for x in booked], acc
                    assert len(a["transactions"]) == len(booked) and (
                        not booked or a["transactions"][-1]["balance"] == a["balances"]["booked"]), acc
                    prod = mine("Product")
                    assert len(prod) == 1 and a["product"]["id"] == prod[0]["ProductId"] and a["product"]["rates"] == {
                        v: float(prod[0]["SupplementaryData"][k]) for k, v in RATES.items() if k in prod[0]["SupplementaryData"]}, acc
                    assert [(s["date"], s["amount"], s["reference"]) for s in a["scheduledPayments"]] == [
                        (day(x["ScheduledPaymentDateTime"]), gbp(x["InstructedAmount"]), x["Reference"])
                        for x in mine("ScheduledPayment")], acc
                    assert [d["name"] for d in a["directDebits"]] == [x["Name"] for x in mine("DirectDebit")], acc
                    assert [(s["reference"], s["toOwnAccountId"]) for s in a["standingOrders"]] == [
                        (x["Reference"], own.get((x.get("CreditorAccount") or {}).get("Identification")))
                        for x in mine("StandingOrder")], acc
                    n.update(accounts=1, pending=len(pend), scheduled=len(a["scheduledPayments"]), products=1,
                             credit_lines=len(a["creditLines"]), to_own=sum(s["toOwnAccountId"] is not None
                                                                            for s in a["standingOrders"]))
            n.update(personas=1, consents=len(c["providers"]), with_scheduled=any(a["scheduledPayments"] for a in c["accounts"]))
        assert n["personas"] == len(truth) and min(n["pending"], n["scheduled"], n["with_scheduled"], n["to_own"]) > 0, n

        # One token per persona per provider; a token works only at its provider and only for that persona's accounts.
        consent = lambda body: call(base + "/mock/consent", body=json.dumps(body).encode())["consents"]
        c72, c01 = consent({"persona": "persona072"}), consent({"persona": "persona001"})
        t72, t01 = ({x["provider"]: x["access_token"] for x in c} for c in (c72, c01))
        ids72 = {x["provider"]: x["accountIds"] for x in c72}
        assert sorted(t72) == sorted(PROVIDERS) and list(t01) == ["MockBank"] and len(sum(ids72.values(), [])) == 7
        for provider, tok in t72.items():
            assert [x["AccountId"] for x in call(P(provider) + "/accounts", tok)["Data"]["Account"]] == ids72[provider]
        main72, card72, main01 = "05a4396f", ids72["MockCards"][0], c01[0]["accountIds"][0]
        assert http_status(P("MockCards") + "/accounts", t72["MockBank"]) == 401
        assert http_status(P("MockBank") + f"/accounts/{main72}", t72["MockDigital"]) == 401
        assert http_status(P("MockBank") + f"/accounts/{card72}/transactions", t72["MockBank"]) == 403
        assert http_status(P("MockCards") + f"/accounts/{main72}/balances", t72["MockCards"]) == 403
        assert http_status(P("MockBank") + f"/accounts/{main01}", t72["MockBank"]) == 403
        assert http_status(P("MockBank") + f"/accounts/{main72}/product", t01["MockBank"]) == 403
        assert http_status(P("MockBank") + "/accounts") == 401 and http_status(P("MockBank") + "/accounts", "x" * 40) == 401
        assert [x["provider"] for x in consent({"persona": "persona072", "provider": "MockCards"})] == ["MockCards"]
        for body in (b'{"persona": "persona029", "provider": "MockCards"}', b'{"persona": "persona072", "provider": "Evil"}',
                     b'{"persona": "persona072", "provider": ["MockBank"]}', b'{"persona": ["persona072"]}',
                     b'{"persona": "persona072", "provider": "MockBank", "x": 1}', b'{"provider": "MockBank"}',
                     b'{"persona": "persona999"}', b'{"persona": "../persona072"}'):
            assert http_status(base + "/mock/consent", body=body) == 400, body
        tok = t72["MockBank"]
        for p in (f"{base}{API}/accounts", f"{base}/providers/Evil{API}/accounts", f"{base}/providers/MockBank/x{API}/accounts",
                  P("MockBank") + f"/accounts/{main72}/products", P("MockBank") + f"/accounts/{main72}/",
                  f"{base}/providers/{API}/accounts", f"{base}/providers/..%2fMockBank{API}/accounts"):
            assert http_status(p, tok) == 404, p
        assert http_status(P("MockBank") + f"/accounts/{main72}/product?x=1", tok) == 400
        assert http_status(P("MockBank") + "/accounts/..%2f..%2fx/balances", tok) == 400

        # Date filters and paging on v2 (September 2026, British Summer Time; + encoded as %2B).
        csv72 = af.parse(csv_text("persona072"))
        sept = call(P("MockBank") + f"/accounts/{main72}/transactions?fromBookingDateTime=2026-09-01T00:00:00%2B01:00"
                    "&toBookingDateTime=2026-09-30T23:59:59%2B01:00", tok)
        assert len(sept["Data"]["Transaction"]) == sum((t["date"].year, t["date"].month) == (2026, 9) for t in csv72) > 0
        assert "Next" not in sept["Links"] and call(P("MockBank") + f"/accounts/{main72}/transactions", tok)["Meta"]["TotalPages"] > 1

        # Tokens per provider give the same picture as the mock consent; the v1 client cannot read a v2 bank.
        assert fetch_customer(base, tokens=t72) == fetch_customer(base, persona="persona072")
        fails(fetch, base, persona="persona072")
        # The main account is the one paid the salary, not the first listed (MockDigital's current account first here).
        rev = fetch_customer(base, tokens=dict(reversed(t72.items())))
        assert next(a for a in rev["accounts"] if a["type"] == "current")["provider"] == "MockDigital"
        assert rev["mainAccountId"] == main72

        # Limits and the exact-origin allow-list still apply.
        url = P("MockBank") + f"/accounts/{main72}/transactions"
        assert "Too many" in fails(read_pages, url, tok, base, Budget(pages=1))
        assert "more data" in fails(read_pages, url, tok, base, Budget(size=1000))
        for u in ("http://example.com", base + "/providers/MockBank", "http://127.0.0.1:1", base + API, None):
            fails(fetch_customer, u, persona="persona072")
        for kw in (dict(), dict(persona="persona072", tokens=t72), dict(persona="x"), dict(tokens={}), dict(tokens=[tok]),
                   dict(tokens={"../MockBank": tok}), dict(tokens={"MockBank": "bad token"}), dict(tokens={"Mock Bank": tok}),
                   dict(tokens={f"P{i}": tok for i in range(MAX_PROVIDERS + 1)}), dict(tokens={"MockCards": tok}),
                   dict(tokens={"MockBank": t01["MockBank"], "MockCards": t72["MockBank"]})):
            fails(fetch_customer, base, **kw)

        # A request's "bank" object with "allAccounts": the main account's transactions equal its CSV, plus the picture.
        tx, picture = from_request({"baseUrl": base, "persona": "persona072", "allAccounts": True})
        assert tx == csv72 and picture["mainAccountId"] == main72 and len(picture["accounts"]) == 7
        assert sum(a["bookedTransactions"] for a in picture["accounts"]) == sum(
            len(a["transactions"]) for a in fetch_customer(base, persona="persona072")["accounts"])
        json.dumps(picture, allow_nan=False)
        for bad in ({"baseUrl": base, "persona": "persona072", "allAccounts": "yes"}, {"baseUrl": base, "tokens": t72},
                    {"baseUrl": base, "token": tok, "allAccounts": True}, {"baseUrl": base, "tokens": t72, "allAccounts": False},
                    {"baseUrl": base, "persona": "persona072", "allAccounts": True, "x": 1}, ["x"]):
            fails(from_request, bad)
    finally:
        srv.shutdown()
    print(f"Mock bank v2 self-check passed: {n['personas']} personas, {n['consents']} provider consents, {n['accounts']} "
          f"accounts ({n['credit_lines']} credit lines, {n['products']} products, {n['pending']} pending transactions, "
          f"{n['scheduled']} scheduled payments for {n['with_scheduled']} personas, {n['to_own']} standing orders to own "
          "accounts) match the JSON, ground truth and main-account CSVs.")


def check(source=None):
    if source in (None, "v1"):
        check_v1()
    if source in (None, "v2"):
        check_v2()


if __name__ == "__main__":
    sys.modules["mock_bank"] = sys.modules[__name__]  # ob_generator imports mock_bank; keep one copy
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--serve", action="store_true", help="run the mock bank on 127.0.0.1")
    ap.add_argument("--port", type=int, default=8766, help="port for --serve (default 8766)")
    ap.add_argument("--source", choices=("v1", "v2"), help="--serve: the data to serve (default v1: Analysis/"
                    "mock_statements; v2: Analysis/open_banking); --check: check only that source (default both)")
    ap.add_argument("--check", action="store_true", help="run the self-check")
    args = ap.parse_args()
    if args.check:
        check(args.source)
    elif args.serve:
        try:
            serve(args.port, source=args.source or "v1").serve_forever()
        except KeyboardInterrupt:
            pass
    else:
        ap.print_help()
