# Second Thought — checkout UI

Chrome extension (Manifest V3). When the user lands on a checkout page, a glowing border animates around the
browser edge while the AI analyses the purchase, then a panel shows a verdict, a short message and action buttons.

## Try it

**Without installing** — serve the folder and open the demo checkout:

```bash
python3 -m http.server 5173 --directory extension
```

Then open http://localhost:5173/demo/checkout.html. The black box on the left switches between mock verdicts.

**As an extension** — `chrome://extensions` → Developer mode → Load unpacked → pick the `extension/` folder.
It runs automatically on pages that look like a checkout; clicking the toolbar icon forces it on any page.

A page counts as a checkout when it has a checkout signal (a URL like `/checkout`, `/gp/buy/`, `/payment`, a host like
`pay.` / `checkout.`, or a visible "Place order" / "Pay now" / "Complete purchase" button) **and** a price on the page.
Cart and product pages are deliberately ignored. Tested on a live Shopify checkout (found "$629.95 USD").

## Your account (Auth0)

The `web/` folder is the account site: sign in with Auth0, save delivery details, payment preferences (method,
card nickname + last 4 digits, never card numbers) and budget, stored in Firestore through a Vercel function.
Fill in `ACCOUNT` in `src/config.js`, then **Options → Sign in**: the extension syncs those details (on sign-in,
hourly and at Chrome start) into the same settings it already uses. A saved payment preference is used at the
cheaper store when the original checkout didn't show which method was chosen. Setup steps: `web/README.md`.

## When it shows up (`src/stages.js`, `src/precheck.js`)

| Moment | What the shopper sees |
| --- | --- |
| Product page | Nothing while browsing. Clicking **Add to basket / Pre-order** checks it there and then: glow, then **one decision** (below), or a small note that fades if there's nothing to decide. Also a "-£3" badge on the toolbar icon if it's cheaper elsewhere. Closed on that store already: the check runs silently. |
| Basket page | A small "£3.00 cheaper at X · See" pill with no glow, only if there's a cheaper price. Before any forms. |
| Checkout | Glow, then **one decision** (below). Instant when the basket was already checked (the earlier result is reused, with the budget part redone against the real total). If there's nothing to decide, just a small "Fits your budget" note that fades. |
| "Place order" | Paused once, only when it would go over budget and the shopper hasn't already said "I still want to buy it": "This puts you £X over budget" with Not now / Buy at X instead / Buy anyway. "Buy anyway" lets the next click through. |

**One decision at a time** (`overlay.decisions`): one message and one main button, never a menu. The first that applies:

1. **Over budget** (`verdict: "reconsider"`): **Don't buy now**.
2. **Could get cheaper if you wait** (`priceOutlook` likely/possible): **Notify me if it drops**.
3. **Cheaper elsewhere** (`alternatives[0]`): **Go to checkout at X**.

Under the main button, **I still want to buy it** moves on to the next one that applies. Once a cheaper price is found,
that button becomes **Found it £24 cheaper at X →**, which opens the cheaper-elsewhere step (with **Buy here anyway**).

The cheaper-price search can take a minute, so "can't afford" (from the affordability model, in a moment) and "could get
cheaper" (usually quicker than the search) show as soon as they're known, with **Still searching for a better price…
Stop** underneath; the button changes when the search finishes. Saying "I still want to buy it" before then shows
"Looking for a cheaper price…" with **Stop and buy here**. When the answer is already known (reused from Add to
basket), it's shown at once.

Closing the panel keeps it quiet on that store for the rest of the session (the over-budget pause still applies).
Earlier checks are kept for 30 minutes in `chrome.storage.session`.

**Demo journey:** open `demo/product.html` → Add to basket → basket pill → Proceed to checkout (instant verdict) →
Place order (over-budget pause). The demo pages use the demo shopper below; `MOCK_BUDGET` in `config.js` can override
the budget part.

## Affordability model (`model.py` on `main`)

The budget decision comes from the team's affordability model when it's running: it reads the customer's accounts
through the mock bank, which serves them in the **UK Open Banking Read/Write API v3.1** account-information format, and
forecasts whether the purchase keeps them on their net-worth goal this month (`POST /decide`). Its verdict replaces the
saved-budget one at Add to basket and at checkout, and the Place order pause uses its "spare this month" figure. When
it's off or unreachable, the saved budget is used and the activity log says so.

On a checkout of `main` (standard library only):

```bash
python3 -X utf8 mock_bank.py --serve --source v2   # mock Open Banking bank on 8766
python3 -X utf8 model.py --serve                   # affordability model on 8765
```

When the model says "can't afford", the panel shows a small chart of the rest of the month from the same answer:
money across all accounts day by day (everyday spending spread evenly, bills on their due dates, salary on payday), with
and without the purchase, against the savings goal. Its last day equals the model's month-end forecast.

`MODEL` in `src/config.js` sets the model URL, the bank URL and which synthetic customer to read (default
`persona001`: 62, North East, £2,414 a month after tax, rent £692; up to about £283 fits, £283 to £525 is tight, above
£525 it says "You can't afford this right now"). `url: ""` turns it off.

## Demo shopper (`src/persona.js`)

A made-up shopper for demo videos on real sites: **Jamie Ferguson**, a student in Marchmont, Edinburgh, with delivery
details, a preferred card (nickname + last 4 only), a £250 shopping budget with £138 spent, and a bank picture:
£312.40 in the current account, rent / gym / phone / Spotify / electricity on fixed days, café wages on the 25th,
£850 saved towards Interrail. Nothing is real (the phone number is Ofcom's reserved range, the email is example.com).

**Options → Demo shopper → Use demo details** writes it into the same storage keys a real account sync fills
(`profile`, `budget`, `spent`, `paymentPreference`) plus `money`, and shows the balance, what's safe to spend before
payday, upcoming bills and recent transactions. **Remove bank picture** goes back to budget-only verdicts.

With `money` saved, the verdict (`precheck.js`, and the prompt in `live.js`) also checks **safe to spend** = balance
minus bills due before the next payday: a total above it is `reconsider` ("This could leave you short… rent due in
6 days") even when it fits the shopping budget, and the Place-order pause uses the tighter of the two limits. Two
extra insights appear: "Safe to spend until payday" and the next bill. The account page's demo mode has a matching
"Fill in the demo shopper's details" link (`web/public/persona.js` is a copy of the same file).

## Real results now (before the backend exists)

Open the extension's settings (right-click the toolbar icon → **Options**; it also opens on first install), paste an
OpenAI API key, optionally your monthly budget, and **Save**. On a checkout it then calls OpenAI's Responses API with
web search (`src/live.js`) to find the same items cheaper at real stores, and gives a verdict against your budget.
The checkout page text (emails and long numbers removed) is sent to OpenAI. "Remind me in 24h" sets a real alarm and
notification.

An **ELM key** (`elm-…`, University of Edinburgh) works too: it's detected by its prefix and calls go to the ELM proxy
(`https://elm.edina.ac.uk/api/v1`, OpenAI-compatible) instead of `api.openai.com`, with the same models. If ELM rejects
the web search tool, the request is retried once without it (logged), so prices then come from the model alone.

If the key's project can't use the chosen model (a 403/404 "does not have access to model"), the extension picks the
first model from its fallback list that `/models` says the key has, saves it as the model, and retries.

Priority: `BACKEND_URL` (team backend) → OpenAI or ELM key (live) → mock. The mock never links to a real store: its
"cheaper elsewhere" card points back at the demo checkout on localhost and is left out elsewhere.

### Switching to the cheaper store (`src/prepare.js`, `src/handoff.js`)

Clicking **Go to checkout at …** shows "Preparing your checkout", while the background works out the fastest route:

| Store | Route | Lands on |
| --- | --- | --- |
| Shopify | `/products/<handle>.js` → `/cart/<variantId>:1` (only when the exact variant is known) | Checkout, item in basket |
| Amazon (left out for now, see below) | ASIN from the URL → `/gp/aws/cart/add.html?ASIN.1=…` | Add-to-basket page |
| WooCommerce | `add-to-cart` id from the page → `/checkout/?add-to-cart=<id>` | Checkout, item in basket |
| Anything else | Product page; the extension clicks "Add to basket" → "Checkout" | Checkout |

Amazon is left out of "cheaper elsewhere" for now: `EXCLUDED_STORES` in `src/config.js` keeps it out of the AI's search
and filters it from any answer (AI, mock or backend) and from the toolbar badge. Remove it there to bring it back.

Before preparing, if the alternative isn't the exact item (`match` is `different_variant` or `similar_item`), the
panel says what differs ("Moss green, not Forest") and asks to continue. Basket links use the shopper's variant and
quantity read from the checkout (Shopify: matched against the product's options; otherwise chosen on the page).

When the built-in rules can't find the way (custom store sites, size/colour pickers, search or listing pages), the
**AI fallback** works like browser use: it sends a screenshot of the tab (`chrome.tabs.captureVisibleTab`) plus a
numbered list of the page's buttons/links/options to the OpenAI model (`ST.live.nextStep`), which returns one step:
open the matching listing, choose a variant, add to basket, go to checkout, or "stuck". The hand-off follows the tab it
opened, so it keeps going when a link leads from one site to another. Up to 4 steps per page, 8 pages in all. When the
model needs something only the shopper knows (which size, a postcode, a delivery choice), or gets stuck on something an
answer could fix, the panel asks them to type it; the answer goes back to the model and carries on. At checkout, needed
fields still empty after filling (name, email, address, city, postcode, or anything marked required) are asked for one
at a time and typed in. Card details, passwords and sign-in are never asked for, and it stops after 4 questions. Every automated click is checked
for what the element **does**, not just its label (`blockReason` in `src/handoff.js`): purchase/payment/account words
in its label, ids, classes or `data-*` attributes; where a link goes; where a submit button's form posts and whether
that form holds card or password fields; and whether it sits in the payment section. While an automated click is
handled, any form submission to an order/payment URL or with card/password fields is cancelled (`safeClick`). The
AI also sees each element's `goes_to` / `submits_form_to`, and elements that fail the check are marked `blocked`. At checkout, the same payment
*type* as on the original store (PayPal, Klarna, card…) is selected; card details are never entered.

The link carries **only the basket**. Personal details are typed into the form once checkout loads (taken from the
checkout the user came from, then their saved settings). They are never put in a URL, where they'd end up in history and
store logs. Card fields are never read or filled, and "Place order" / "Pay" are never clicked. Details are deleted once
filled, or after 30 minutes.

## Debugging: activity log

Every step is logged (`src/log.js`): detection, analysis results, the chosen checkout route, each AI request and
answer, blocked clicks and errors. Open **Options → Activity log** (or **See what happened** on an error panel). It
updates live and has **Copy** for sharing. It keeps the last 300 entries in `chrome.storage.local`, never API keys
or form values. The same lines go to the page console and the service-worker console, prefixed `[Second Thought]`.

## Files

| File | What it does |
| --- | --- |
| `src/config.js` | `BACKEND_URL`, timings, the "analysing" step labels |
| `src/detect.js` | Checkout detection (URL + "Place order"-style buttons) and scraping total / items / page text |
| `src/overlay.js` | All UI: glowing edge + panel, in a closed shadow root |
| `src/content.js` | Glue: detect → analyse → show result → report the chosen action |
| `src/api.js` / `src/background.js` | Backend calls (go through the background worker to avoid CORS) |
| `src/mock.js` | Fake backend used while `BACKEND_URL` is empty |

## Backend contract

Set `BACKEND_URL` in `src/config.js` (e.g. `http://localhost:8000`). The extension makes two calls.

### `POST /analyze`

Request:

```json
{
  "url": "https://shop.example/checkout",
  "merchant": "Northwind Outfitters",
  "pageTitle": "Checkout · Northwind Outfitters",
  "total": 177.99,
  "currency": "GBP",
  "items": [{ "name": "Trailhead Waterproof Jacket", "price": 149 }],
  "pageText": "visible page text, emails and long numbers redacted, max 4000 chars",
  "timestamp": "2026-11-07T14:52:00.000Z"
}
```

`total` may be `null` and `items` may be empty if scraping fails — `pageText` is there so the model can work it out.

Response:

```json
{
  "sessionId": "optional, echoed back on /action",
  "verdict": "good | caution | reconsider | neutral",
  "title": "Worth a pause",
  "message": "One or two sentences.",
  "insights": [
    { "label": "Shopping budget left", "value": "£222.49" },
    { "label": "After this", "value": "£44.50" }
  ],
  "actions": [
    { "id": "cheaper", "label": "Show cheaper options", "variant": "primary", "confirmation": "Opening alternatives…" },
    { "id": "remind", "label": "Remind me in 24h", "variant": "secondary", "confirmation": "Got it. We'll check in tomorrow." },
    { "id": "proceed", "label": "Buy anyway", "variant": "ghost" }
  ]
}
```

- `verdict` is about the **budget only** and sets the glow colour: `good` green (fits), `caution` amber (tight),
  `reconsider` red (over budget), `neutral` blue (no budget known). Never set it from price comparison: cheaper
  options go in `alternatives` and get their own green card whatever the verdict.
- `insights`: up to 4, shown as a 2-column grid. Values are display strings (format currency on the backend).
- `actions`: up to 4. `variant` is `primary` (full width, coloured), `secondary` or `ghost`.
  If `confirmation` is set, that text is shown briefly before the panel closes; otherwise it closes immediately.
- `alternatives` (optional): cheaper places to buy the same basket — see below.
- Anything missing or malformed falls back to safe defaults rather than breaking the page.

### Cheaper elsewhere (`alternatives`)

```json
"alternatives": [
  { "merchant": "Outdoor Depot", "price": 153.07, "currency": "GBP", "note": "Same items · free delivery",
    "url": "https://outdoordepot.example/cart/39876543210:1,39876543299:1" }
]
```

- Shown as a green "Cheaper elsewhere" card with a **Go to checkout at …** button; on phones it becomes the main
  button in the collapsed view ("Save £24.92 at Outdoor Depot"). Up to 3, cheapest first; extra ones are smaller links.
- `savings` is optional — the UI works it out from the scraped total. Alternatives that aren't actually cheaper are hidden.
- `url` must be `http(s)`. It opens in a new tab and the click is reported to `/action` as
  `{ "actionId": "alternative", "alternative": { "merchant", "url", "price" }, ... }`.
- **To land the user on checkout with the basket already filled, return a cart link, not a product page:**

| Store type | Cart link that adds items and opens the cart/checkout |
| --- | --- |
| Shopify | `https://store.com/cart/{variantId}:{qty},{variantId}:{qty}` (goes straight to checkout) |
| Amazon | `https://www.amazon.co.uk/gp/aws/cart/add.html?ASIN.1={asin}&Quantity.1=1&ASIN.2=…` |
| WooCommerce | `https://store.com/checkout/?add-to-cart={productId}&quantity=1` (one product per link) |
| Anything else | The product page — the user adds it themselves |

### Likely cheaper soon (`priceOutlook`)

```json
"priceOutlook": {
  "likelihood": "likely | possible | unlikely | unknown",
  "expectedPrice": 54.99,
  "byDate": "2026-11-27",
  "reason": "It dropped to £54.99 last Black Friday, which is on 27 Nov.",
  "signals": ["£54.99 at Argos, Black Friday 2025", "Price unchanged for 8 weeks"]
}
```

- Live mode gets it from a **separate call** (`ST.live.outlook`), run alongside the price comparison (at Add to basket
  and at checkout). The panel waits for both, up to 40 s for the outlook, so it shows one settled decision. The model looks for evidence with web search: price history sites, upcoming sales (Black Friday, Cyber Monday,
  Boxing Day…), a successor launching, pre-order undercutting. `likely` needs concrete evidence.
- A team backend sends `priceOutlook` inside the `/analyze` response instead; the extension then makes no extra call.
- Shown as the "Could get cheaper" decision only for `likely`/`possible`, and only when `expectedPrice` (if given) is
  below the total. Like alternatives, it never changes `verdict`. `signals` sit under a collapsed "Why?".
- Its **Notify me if it drops** button reports `{ "actionId": "watch", "outlook": { ... }, "purchase": ... }` to
  `/action`. Without a backend, the extension watches the price itself: a web-search price check every 12 hours (your API
  key), a notification when it's at or under `expectedPrice` or at least 3% under the checkout total (clicking opens
  the deal), and a "no drop yet" notification a week after `byDate` (30 days if none, 60 at most). Watches are listed in
  **Options → Price watches**, with **Check now** and **Stop**.

### `POST /action`

Fire-and-forget when the user clicks a button:

```json
{ "actionId": "remind", "sessionId": "…", "verdict": "caution", "purchase": { "...same as /analyze request" } }
```
