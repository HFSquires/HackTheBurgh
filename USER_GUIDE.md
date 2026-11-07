# User guide

Fill in each section from the code as it actually exists, and update it whenever setup, commands or outputs change. Runnable code: the mock bank-statement generator (`mock_statements.py`, tasks T05 and T05c) the back end (`affordability.py`, task T07) the affordability figures (`affordability_figures.py`, task T07b) the spending-forecast backtest (`forecast.py`, task T12) the market data (`market_data.py`, task T14) and the Bayesian spending model (`bayes.py`, task T17). The browser extension front end is being built by Auro (T10) and is not yet in the repository.

## Purpose

`mock_statements.py` writes synthetic bank-statement CSVs for the demo of the affordability extension (Bank of Scotland "Smart Cost of Living" challenge). Each statement belongs to a synthetic UK persona (any of the 12 UK countries and English regions) from the Hugging Face dataset `nvidia/Nemotron-Personas-UK`; the salary comes from ONS earnings by occupation (ASHE Table 14) and the spending from ONS Family Spending workbook 3 for the persona's own region. The default is 100 personas. The output is deterministic: the same inputs give byte-identical files.

## Setup

Windows, from the repository root, without admin rights:

```
uv venv --python 3.12
uv pip install --no-cache -r requirements.txt
```

Dependencies (`requirements.txt`): `openpyxl`, `pandas` and `odfpy` (the last two read the English Housing Survey `.ods` table used for tenure); `affordability.py` needs numpy, scipy and pandas from the `.venv` (through `bayes.py`), but not matplotlib or TeXFormat. The raw inputs are already committed in `data/`, except the 9.6 MB ASHE zip, which is not needed (the extracted workbook is committed); `data/README.md` gives its download command.

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

The CSV layout is an unchecked belief about the Lloyds export format. Net pay uses 2026/27 income tax (Scottish bands for Scottish personas, rest-of-UK bands otherwise) and National Insurance, read on gov.uk on 7 November 2026, with no pension, student loan, tax code or personal-allowance taper. Spending is the regional average adjusted by household type (Table A23) and by the gross-income decile of the persona's own salary (Family Spending workbook 2, Table A4), the decile being taken from that salary alone because a partner's income is not modelled; the two adjustments overlap, so some spending is double-counted. Spending is uprated to September 2026 prices by CPI division (`Analysis/market/cpi_uprating_factors.csv`, which must exist; rent, energy and water, and council tax use division 04, a poor proxy for council tax, which CPI excludes); ASHE April 2025 pay is uprated to August 2026 by ONS average weekly earnings, whole-economy regular pay (KAI7, seasonally adjusted, nominal; 707 / 674 = 1.0490, from whole-pound levels) before tax; the income decile used to scale spending still uses April 2025 pay, because the Family Spending decile boundaries are 2024/25 incomes. End balances after three months range from -£1,215.34 to £16,435.65 (median about £5,267, three overdrawn). Vehicle purchases, package holidays, maintenance and other expenditure (ONS category 13 apart from council tax) are excluded. Tenure is sampled by age band from English Housing Survey 2024-25 table FA1201 (England only, applied to the UK); mortgagors are excluded (22 own outright, 29 social rented, 49 private rented). Pensioners, multi-adult and other household types are excluded, so all 100 are working-age. Rail operators and football clubs used for merchant flavour are typed into the code. Merchant names, transaction dates and buy-now-pay-later schedules are synthetic flavour. Each approximation is marked with a `ponytail:` comment in the code.

## Troubleshooting

If the Hugging Face or ONS files need refreshing, use the URLs in `data/README.md`; the datasets-server `filter` endpoint returned an authentication error on 7 November 2026, so personas are selected in code from unfiltered pages. ONS rate-limits repeated downloads (error 1015): wait and retry. The earnings series is downloaded from the ONS URL for KAI7 given in `data/README.md`.

## Back end API

`affordability.py` reads a statement CSV in the layout above and serves a JSON API for the extension on `127.0.0.1` (default port 8765; CORS allows any origin). It uses the project `.venv` for the Bayesian dependencies listed in Setup. Start it with `.venv\Scripts\python -X utf8 affordability.py --serve [--port N]`; stop with Ctrl+C. Self-check: `.venv\Scripts\python -X utf8 affordability.py --check` (all persona CSVs at £50, £300 and £1,200, malformed CSVs, and the HTTP endpoints; prints how many personas can pay now, only with plain pay-in-3, or neither). The check also covers a large spending shock, unrecognised income, ambiguous BNPL payments, zero amounts and non-finite amounts.

Endpoints: `GET /health`; `GET /personas` (id, age, region, household, occupation, tenure); `POST /assess` with `{"persona": "persona079"}` or `{"csv": "<CSV text>"}`, plus `"price"` in GBP (> 0), optional `"merchant"`, optional `"product"` (a catalogue id such as `"P02"`, or a product name matched case-insensitively, word for word, against the catalogue names) and `"today"` (YYYY-MM-DD; default the day after the last transaction; must be after it and not after a missed payday). Errors return status 400 and `{"error": "..."}`. Example (Git Bash):

```
curl -s -X POST http://127.0.0.1:8765/assess -H "Content-Type: application/json" -d '{"persona": "persona004", "price": 229.99, "merchant": "John Lewis", "product": "P02", "today": "2026-11-07"}'
```

The response gives the detected salary and next payday, committed payments (direct debits, standing orders, same-amount card payments in three or more months) with due dates, buy-now-pay-later plans (Klarna, Clearpay, PayPal Pay in 3) with remaining instalments, `safeToSpendBeforeEverydaySpending` (balance minus committed payments and BNPL instalments due before payday), `predictedSpendingUntilPayday` (Bayesian posterior predictive mean and 80% interval of everyday spending until payday, from `bayes.py`), `safeToSpend` (the first minus the predicted mean), a monthly view, and five payment options (`payNow`, `bnplPot`, `bnplPlain`, `card0`, `cardPaidInFull`) with facts only, marking `cheapest` and `mostLeftUntilPayday` without recommending. Affordability uses the new `safeToSpend`; `bnplPlain` also needs the monthly left-over (after everyday spending) to cover one instalment. Every option except `card0` has `shortfallProbability`, the Bayesian probability that the balance falls below zero before payday after choosing it. `cardPaidInFull` assumes the card is cleared in full by direct debit, with float interest over an assumed 40-day interest-free period at the Bank Rate proxy and a `section75` flag for purchases of £100 to £30,000. `floatVerdict` is one neutral sentence comparing the interest from spreading the purchase with the saving from the cheapest mainstream price. `bnplPot.potInterest` estimates the interest the pot would earn: simple daily interest (365-day year) on the declining balance over the instalment schedule, at the latest Bank of England Bank Rate on or before `today` (`data/boe_bank_rate_IUDBEDR_2026-11-07.csv`), which stands in for an easy-access savings rate; it does not change the cost or affordability. `saleNote` names the next UK sale event within 60 days. When `product` matches the catalogue (`data/retail_prices_2026-11-07.csv`, prices collected 7 November 2026), `betterPrice` gives the cheapest price among Amazon UK, Argos, Currys, John Lewis, AO and Very, the saving against the given price (null unless that price is lower), `sameAsCurrent`, any cheaper marketplace or third-party seller (`marketplaceCheaper`, flagged separately and never `cheapest`) and caveats; otherwise it is null. `saleNote.priceHistory` gives PriceSpy UK's 3-month lowest and highest prices only when today's cheapest offer and the cheapest mainstream price both lie inside that range (currently P04 only); otherwise a caveat in `betterPrice` says why it is omitted. Definitions are returned in the response (`safeToSpendDefinition`, `affordableDefinition`, `shortfallDefinition`).

Limitations: UK bank holidays are ignored in payday prediction; annual debits are treated as monthly; card subscriptions younger than three months are missed; BNPL instalment counts are assumed by provider; there is no card data, so the 0% card option is descriptive only. Black Friday and Cyber Monday dates are checked against the calendar in `--check`; the Boxing Day sale start is a convention. The catalogue covers five products on one day, mostly from PriceSpy UK, which may lag retailers; product names are matched only when one name contains the other, so a reworded page title is missed. Pot interest uses Bank Rate as a proxy, with no compounding, tax or rate changes; real easy-access rates vary.

Input validation (T19): each transaction needs exactly one non-negative debit or credit and a finite balance; zero amounts and negative balances are allowed. NaN, infinity, malformed CSV and invalid requests return HTTP 400 with an error message. Unexpected internal failures return HTTP 500. Responses are strict JSON, without NaN or Infinity literals.

The front end must check `assessmentStatus`. `estimated` means the engine could calculate an estimate under its assumptions; `incomplete` means income/payday or BNPL commitments could not be established. `assessmentWarnings` explains why. In an incomplete assessment, both safe-to-spend fields and each option's `affordable`, `leftAfter` and `shortfallProbability` are null; `cheapest` and `mostLeftUntilPayday` are empty. Render null as unknown, never as zero or an affordable result. Monthly `afterCommitted` and `leftOver` are also null; income is null when not detected, and monthly BNPL is null when its plans are ambiguous. Independent product-price and illustrative payment-schedule information remains available. There is no manual income or repayment-schedule override endpoint yet.

BNPL detection assumes one plan per transaction description. More payments than the provider's plan length, amounts differing by more than a penny, or gaps outside the assumed provider cadence by more than three days make that description uncertain. Its entry has `uncertain: true`, null `remaining` and `instalment`, and an empty `schedule` meaning unknown; it stays in `bnplActive`. Obtain provider-confirmed schedules to resolve this ambiguity. Even a consistent series is an estimate: overlapping plans with indistinguishable payments cannot reliably be separated from a CSV alone. The forecast backtest rejects ambiguous schedules, and the affordability figures reject incomplete assessments rather than counting them as unaffordable.

## Affordability figures

`affordability_figures.py` (task T07b) runs the back end on every statement in `Analysis/mock_statements/` (default `today`: the day after each statement's last transaction) at test prices of £50, £100, £200, £300, £500, £750, £1,000 and £1,500, and writes the pitch figures. It needs `matplotlib` (in `requirements.txt`), a `texformat.pth` in the `.venv` (see Plots in `CLAUDE.md`) and LaTeX (MiKTeX) on the PATH.

```
.venv\Scripts\python -X utf8 affordability_figures.py           # writes everything, about 40 s
.venv\Scripts\python -X utf8 affordability_figures.py --check   # verifies outputs; rewrites nothing
```

Outputs: `Analysis/affordability/households.csv` (one row per persona: tenure, region, household, income, next payday, balance, safeToSpend, monthly left-over, and the outcome at each price: `payNow`, `bnplPlainOnly` or `neither`); `Figures/affordability/affordability_by_price.{pdf,svg,md}` (stacked counts by price); `Figures/affordability/safe_to_spend_vs_income.{pdf,svg,md}` (safe to spend and monthly left-over against monthly net income, coloured by tenure). Each `.md` holds the definitions, data and statistics for its figure.

Also written: `Analysis/value/savings_comparison.csv` and `Figures/value/savings_comparison.{pdf,svg,md}` (money saved per product by buying at the cheapest mainstream price, a 1% cashback card (assumed rate), pay-in-3 float interest and credit-card float interest). `households.csv` also has `safeToSpendBeforeEverydaySpending` and `predictedSpendingMean`.

Limitations: Spearman p-values use a normal approximation (SciPy is not installed); read them only as far below 0.001. PDFs differ byte for byte between runs because of font-subset tags; SVGs do not.

## Spending-forecast backtest

`forecast.py` (task T12) fits forecasts of each persona's discretionary card spending (card payments other than buy-now-pay-later and committed payments, as in `affordability.card_spend`, with committed payments detected on 30 September) on August and September 2026 and scores them on October. Models: last month; mean of August and September; that mean with buy-now-pay-later instalments added back and October's scheduled instalments subtracted; a pooled least-squares regression fitted on August to September (household type, tenure, prior spending, scheduled instalments, net pay) with person-level 10-fold cross-validation (seed 20261107); and log-scale shrinkage towards a pooled prior. Within the month: cumulative spending by day of October, forecast as the average of the August and September curves or as the monthly forecast × d/31. A generator-mean reference calls `mock_statements.spend_model` per persona (it needs the `data/` workbooks).

```
.venv\Scripts\python -X utf8 forecast.py           # writes Analysis/forecast and Figures/forecast
.venv\Scripts\python -X utf8 forecast.py --check   # asserts only; writes nothing
```

The check corrupts October rows and requires every forecast to be unchanged, checks the definitions against `card_spend` and `personas.md`, checks the metrics on a hand example, and checks reproducibility. Outputs: `Analysis/forecast/` (`predictions_october.csv`, `curves_october.csv`, `backtest_summary.md`) and `Figures/forecast/` (`forecast_scatter` and `forecast_errors`, PDF, SVG and `.md`). Needs matplotlib, scipy, the `texformat.pth` link and MiKTeX.

Limitation: the mock statements have independent monthly noise and no persistent habits, so the backtest shows how well the generator's process is recovered, not real behaviour. No model beats the two-month mean detectably (after T15 regeneration, pooled regression minus mean: −£0.32 ± £0.90 per person, p = 0.72).

## Market data

`market_data.py` (task T14) reads the ONS series in `data/` (`ons_mm23_cpi_index_<CDID>.csv` for all-items CPI and the 12 COICOP divisions; `ons_drsi_retail_sales_value_nsa_J5AH.csv`, retail sales value, not seasonally adjusted, Great Britain, all retailers including fuel). It writes `Analysis/market/cpi_uprating_factors.csv`, where `factor` is the September 2026 CPI index divided by the mean index over April 2024 to March 2025 (the Family Spending reference period), for uprating spending to current prices (all items 1.069; housing, water and fuels 1.109; food 1.054). It also writes `Figures/market/retail_sales_seasonality.{pdf,svg,md}`: the index by calendar month, each year scaled to its own mean, 2021 to 2025, with the November and December uplift ((13.7 ± 1.2)% and (19.9 ± 1.1)%).

```
.venv\Scripts\python -X utf8 market_data.py           # writes everything
.venv\Scripts\python -X utf8 market_data.py --check   # 13 factors in (0.9, 1.3), equal to a fresh calculation; .md tables match
```

Limitations: the data are a snapshot (to September 2026); to update, re-download the CSVs from the ONS URLs in `data/README.md` (ONS rate-limits repeated requests) and rerun. The retail index base year is not stated in the file. The years used (2021 to 2025) are fixed in `YEARS`. The seasonality figure shows points with ±SE error bars joined by a line; its y axis does not start at 0.

## Bayesian spending model

`bayes.py` (task T17) models each persona's daily discretionary card spending (defined as in `affordability.card_spend`) as a share of a monthly budget, with a Normal-Inverse-Gamma prior from a population regression on net pay. It updates exactly after each day and gives a Student-t predictive for spending over any future days. `spending_until(tx, payday, hyper=None)` returns the raw Student-t distribution F, or None when no days remain. For decisions, `spending_summary(F)` returns the mean and central 80% interval of max(0, F): negative predictive mass is placed at zero. `spending_risk(F, cushion)` calculates the corresponding shortfall probability, always 1 for a negative cushion. Both the API and `shortfall_probability(tx, price, today=None, payday=None, pay_in_3=False)` use these shared calculations, so negative forecasts cannot increase spendable cash. The latter returns risk after a purchase paid in full or by pay-in-3, with the cushion and spending summary; it raises `StatementError` for missing income or ambiguous BNPL plans. Its default prior is fitted on all 100 mock statements.

```
.venv\Scripts\python -X utf8 bayes.py           # October backtest: writes Analysis/bayes and Figures/bayes (about 25 s)
.venv\Scripts\python -X utf8 bayes.py --check   # asserts only; writes nothing
```

The check asserts that daily updates equal the batch posterior, that 80% intervals cover about 80% on data simulated from the model (seed 20261107), that the shortfall probability does not decrease with price, and that corrupting October changes no fitted quantity. Outputs: `Analysis/bayes/` (`intervals_october.csv`, `shortfall_october.csv`, `bayes_summary.md`) and `Figures/bayes/` (`calibration`, `cold_start`: PDF, SVG and `.md`). Needs scipy, matplotlib, the `texformat.pth` link and MiKTeX.

Limitations: Gaussian days ignore skew, so intervals over a few days are rough. Censoring negative predicted spending at zero enforces non-negative expenditure; it does not establish calibration on real spending shocks. The check compares the censored mean with independent numerical integration and tests negative and zero cash cushions. The model works in calendar months, not pay cycles. The intra-month correlation parameter φ (about 0.02 here) is plugged in without its own uncertainty and reflects the generator's fixed monthly totals; real data would give a larger φ. The prior uses net pay only. A statement with no detected salary raises an error in the Python risk function; the HTTP API instead returns an incomplete assessment. The shortfall test has few intermediate probabilities, so it is uninformative on these data.

