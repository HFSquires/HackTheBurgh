# User guide

Fill in each section from the code as it actually exists, and update it whenever setup, commands or outputs change. Runnable code: the generation-1 statement generator (`mock_statements.py`, tasks T05 and T05c), the Open Banking data generator (`ob_generator.py`, task T20) and its figures (`ob_figures.py`, task T25), the statement parser and detectors (`statements.py`, task T29), Andrew's model (`model.py`, task T30), the market data (`market_data.py`, task T14) and the mock bank (`mock_bank.py`, tasks T18b and T21). Auro's extension and account site are in `extension/` and `web/`. The old spending model and affordability engine (`affordability.py`, `bayes.py`, `forecast.py`, `affordability_figures.py`) were archived on 7 November 2026 (task T29; see `archive/README.md`); the new back end is `model.py`.

## Purpose

`mock_statements.py` writes synthetic bank-statement CSVs for the demo of the affordability extension (Bank of Scotland "Smart Cost of Living" challenge). Each statement belongs to a synthetic UK persona (any of the 12 UK countries and English regions) from the Hugging Face dataset `nvidia/Nemotron-Personas-UK`; the salary comes from ONS earnings by occupation (ASHE Table 14) and the spending from ONS Family Spending workbook 3 for the persona's own region. The default is 100 personas. The output is deterministic: the same inputs give byte-identical files.

## Setup

Windows, from the repository root, without admin rights:

```
uv venv --python 3.12
uv pip install --no-cache -r requirements.txt
```

Dependencies (`requirements.txt`): `openpyxl`, `pandas` and `odfpy` (the last two read the English Housing Survey `.ods` table used for tenure); `matplotlib` draws the figures (with the `texformat.pth` link and MiKTeX, see Plots in `CLAUDE.md`); `ob_figures.py` also uses numpy, installed with pandas. `statements.py` and `mock_bank.py` use the standard library only. The raw inputs are already committed in `data/`, except the 9.6 MB ASHE zip, which is not needed (the extracted workbook is committed); `data/README.md` gives its download command.

## Inputs

All in `data/` (sources, licences and dates in `data/README.md`): five pages of persona rows (`personas_rows_offset*.json`, 500 rows from all 12 UK regions; 245 are usable, i.e. working-age, aged 21 to 64, in one of the four household compositions with a Family Spending column, and with an ASHE occupation median), the ASHE Table 14.7a annual gross pay workbook (2025 revised), Family Spending workbooks 2 and 3 (financial year ending 2025), and English Housing Survey table FA1201 (tenure by age, 2024-25).

## Commands

```
.venv\Scripts\python mock_statements.py           # write Analysis/mock_statements/ (100 personas)
.venv\Scripts\python mock_statements.py --n 20    # a different number of personas
.venv\Scripts\python mock_statements.py --check   # self-check
```

If the console shows encoding errors, add `-X utf8` after `python`.

## Options

`--n N` sets the number of personas (default 100); it applies to `--check` too. Personas are chosen by a seeded draw stratified by region and household type. `--check` runs the self-check instead of writing outputs: N files with unique names, all 12 regions present, column order, balances reconcile on every row, a salary credit in each of August, September and October 2026, buy-now-pay-later plans for about a third of personas (within about 7% of N/3), dates ascending and ending by 31 October 2026, and identical output across two runs. The random seed and the CSV layout (columns, date format, fake sort code) are set in one block at the top of the script.

## Outputs

`Analysis/mock_statements/`: one CSV per persona (`persona<NNN>_<uuid8>.csv`, three digits), three months to 31 October 2026, in the Lloyds Banking Group export layout (Transaction Date, Transaction Type, Sort Code, Account Number, Transaction Description, Debit Amount, Credit Amount, Balance; dates DD/MM/YYYY); and `personas.md`, with one row per persona (number, uuid8, age, region, household, occupation, tenure, gross salary, net monthly pay, modelled monthly spend, buy-now-pay-later, end balance) and a table of spending by category.

## Limitations

The CSV layout is an unchecked belief about the Lloyds export format. Net pay uses 2026/27 income tax (Scottish bands for Scottish personas, rest-of-UK bands otherwise) and National Insurance, read on gov.uk on 7 November 2026, with no pension, student loan, tax code or personal-allowance taper. Spending is the regional average adjusted by household type (Table A23) and by the gross-income decile of the persona's own salary (Family Spending workbook 2, Table A4), the decile being taken from that salary alone because a partner's income is not modelled; the two adjustments overlap, so some spending is double-counted. Spending is uprated to September 2026 prices by CPI division (`Analysis/market/cpi_uprating_factors.csv`, which must exist; rent, energy and water, and council tax use division 04, a poor proxy for council tax, which CPI excludes); ASHE April 2025 pay is uprated to August 2026 by ONS average weekly earnings, whole-economy regular pay (KAI7, seasonally adjusted, nominal; 707 / 674 = 1.0490, from whole-pound levels) before tax; the income decile used to scale spending still uses April 2025 pay, because the Family Spending decile boundaries are 2024/25 incomes. Rent is the UK housing cost of the tenure (Table A32) less UK maintenance, water and energy, scaled by the region's gross rent over the UK's (A35 4.1.1); because both are all-household averages, the region's share of renters also enters the ratio. Council tax is the region's ONS 13.1, which pools council tax with mortgage interest, times the UK council-tax share of 13.1 (0.4946, Family Spending workbook 1, Table A1), assumed equal in every region; no single-person discount beyond the average is applied. End balances after three months range from -£710.87 to £16,963.39 (median about £5,905, two overdrawn). Vehicle purchases, package holidays, maintenance and other expenditure (ONS category 13 apart from the council-tax share of 13.1) are excluded. Tenure is sampled by age band from English Housing Survey 2024-25 table FA1201 (England only, applied to the UK); mortgagors are excluded (22 own outright, 29 social rented, 49 private rented). Pensioners, multi-adult and other household types are excluded, so all 100 are working-age. Rail operators and football clubs used for merchant flavour are typed into the code. Merchant names, transaction dates and buy-now-pay-later schedules are synthetic flavour. Each approximation is marked with a `ponytail:` comment in the code.

## Troubleshooting

If the Hugging Face or ONS files need refreshing, use the URLs in `data/README.md`; the datasets-server `filter` endpoint returned an authentication error on 7 November 2026, so personas are selected in code from unfiltered pages. ONS rate-limits repeated downloads (error 1015): wait and retry. The earnings series is downloaded from the ONS URL for KAI7 given in `data/README.md`.

## Statement parsing and detection

`statements.py` (task T29, standard library only) is the part of the old engine kept for the new back end: it parses a statement CSV in the layout above, or the same transactions as `mock_bank.py` rebuilds them from Open Banking data, and detects the salary and regular payments that Andrew's model infers first. Functions (all on the transaction list `parse` returns: dicts with `date`, `type`, `desc`, `debit`, `credit`, `balance`, oldest first):

| Function | Returns |
| --- | --- |
| `parse(text)` | The transaction list; raises `StatementError` with a message naming the line for anything unusable |
| `detect_income(tx)` | The regular salary (the credit description seen in the most calendar months, at least two, preferring BGC): `name`, `monthly` (latest amount), `day` (most common day of the month), `lastPaid`; or None |
| `next_payday(income, after)` | The first predicted payday after a date, moved to the previous Friday at weekends |
| `detect_bnpl(tx)` | Buy-now-pay-later plans (Klarna, Clearpay, PayPal Pay in 3): instalment, paid, remaining and schedule, or `uncertain: true` with unknown remaining |
| `detect_committed(tx, as_of)` | Committed payments due in the month after `as_of`: direct debits and standing orders seen within 35 days, and card payments of the same description and amount in at least three calendar months |
| `bank_rate()` | Bank of England Bank Rate history from `data/boe_bank_rate_IUDBEDR_2026-11-07.csv` |
| `personas()`, `load_persona(pid)` | The generation-1 persona list and one persona's CSV text from `Analysis/mock_statements/` |

```
.venv\Scripts\python -X utf8 statements.py --check
```

The check runs over all 100 generation-1 statements (salary equal to the BGC credits, every direct debit and standing order of the last month detected as committed, BNPL found exactly where present, payday within 35 days on a weekday), the BNPL ambiguity cases, zero and malformed amounts (NaN, infinity, wrong field counts, impossible dates, out-of-order dates) and the Bank Rate file.

Input validation: each transaction needs exactly one non-negative debit or credit and a finite balance; zero amounts and negative balances are allowed. Limitations: UK bank holidays are ignored in payday prediction; annual debits are treated as monthly; card subscriptions younger than three months are missed; BNPL instalment counts are assumed by provider. BNPL detection assumes one plan per transaction description: more payments than the provider's plan length, amounts differing by more than a penny, or gaps outside the provider cadence by more than three days make that description uncertain, with null `remaining` and `instalment` and an empty `schedule` meaning unknown, not debt-free.

## Andrew's model (model.py)

`model.py` (task T30) implements Andrew's model (`model outline/`): from a customer picture read through an Open Banking aggregator (`mock_bank.fetch_customer`; here the v2 mock bank), it forecasts this calendar month's everyday spending and decides whether a purchase keeps the customer on their net-worth goal. It uses `statements.py`, `mock_bank.py` and `market_data.py`; the decision and the endpoint use the standard library only, the backtest figure needs matplotlib, TeXFormat and MiKTeX. Every default is a proposal from `model outline/IMPLEMENTATION.md` section 2, set as a constant at the top of the file (`K`, `ONE_OFF_GBP`, `ONE_OFF_MCC`, `JOINT_SHARE`, `GOOD_MARGIN`, `MAX_DAYS`).

```
.venv\Scripts\python -X utf8 model.py                          # backtest: Analysis/model/ and Figures/model/ (about 40 s)
.venv\Scripts\python -X utf8 model.py --check                  # self-check, writes nothing (a few minutes)
.venv\Scripts\python -X utf8 mock_bank.py --serve --source v2  # terminal 1: mock bank on 8766
.venv\Scripts\python -X utf8 model.py --serve [--port 8765]    # terminal 2: POST /decide, GET /health
```

All three need the 100 persona JSON files in `Analysis/open_banking/` (run `ob_generator.py` first; only five are committed). Example request (Git Bash):

```
curl -s -X POST http://127.0.0.1:8765/decide -H "Content-Type: application/json" -d '{"bank": {"baseUrl": "http://127.0.0.1:8766", "persona": "persona004"}, "price": 409}'
```

Request: `bank` as `{"baseUrl", "persona"}` or `{"baseUrl", "tokens": {provider: token}}` (same allow-list as the mock bank client), `price` in GBP (above 0, at most 1,000,000), optional `today` (YYYY-MM-DD, in the month of the bank's balances and not before their date; default that date, 2 November 2026 for the synthetic data) and optional `goalRate` (a fraction a year between -0.5 and 1; default the 12-month CPI all-items inflation from `data/ons_mm23_cpi_index_D7BT.csv`, 3.4458% to September 2026). `Content-Type: application/json` is required (415 otherwise); bad input returns 400 with a message; CORS allows any origin.

Response: `verdict` (`good`, `caution`, `reconsider` or `neutral`, the extension's four states), `title`, `message`, `daysToAfford` (when the goal is missed: days of this month's forecast surplus needed to cover the shortfall, null beyond 90 days), `income` (salary, next payday, salary still due this month, other income by description), `regularDueThisMonth` (direct debits, standing orders and regular card payments due after the last booked day, own-account transfers excluded), `everyday` (forecast for the month, spent so far including pending purchases, remainder, the linear remainder for comparison, the k months used), `netWorth` (now, start of month, goal, forecast month end with and without the purchase, headroom, surplus), `assumptions` and `notAdvice`.

Definitions. Everyday spending: card purchases (rows with a merchant category code) on every account, less regular card payments (same description and amount, the same number of times, in at least three calendar months and seen in the last 35 days: `statements.detect_committed` on card rows), BNPL instalments (regular payments, their outstanding schedule already subtracted from net worth) and one-offs (merchant category 4722, package holidays, or a single purchase of GBP 250 or more). Forecast: `f_target × mean(r_j / f_j)` over the last k = 3 full months, f the ONS retail-sales seasonal factor (mean 1). Net worth: every account's booked balance (a joint account at half, cards negative) less outstanding BNPL scheduled payments and pending purchases. Goal: start-of-month net worth plus `max(W, 0) × ((1 + g)^(1/12) - 1)`. Verdict: `good` when the forecast month-end net worth after the purchase exceeds the goal by at least 10% of monthly salary, `caution` when it meets the goal by less, `reconsider` when it misses, `neutral` without a salary or a full month of history.

Self-check: hand-worked forecast and statistics helpers; on all 100 personas, everyday totals against the generator's ground truth (970 of 1,200 person-months exact, the other 230 explained by lumpy purchases below GBP 250 and BNPL instalments), salaries (100 of 100) and recent mandates; no look-ahead in the backtest; verdicts never improve as the price rises; the four personas in unarranged overdraft get `reconsider` at GBP 300; a missing salary gives `neutral`; the endpoint round-trips three personas and rejects malformed requests.

Outputs of the backtest: `Analysis/model/backtest.csv`, `Analysis/model/validation.md`, `Figures/model/forecast_errors.{pdf,svg,md}`. Limitations: synthetic data only, and the seasonal factors are the generator's own profile (the forecast's advantage over a plain mean is therefore not evidence of learning); the joint-account share, the GBP 250 one-off threshold and the interest-free `daysToAfford` are stated simplifications; other income is reported but not added to the month's flows; pensions and investments outside Open Banking are not in net worth; guidance, not financial advice.

## Mock bank API

`mock_bank.py` (tasks T18b and T21, standard library only) is a mock bank: it serves synthetic persona data through UK Open Banking Read/Write API v3.1 account-information (AISP) shapes on `127.0.0.1` (default port 8766; CORS allows any origin), from one of two sources chosen with `--source`:

| Source | Data | API base | Accounts per persona |
| --- | --- | --- | --- |
| `v1` (default) | `Analysis/mock_statements/` CSVs, three months | `/open-banking/v3.1/aisp` | one current account |
| `v2` | `Analysis/open_banking/persona*.json` from `ob_generator.py`, twelve months | `/providers/{Provider}/open-banking/v3.1/aisp`, Provider `MockBank`, `MockDigital` or `MockCards` | 1 to 7 |

v1 is the default (the generation-1 statements and the v1 check use it). v2 needs the gitignored JSON: only five samples (persona001, 029, 072, 082, 100) are committed, so run `ob_generator.py` first (it needs the FCA tables in `data/`); with the samples alone, v2 serves those five personas.

It is a mock: `POST /mock/consent` returns random bearer tokens (expiring after 3600 s; kept in memory and lost on restart) without authenticating anyone. Real account access needs an FCA-authorised account information service provider (AISP) and the customer's explicit consent through each of their banks. v1: `{"persona": "persona050"}` returns one token (`access_token`, `expires_in`, `accountId`). v2: one token per provider, as each bank authorises access to its own accounts: `{"persona": "persona072"}` returns `{"consents": [{"provider", "access_token", "token_type", "expires_in", "accountIds"}, ...]}` for every provider at which the persona holds accounts, and `{"persona": "persona072", "provider": "MockCards"}` returns that one only (400 when the persona holds nothing there). A token works only at the provider that issued it and only for that persona's accounts there.

Start it with `.venv\Scripts\python -X utf8 mock_bank.py --serve [--port N] [--source v1|v2]`; self-check with `.venv\Scripts\python -X utf8 mock_bank.py --check [--source v1|v2]` (both sources by default, about 45 s; the v2 part needs all 100 JSON files). v1: all 100 personas read through the API must equal their CSV parse. v2: every persona's accounts are read across all its providers and compared with the JSON, `ground_truth.csv` and the main-account CSVs in `Analysis/open_banking/csv/`; token scope, consent, paths, limits, the allow-list and `from_request`'s `allAccounts` flag are also tested.

Every request needs `Authorization: Bearer <token>`. Endpoints, under the base above: `GET /accounts`, `/accounts/{AccountId}`, `/accounts/{AccountId}/balances`, `/accounts/{AccountId}/transactions` (newest first, 100 per page; optional `fromBookingDateTime` and `toBookingDateTime`, ISO 8601 and inclusive, naive values read as UTC, `+` encoded as `%2B`; `page`), `/accounts/{AccountId}/direct-debits`, `/accounts/{AccountId}/standing-orders`, and in v2 also `/accounts/{AccountId}/scheduled-payments` and `/accounts/{AccountId}/product`. Responses use the standard `Data`/`Links`/`Meta` envelope, with amounts as two-decimal strings and a `CreditDebitIndicator`. v1: the AccountId is the statement file's 8-character suffix, the balance is InterimBooked, and direct debits and standing orders are derived from the statement's DD and SO rows. v2 serves the generator's objects unchanged: OpeningBooked, InterimBooked and InterimAvailable balances with `CreditLine` (arranged overdraft on current accounts, credit limit on cards); Booked and Pending transactions with `MerchantDetails` (merchant name and ISO 18245 code) and `CardInstrument`; mandates with frequencies and dates; buy-now-pay-later instalments as scheduled payments; and product terms, with rates in `SupplementaryData`. Errors use the Open Banking error body: 401 for a missing, invalid or expired token or one issued by another provider, 403 for an account the token does not cover, 400 for invalid parameters, and 404 for unknown paths or providers.

Requests. `mock_bank.from_request(bank)` validates an untrusted "bank" object (the shape the archived `POST /assess` took) and returns `(transactions, picture)`. One account (v1 layout): with `{"baseUrl": ..., "token": ...}` or `{"baseUrl": ..., "persona": ...}` it reads the one current account behind the token (`mock_bank.fetch`) and converts it into the same transactions as the CSV: the type comes from the proprietary bank code, else the ISO code, else the direct-debit or standing-order names; running balances are rebuilt from the booked balance and must reconcile with any per-transaction balances. This path does not read a v2 mock bank; the picture is None.

Every account (v2). With `{"baseUrl": ..., "persona": "persona072", "allAccounts": true}`, or with `"tokens": {"MockBank": "<token>", "MockCards": "<token>"}` in place of `persona`, it reads every account at every provider (`mock_bank.fetch_customer`) and returns the main current account's transactions, the main account being the current account in the customer's sole name with the largest regular income detected (`statements.detect_income`), with the picture. In JSON form (`customer_json`) the picture has `providers`, `mainAccountId` and `accounts`. Each account has `provider`, `accountId`, `subType`, `nickname` and `identification`; `type` (`current`, `jointCurrent`, `savings`, `cashIsa` or `creditCard`); `balances` (`booked`, `available` and `opening` in GBP, negative when owed, and `asOf`); `creditLines` (`type` Arranged or Credit, and `amount`); `product` (`id`, `name`, `type`, `rates` in per cent as `overdraftEAR`, `interestAER` or `purchaseAPR`, and for cards `statementDay` and `paymentDueDays`); `directDebits`; `standingOrders`, with `toOwnAccountId` when the order pays another of the customer's accounts; `scheduledPayments`; `pending` (date, type, description, debit, credit, `id`, `time`, `merchant` and `mcc`); and `bookedTransactions`, a count only, since the transaction lists are not sent to the browser. Dates are `YYYY-MM-DD`. Example (Git Bash):

```
.venv/Scripts/python -X utf8 mock_bank.py --serve --source v2   # terminal 1: mock bank v2 on 8766
.venv/Scripts/python -X utf8 -c "import mock_bank as m; tx, pic = m.from_request({'baseUrl': 'http://127.0.0.1:8766', 'persona': 'persona072', 'allAccounts': True}); print(len(tx), [a['type'] for a in pic['accounts']])"
```

In Python, `mock_bank.fetch_customer(base_url, persona=None, tokens=None)` returns the same picture with, for each account, `transactions` (booked, oldest first, exactly `statements.parse`'s format) and `transactionDetails` (aligned with it item by item: `id`, `time`, `merchant`, `mcc`), and dates as `datetime.date`. `mock_bank.main_account(picture)` returns the main account's entry, and `mock_bank.customer_json(picture)` returns the JSON form above.

`baseUrl` must be an allowed origin with no path: `http://127.0.0.1:8766` or `http://localhost:8766` by default; others (for example a mock bank started with `--port N`) through `BANK_ALLOWED_HOSTS`, a comma-separated list of origins including the port, such as `http://127.0.0.1:9000,https://bank.example:443`. Redirects are refused; bank errors return 400 with a fixed message giving at most the HTTP status. Each fetch, including a whole customer across providers, is limited to 30 s, 20 MB and 200 transaction pages; provider names in `tokens` must be a letter followed by letters or digits, at most 10 providers. Use `127.0.0.1` rather than `localhost` on Windows: `localhost` tries IPv6 first and costs about 2 s per connection.

Limitations: the consent is a mock with no customer authentication; passing tokens from the browser to the back end is acceptable only for the demo. The ISO bank-transaction code names are approximations, not checked against the Open Banking code list. v1: standing-order first and final dates and payee accounts are omitted, annual orders appear as monthly, pending transactions are ignored, and an account with more than one current account stops with an error. v2: joint accounts and cash ISAs are recognised from the mock's product data (`SupplementaryData.JointAccount`, `OtherProductType`), whereas a real provider shows joint holders through `/accounts/{id}/parties`; AccountIds are assumed unique across a customer's providers (a clash stops with an error); `from_request` returns only the main current account's transactions; the other accounts are in the picture. A real provider (for example TrueLayer, whose Data API has its own response shape) needs a small converter and Harrison's credentials in `.env`.

## Market data

`market_data.py` (task T14) reads the ONS series in `data/` (`ons_mm23_cpi_index_<CDID>.csv` for all-items CPI and the 12 COICOP divisions; `ons_drsi_retail_sales_value_nsa_J5AH.csv`, retail sales value, not seasonally adjusted, Great Britain, all retailers including fuel). It writes `Analysis/market/cpi_uprating_factors.csv`, where `factor` is the September 2026 CPI index divided by the mean index over April 2024 to March 2025 (the Family Spending reference period), for uprating spending to current prices (all items 1.069; housing, water and fuels 1.109; food 1.054). It also writes `Figures/market/retail_sales_seasonality.{pdf,svg,md}`: the index by calendar month, each year scaled to its own mean, 2021 to 2025, with the November and December uplift ((13.7 ± 1.2)% and (19.9 ± 1.1)%).

```
.venv\Scripts\python -X utf8 market_data.py           # writes everything
.venv\Scripts\python -X utf8 market_data.py --check   # 13 factors in (0.9, 1.3), equal to a fresh calculation; .md tables match
```

Limitations: the data are a snapshot (to September 2026); to update, re-download the CSVs from the ONS URLs in `data/README.md` (ONS rate-limits repeated requests) and rerun. The retail index base year is not stated in the file. The years used (2021 to 2025) are fixed in `YEARS`. The seasonality figure shows points with ±SE error bars joined by a line; its y axis does not start at 0.

## Open Banking synthetic data (generation 2)

`ob_generator.py` (task T20) writes 12 months (1 November 2025 to 31 October 2026, plus pending card payments on 1 and 2 November 2026) of UK Open Banking v3.1 account-information objects for the same 100 personas as `mock_statements.py`, which it imports unchanged. Each person holds 1 to 7 accounts across fictional providers (MockBank, MockDigital, MockCards): a main current account with an arranged overdraft, and possibly a second current account at another provider, a joint account (couples), savings, a cash ISA and up to two credit cards (holdings: 3 people hold 1 account, 15 hold 2, 29 hold 3, 33 hold 4, 18 hold 5, 1 holds 6, 1 holds 7). Holding probabilities come from the FCA Financial Lives 2024 survey by age and household income where published (savings, cash ISA, credit card, second provider), and from stated synthetic rules otherwise (joint account, second card). Spending has persistent per-person habits (category multipliers, month-to-month correlation, a payday effect, a trend, seasonality from ONS retail sales, one-off purchases) whose true values are saved for testing. Transactions carry merchant names and ISO 18245 merchant category codes, times of day, booked or pending status and paired references for own-account transfers.

Setup: as above, plus the two FCA Financial Lives tables in `data/` (gitignored pending the FCA's reuse terms; download commands in `data/README.md`).

```
.venv\Scripts\python -X utf8 ob_generator.py [--n 100]   # a few seconds
.venv\Scripts\python -X utf8 ob_generator.py --check     # about 15 s
```

The check confirms byte-identical reruns, that every account reconciles transaction by transaction, that card and overdraft limits hold (breaches only for flagged committed payments), that own-account transfers net to zero, that the current-account CSV parses with the engine and its salary and mandates are detected, and that the ground truth is recoverable in aggregate (category multipliers: correlation 0.979; payday share: 0.963; trend only 0.405, not recoverable person by person over 12 months).

Outputs in `Analysis/open_banking/`: `persona<NNN>_<uuid8>.json` (one block per provider, with the resources Account, Balance, Product, DirectDebit, StandingOrder, ScheduledPayment and Transaction; about 47 MB in all, gitignored except five samples: 001, 029, 072, 082, 100), `csv/` (main current account only, in the statement layout), `ground_truth.csv`, `ground_truth_monthly.csv` and `summary.md`.

Limitations: synthetic, not real bank data; every assumption is listed in the SYNTHETIC block of the code (overdraft and card limits by pay band, 39.9% overdraft EAR, 24.9% card APR, 60% of card holders pay in full, savings rates at Bank Rate minus 0.75 points, opening balances); four personas (029, 054, 079, 100) reach unarranged overdraft because their committed payments exceed their pay and no benefits are modelled; balances are high because some ONS spending is not modelled; prices and pay are held at their 2026 level for the whole year. The CSV export covers the main account only, so card and second-account spending is invisible in it, and `statements.detect_committed` counts standing orders to a person's own savings or joint accounts as committed payments.

## Open Banking figures (T25)

`ob_figures.py` reads the 100 persona JSON files, `ground_truth.csv` and `summary.md` in `Analysis/open_banking/` and draws four figures describing the synthetic data set the model is tested on: spending through the year (the seasonality of everyday spending), accounts held against FCA Financial Lives 2024 (the accounts in net worth), the payday effect (why the within-month remainder matters) and main-account balances with overdraft use. Three earlier figures (where the money goes, monthly spending by category and tenure, top merchants) were archived in T31; `ob_figures.py` at commit `dd145f1` draws them. Everyday spending means booked card purchases (`DEB` and `PUR`) across all accounts, excluding own-account transfers and one-off purchases (the package holiday and the lumpy purchases in `ground_truth.csv`). The figures describe the generator, not real customers.

```
.venv\Scripts\python -X utf8 ob_figures.py          # about 1 minute
.venv\Scripts\python -X utf8 ob_figures.py --check  # about 1 minute
```

Requirements: the setup above and the TeXFormat link (`texformat.pth`); LaTeX must be on the PATH. Run `ob_generator.py` first, because the persona JSONs are gitignored apart from five samples and the script stops if fewer than 100 are present. Outputs: `Figures/open_banking/<name>.{pdf,svg,md}` (each `.md` is the companion statistics file) and the derived tables in `Analysis/open_banking_figures/` (listed in its README). The `--check` mode recomputes one month (March 2026) from the raw JSON with a separate code path, confirms the account-count bars sum to 100 and the `.md` tables match the CSVs, and compares the count of persons overdrawn with `summary.md`. Limitations: three lumpy purchases the generator forgoes (the person was overdrawn) are skipped, an overdraft is counted from the end-of-day balance (not intraday dips), and error bars are standard errors across 100 people.

## Browser extension and account site (Auro)

Auro's checkout extension ("Second Thought") is in `extension/` and its account site (Auth0, Firebase, Vercel) in `web/`, merged from the branch `frontend-extension` on 7 November 2026. Their own READMEs (`extension/README.md`, `web/README.md`) give setup and the back-end contract: with `BACKEND_URL` empty in `extension/src/config.js`, the extension uses built-in mock responses or, with the user's own OpenAI or ELM key, an AI web search; with `BACKEND_URL` set, it calls `POST /analyze` and `POST /action` on that server. The team will connect it to the new back end itself; branch `t26-extension-api` (parked, unmerged) shows the old engine answering this contract and is kept as reference.
