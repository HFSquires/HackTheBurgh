"""Back end for Auro's checkout extension ("Second Thought", extension/), task T26.

Answers the extension's own contract (extension/README.md, "Backend contract"): POST /analyze and POST /action, served
by affordability.py's HTTP server, which routes those two paths here. The budget verdict comes only from the engine's
safeToSpend and the pay-now shortfallProbability; catalogue prices go in `alternatives` and the sale note in
`priceOutlook`, never in the verdict. Guidance, not advice: facts and options, never what the customer should do.

The payload carries no identity, so /analyze is answered for one persona statement: the payload's optional "persona",
else the one given with --persona when the server starts, else the first persona statement.

    python extension_api.py --serve [--port 8765] [--persona persona004]
    python extension_api.py --check     # starts the real server and validates every response against the contract
"""
import argparse, collections, datetime as dt, json, math, re, sys, threading, time, urllib.error, urllib.request, uuid
import affordability as af

MAX_BODY = 65_536  # bytes; the extension sends at most 4,000 characters of page text and 20 items
GOOD_SHARE = 0.6   # good only if the price is at most 60% of safeToSpend (the extension's own "uses most of it" line)
CAUTION_P = 0.10   # caution from a 10% chance of the balance going below £0 before payday (paying now)
RECONSIDER_P = 0.5  # reconsider from 50%, or when the price is more than safeToSpend
VERDICTS = ("good", "caution", "reconsider", "neutral")
ACTION_ID = re.compile(r"[a-z][a-z_]{0,31}")
PERSONA = None  # set by --persona; None means the first persona statement
ACTIONS = collections.deque(maxlen=500)  # in memory only: (unix time, actionId, sessionId, verdict); no page content


def gbp(x):
    return f"-£{abs(x):,.2f}" if x < 0 else f"£{x:,.2f}"


def pct(p):
    return "under 1%" if p < 0.005 else "over 99%" if p > 0.995 else f"{round(100 * p)}%"


def number(v, name):
    if v is None:
        return None
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
        raise af.StatementError(f"{name} must be a number or null.")
    return float(v)


def text(v, name, limit=1000):
    if v is not None and (not isinstance(v, str) or len(v) > limit):
        raise af.StatementError(f"{name} must be a string of at most {limit} characters.")
    return v


def budget(a):
    """(verdict, title, message, insights, safeToSpend) from safeToSpend and the pay-now shortfall probability only."""
    price, safe = a["price"], a["safeToSpend"]
    if a["assessmentStatus"] != "estimated" or safe is None:
        why = ("No regular income was found in the account" if not a["income"]
               else "The account's income or BNPL repayments could not be established")
        return "neutral", "Budget check unavailable", f"{why}, so safe-to-spend cannot be worked out.", [], None
    p = next(o for o in a["options"] if o["kind"] == "payNow")["shortfallProbability"]
    pay = dt.date.fromisoformat(a["income"]["nextPayday"])
    day = f"{pay:%a} {pay.day} {pay:%b}"
    if price > safe or p >= RECONSIDER_P:
        v, title = "reconsider", "More than is safe to spend" if price > safe else "Likely to go below £0"
    elif price > GOOD_SHARE * safe or p >= CAUTION_P:
        v, title = "caution", "Uses most of safe-to-spend" if price > GOOD_SHARE * safe else "Some chance of going below £0"
    else:
        v, title = "good", "Within safe-to-spend"
    if safe <= 0:
        msg = f"Nothing is safe to spend before payday on {day} (safe-to-spend is {gbp(safe)})."
    elif price > safe:
        msg = f"{gbp(price)} is {gbp(price - safe)} more than the {gbp(safe)} safe to spend before payday on {day}."
    else:
        msg = f"{gbp(price)} is {round(100 * price / safe)}% of the {gbp(safe)} safe to spend before payday on {day}."
    if v != "good":
        msg += f" The chance of the balance going below £0 before payday is {pct(p)}."
    insights = [("Safe to spend until payday", gbp(safe)), ("Left after this", gbp(af.money(safe - price))),
                ("Next payday", day), ("Chance of going below £0", pct(p))]
    return v, title, msg, insights, safe


def alternatives(a):
    """Cheaper catalogue prices from betterPrice: only below the price here, http(s) URLs, cheapest first, at most 3."""
    b = a["betterPrice"]
    if not b:
        return []
    when = dt.date.fromisoformat(b["cheapest"]["retrieved"]) if b["cheapest"] else None
    delivery = " · delivery may not be included" if "Delivery charges may not be included." in b["caveats"] else ""
    out = []
    if b["saving"] and b["cheapest"]:
        c = b["cheapest"]
        via = " via PriceSpy UK" if c["source_type"] == "comparison site" else ""
        out.append(dict(merchant=c["retailer"], price=c["price"], url=c["source_url"],
                        note=f"Price{via} on {when.day} {when:%b %Y}{delivery}"))
    if b["marketplaceCheaper"]:
        m = b["marketplaceCheaper"]
        out.append(dict(merchant=m["retailer"], price=m["price"], url=m["source_url"],
                        note="Marketplace or third-party seller: check the model, condition and seller"))
    # ponytail: the catalogue is matched by product name, so the colour or variant is unknown; upgrade with EAN matching
    out = [x | dict(currency="GBP", savings=af.money(a["price"] - x["price"]), match="different_variant",
                    matchNote="Colour or variant may differ", variant="")
           for x in out if x["price"] < a["price"] and re.match(r"https?://", x["url"] or "")]
    return sorted(out, key=lambda x: x["price"])[:3]


def outlook(a):
    """priceOutlook from saleNote: `possible` when the product is in the catalogue (no price statistics are claimed,
    so never `likely`), else `unknown`, which the extension does not show; no expected price."""
    s = a["saleNote"]
    if not s:
        return None
    d, h = dt.date.fromisoformat(s["date"]), s["priceHistory"]
    return dict(likelihood="possible" if a["betterPrice"] else "unknown", expectedPrice=None, byDate=s["date"],
                # The date only: daysToGo counts from the engine's today (the day after the statement), not the request.
                reason=f"{s['event']}: {d.day} {d:%b}. Sale prices are not always lower than earlier prices.",
                signals=[h["note"]] if h else [])


def actions(v, cheaper):
    """Ids the extension already handles: remind sets its 24-hour alarm; proceed and dismiss close the panel."""
    if v in ("good", "neutral"):
        return [dict(id="proceed", label="Continue to pay", variant="secondary" if cheaper else "primary"),
                dict(id="dismiss", label="Dismiss", variant="ghost")]
    return [dict(id="remind", label="Remind me in 24h", variant="secondary" if cheaper else "primary",
                 confirmation="Reminder set for this time tomorrow."),
            dict(id="proceed", label="Continue to pay", variant="ghost"),
            dict(id="dismiss", label="Dismiss", variant="ghost")]


def analyze(req):
    pid = req.get("persona") or PERSONA or af.personas()[0]["id"]
    af.load_persona(pid)  # validates the id and that its statement exists
    total, items = number(req.get("total"), "total"), req.get("items") or []
    if not isinstance(items, list) or len(items) > 50 or not all(isinstance(i, dict) for i in items):
        raise af.StatementError("items must be a list of at most 50 objects.")
    prices = [number(i.get("price"), "items[].price") for i in items]
    names = [text(i.get("name"), "items[].name") for i in items]
    merchant, title = text(req.get("merchant"), "merchant", 300), text(req.get("pageTitle"), "pageTitle")
    currency = (text(req.get("currency"), "currency", 8) or "GBP").upper()
    # Price: the total, else the sum of the items' prices as scraped (line prices; quantities are not multiplied).
    price = total if total and total > 0 else (
        af.money(sum(prices)) if prices and all(p and p > 0 for p in prices) else None)
    product = next((p for p in (names[0] if names else None, title) if p and af.find_product(p[:300])), None)
    sid = uuid.uuid4().hex
    base = dict(sessionId=sid, persona=pid, alternatives=[], priceOutlook=None)
    if price is None:
        v = "neutral"
        out = dict(title="Price not found", message="The price could not be read from this page, so it was not "
                                                    "compared with safe-to-spend.", insights=[])
    elif currency != "GBP":
        v = "neutral"
        out = dict(title="Budget check unavailable",
                   message=f"The budget check works in pounds; this checkout is in {currency}.", insights=[])
    else:
        a = af.assess(af.parse(af.load_persona(pid)), price, merchant=merchant,
                      product=af.find_product(product[:300]) if product else None)
        v, t, msg, ins, safe = budget(a)
        out = dict(title=t, message=msg, insights=[dict(label=k, value=x) for k, x in ins][:4],
                   alternatives=alternatives(a), priceOutlook=outlook(a))
        if safe is not None:
            out["budgetInfo"] = dict(left=safe)  # what the extension's Place-order pause compares the total with
    return base | out | dict(verdict=v, actions=actions(v, bool(out.get("alternatives"))))


def action(req):
    aid, sid, v = req.get("actionId"), req.get("sessionId"), req.get("verdict")
    if not isinstance(aid, str) or not ACTION_ID.fullmatch(aid):
        raise af.StatementError("actionId must be a short lower-case id such as 'remind'.")
    if sid is not None and (not isinstance(sid, str) or len(sid) > 64):
        raise af.StatementError("sessionId must be a string of at most 64 characters or null.")
    if v is not None and v not in VERDICTS:
        raise af.StatementError(f"verdict must be one of {', '.join(VERDICTS)} or null.")
    ACTIONS.append((round(time.time()), aid, sid, v))  # purchase, pageText and alternative are never kept
    return dict(ok=True)


def bad_constant(name):
    raise ValueError(f"{name} is not allowed")


def handle(h):
    """POST /analyze or /action for affordability.Handler `h`: JSON bodies only, size-limited, errors as {"error"}."""
    if h.headers.get_content_type() != "application/json":  # also makes browsers send a CORS preflight
        return h.send(415, dict(error="Send the body with Content-Type: application/json."))
    try:
        size = h.headers.get("Content-Length", "")
        size = int(size) if size.isdigit() else 0
        if not 0 < size <= MAX_BODY:
            raise af.StatementError(f"Send a JSON body of at most {MAX_BODY} bytes.")
        try:
            req = json.loads(h.rfile.read(size), parse_constant=bad_constant)
        except (ValueError, RecursionError):  # includes JSONDecodeError, UnicodeDecodeError and NaN/Infinity
            raise af.StatementError("The body is not valid JSON.") from None
        if not isinstance(req, dict):
            raise af.StatementError("Send a JSON object.")
        h.send(200, analyze(req) if h.path == "/analyze" else action(req))
    except af.StatementError as e:
        h.send(400, dict(error=str(e)))
    except Exception as e:  # never leave the extension hanging
        h.send(500, dict(error=f"Internal error: {type(e).__name__}: {e}"))


# ---------------------------------------------------------------- self-check
ADVICE = re.compile(r"\b(should|recommend|advise|must|don't|do not|avoid)\b", re.I)


def validate(r, total):
    """The extension's contract (README "Backend contract", content.js normalize, live.js SCHEMA)."""
    assert {"sessionId", "verdict", "title", "message", "insights", "actions", "alternatives", "priceOutlook"} <= set(r)
    assert r["verdict"] in VERDICTS and r["title"] and r["message"] and isinstance(r["sessionId"], str)
    assert len(r["insights"]) <= 4 and all(set(i) == {"label", "value"} and all(isinstance(x, str) and x
                                                                                for x in i.values()) for i in r["insights"])
    assert 1 <= len(r["actions"]) <= 4
    for a in r["actions"]:
        assert a["id"] in ("proceed", "dismiss", "remind") and a["label"] and a["variant"] in ("primary", "secondary", "ghost")
    alts = r["alternatives"]
    assert len(alts) <= 3 and [x["price"] for x in alts] == sorted(x["price"] for x in alts)
    for x in alts:
        assert x["merchant"] and re.match(r"https?://", x["url"]) and x["currency"] == "GBP", x
        assert isinstance(x["price"], float) and (total is None or x["price"] < total), (x, total)
        assert x["match"] in ("exact", "different_variant", "similar_item")
    o = r["priceOutlook"]
    if o is not None:
        assert o["likelihood"] in ("likely", "possible", "unlikely", "unknown") and o["expectedPrice"] is None
        assert re.fullmatch(r"(\d{4}-\d{2}-\d{2})?", o["byDate"]) and o["reason"] and len(o["signals"]) <= 3
    words = " ".join([r["title"], r["message"], *(i["label"] for i in r["insights"]), *(a["label"] for a in r["actions"])])
    assert not ADVICE.search(words), words  # guidance, not advice
    json.dumps(r, allow_nan=False)


def check():
    srv = af.serve(0, quiet=True)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{srv.server_port}"
    ext = "chrome-extension://abcdefghijklmnopabcdefghijklmnop"  # the background worker's origin

    def call(path, body, ctype="application/json", method="POST"):
        data = body if isinstance(body, bytes) or body is None else json.dumps(body).encode()
        headers = {"Origin": ext} | ({"Content-Type": ctype} if ctype else {})
        try:
            with urllib.request.urlopen(urllib.request.Request(url + path, data, headers, method=method)) as r:
                return r.status, (json.load(r) if r.status != 204 else None), r.headers
        except urllib.error.HTTPError as e:
            return e.code, json.load(e), e.headers

    readme = {"url": "https://shop.example/checkout", "merchant": "Northwind Outfitters",
              "pageTitle": "Checkout · Northwind Outfitters", "total": 177.99, "currency": "GBP",
              "items": [{"name": "Trailhead Waterproof Jacket", "price": 149}],
              "pageText": "visible page text, emails and long numbers redacted, max 4000 chars",
              "timestamp": "2026-11-07T14:52:00.000Z"}
    sony = "Sony WH-1000XM5 Wireless Noise Cancelling Headphones - Black"
    cases = {  # name: (payload changes, price the engine should be asked about)
        "readme": ({}, 177.99),
        "null total, items only": (dict(total=None, items=[dict(name="Trailhead Waterproof Jacket", price=149),
                                                           dict(name="Merino socks", variant="M", qty=2, price=12.5)]), 161.5),
        "no price": (dict(total=None, items=[]), None),
        "unaffordable": (dict(total=1_000_000), 1_000_000),
        "cheaper in catalogue": (dict(merchant="John Lewis", total=229.99, pageTitle="Checkout",
                                      items=[dict(name=sony, variant="Black", qty=1, price=229.99)]), 229.99),
        "page title only": (dict(merchant="johnlewis.com", total=229.99, items=[],
                                 pageTitle="Sony WH-1000XM5 wireless noise-cancelling headphones | John Lewis"), 229.99),
        "dollars": (dict(currency="USD"), None),
    }
    ps = [p["id"] for p in af.personas()]
    chosen = sorted({ps[0], ps[len(ps) // 4], ps[len(ps) // 2], ps[3 * len(ps) // 4], ps[-1]})
    tally = collections.Counter()
    try:
        code, out, hdr = call("/analyze", readme)  # no persona: the server's default (the first statement)
        assert code == 200 and out["persona"] == ps[0] and hdr["Access-Control-Allow-Origin"] == "*", (code, out)
        code, _, hdr = call("/analyze", None, ctype=None, method="OPTIONS")  # CORS preflight from any origin
        assert code == 204 and hdr["Access-Control-Allow-Origin"] == "*" and "Content-Type" in hdr[
            "Access-Control-Allow-Headers"]
        for pid in chosen:
            for name, (change, price) in cases.items():
                body = readme | change | dict(persona=pid)
                code, r, _ = call("/analyze", body)
                assert code == 200, (pid, name, r)
                validate(r, body["total"] if body["total"] else price)
                tally[name, r["verdict"]] += 1
                if price is None:
                    assert r["verdict"] == "neutral" and not r["insights"] and not r["alternatives"], (pid, name)
                    continue
                # The verdict against /assess (the engine over HTTP) for the same persona and price.
                code, a, _ = call("/assess", dict(persona=pid, price=price))
                assert code == 200
                safe, p = a["safeToSpend"], a["options"][0]["shortfallProbability"]
                want = ("neutral" if a["assessmentStatus"] != "estimated" else
                        "reconsider" if price > safe or p >= RECONSIDER_P else
                        "caution" if price > GOOD_SHARE * safe or p >= CAUTION_P else "good")
                assert r["verdict"] == want, (pid, name, r["verdict"], want, safe, p)
                assert want == "neutral" or r["insights"][0]["value"] == gbp(safe) and r["budgetInfo"]["left"] == safe
                if name == "unaffordable":
                    assert r["verdict"] in ("reconsider", "neutral")
                if name in ("cheaper in catalogue", "page title only"):
                    assert r["alternatives"] and r["priceOutlook"]["likelihood"] in ("possible", "unknown"), r
                if name in ("readme", "null total, items only"):  # the jacket is not in the catalogue
                    assert not r["alternatives"] and (r["priceOutlook"] is None
                                                      or r["priceOutlook"]["likelihood"] == "unknown")
        # /action: validated and acknowledged; page content never kept.
        code, r, _ = call("/action", dict(actionId="remind", sessionId="abc", verdict="caution", purchase=readme))
        assert code == 200 and r == {"ok": True} and ACTIONS[-1][1:] == ("remind", "abc", "caution")
        code, r, _ = call("/action", dict(actionId="alternative", alternative=dict(merchant="X", url="https://x.example",
                                                                                     price=1), purchase=readme))
        assert code == 200 and readme["pageText"] not in repr(list(ACTIONS)) and "x.example" not in repr(list(ACTIONS))
        for path, body in (("/action", {}), ("/action", dict(actionId="<script>")), ("/action", dict(actionId=3)),
                           ("/action", dict(actionId="proceed", verdict="great")), ("/analyze", b"not json"),
                           ("/analyze", b"[1]"), ("/analyze", b'{"total": NaN}'), ("/analyze", dict(total="12")),
                           ("/analyze", dict(total=True)), ("/analyze", dict(persona="x")),
                           ("/analyze", dict(persona="persona999")), ("/analyze", dict(items="x")),
                           ("/analyze", dict(items=[1])), ("/analyze", dict(merchant=["x"])),
                           ("/analyze", dict(total=1e8)), ("/analyze", b"[" * 20_000 + b"]" * 20_000)):
            code, r, _ = call(path, body)
            assert code == 400 and r["error"], (path, body, code, r)
        for kind in ("text/plain", None):  # a simple (preflight-free) cross-origin POST is refused
            assert call("/analyze", readme, ctype=kind)[0] == 415 and call("/action", {"actionId": "x"}, ctype=kind)[0] == 415
        try:
            code = call("/analyze", readme | dict(pageText="a" * MAX_BODY))[0]
        except (ConnectionError, urllib.error.URLError):  # the server may close before the oversized body is sent
            code = 400
        assert code == 400
    finally:
        srv.shutdown()
    print(f"Self-check passed: {len(cases)} payloads x {len(chosen)} personas ({', '.join(chosen)}), "
          "plus the default persona, CORS preflight, /action and malformed requests.")
    print("Payload | verdicts")
    for name in cases:
        print(f"{name} | " + ", ".join(f"{v} {tally[name, v]}" for v in VERDICTS if tally[name, v]))


if __name__ == "__main__":
    sys.modules["extension_api"] = sys.modules[__name__]  # affordability.Handler imports this module by name
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--serve", action="store_true", help="run the API (affordability.py's server) on 127.0.0.1")
    ap.add_argument("--port", type=int, default=8765, help="port for --serve (default 8765)")
    ap.add_argument("--persona", help="customer for /analyze when the payload names none (default: the first statement)")
    ap.add_argument("--check", action="store_true", help="run the self-check")
    args = ap.parse_args()
    if args.persona:
        af.load_persona(args.persona)
        PERSONA = args.persona
    if args.check:
        check()
    elif args.serve:
        srv = af.serve(args.port)
        print(f"/analyze answers for {PERSONA or af.personas()[0]['id']}")
        try:
            srv.serve_forever()
        except KeyboardInterrupt:
            pass
    else:
        ap.print_help()
