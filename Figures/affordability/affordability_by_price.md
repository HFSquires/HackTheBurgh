# Affordability by purchase price

Files: `affordability_by_price.pdf`, `affordability_by_price.svg` (this file: `affordability_by_price.md`), written by `affordability_figures.py`.

## Source data

The 100 statement CSVs in [`Analysis/mock_statements/`](../../Analysis/mock_statements/) (last changed in commit `d7ad54d`), read by `affordability.py` at commit `3e4d094`, called by `affordability_figures.py` (commit `5848aa0` or later). Tenure, region and household type from `Analysis/mock_statements/personas.md` via `affordability.personas()`. Plot style: `TeXFormat.py` sha256 `a33ce9f67e0a`.

## Filters, transformations and units

No persona is excluded (n = 100). For each persona, `assess(parse(csv), P)` is called once per test price
P in GBP (50, 100, 200, 300, 500, 750, 1,000, 1,500). Each persona is put in one category per price: `payNow` if the
`payNow` option is affordable (equivalently `bnplPot`, which the engine marks affordable exactly when `payNow` is);
`bnplPlainOnly` if `bnplPlain` is affordable but `payNow` is not; otherwise `neither`. Bars are stacked counts of
households out of 100. Counts of 4 or more are printed on the bars. asOf ranges from `2026-10-28` to `2026-10-31`; `today` is the day after each.

## Definitions

`safeToSpendDefinition`, copied from the engine output: "safeToSpend = balance (after the statement's last transaction, on asOf) minus every committed payment (recurring direct debit, standing order or same-amount card payment) and every BNPL instalment predicted after asOf and before nextPayday. Everyday spending such as food, and any card spending between asOf and today, is not deducted."

Everyday spending until payday (food, travel and other card spending) is NOT deducted in the current definition, so
safe-to-spend is generous: it exceeds what is actually left at payday by whatever is spent on everyday items in
the meantime. The `bnplPlain` rule below likewise uses `afterCommitted`, which does not deduct everyday spending.

`monthly.definition`, copied from the engine output: "afterCommitted = income (latest salary credit) - committed (one month of recurring payments) - bnpl (existing BNPL instalments due in the month after asOf); leftOver = afterCommitted - typicalCardSpending (median monthly everyday card spending over the full months in the statement, excluding BNPL and committed card payments)."

Option rules in `assess()` for a price P (instalments are P/3, rounded to the penny, the first due on `today` and the
others one and two months later). `payNow` is affordable when `safeToSpend - P >= 0`. `bnplPot` is affordable under the
same condition; the engine's note reads: "The pot takes the same money as paying now, so it is affordable exactly when paying now is." `bnplPlain` is affordable when `safeToSpend` minus the instalments
due before `nextPayday` is at least 0 and `monthly.afterCommitted - P/3 >= 0`. The `card0` option has no data and is
not used here. `today` is the engine default, the day after each statement's last transaction (asOf).

## Plotted data

| Price [GBP] | Can pay now (or with the BNPL pot) (`payNow`) | Only with plain pay-in-3 (`bnplPlainOnly`) | Neither (`neither`) | Total |
|---|---|---|---|---|
| 50 | 93 | 1 | 6 | 100 |
| 100 | 93 | 0 | 7 | 100 |
| 200 | 91 | 2 | 7 | 100 |
| 300 | 90 | 3 | 7 | 100 |
| 500 | 90 | 2 | 8 | 100 |
| 750 | 87 | 4 | 9 | 100 |
| 1,000 | 85 | 5 | 10 | 100 |
| 1,500 | 80 | 9 | 11 | 100 |

Per-persona categories: [`Analysis/affordability/households.csv`](../../Analysis/affordability/households.csv)
(columns `outcome_<price>`).

## n

100 households at every price; the n of each stacked segment is the count in the table.

## Descriptive statistics

Counts only, as tabulated. Error bars: not applicable.

## Fits and tests

Not applicable.

## Random seed

None (the engine is deterministic; the mock statements were generated with the seed recorded in
`Analysis/mock_statements/personas.md`).

## Interpretation

At GBP 50, 93 of 100 households can pay now, 1 only with plain pay-in-3 and 6
neither. At GBP 1,500, the counts are 80, 9 and 11. Because everyday spending until payday is
not deducted from safe-to-spend, these counts overstate how many households could pay without strain.
