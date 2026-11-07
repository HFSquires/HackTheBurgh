# Affordability by purchase price

Files: `affordability_by_price.pdf`, `affordability_by_price.svg` (this file: `affordability_by_price.md`), written by `affordability_figures.py`.

## Source data

The 100 statement CSVs in [`Analysis/mock_statements/`](../../Analysis/mock_statements/) (last changed in commit `7fa4ca1`), read by `affordability.py` at commit `7098d56` (with `bayes.py` at commit `7098d56` for everyday spending), called by `affordability_figures.py` (commit `f209ff6` or later). Tenure, region and household type from `Analysis/mock_statements/personas.md` via `affordability.personas()`. Plot style: `TeXFormat.py` sha256 `a33ce9f67e0a`.

## Filters, transformations and units

No persona is excluded (n = 100). For each persona, `assess(parse(csv), P)` is called once per test price
P in GBP (50, 100, 200, 300, 500, 750, 1,000, 1,500). Each persona is put in one category per price: `payNow` if the
`payNow` option is affordable (equivalently `bnplPot`, which the engine marks affordable exactly when `payNow` is);
`bnplPlainOnly` if `bnplPlain` is affordable but `payNow` is not; otherwise `neither`. Bars are stacked counts of
households out of 100. Counts of 4 or more are printed on the bars. asOf ranges from `2026-10-28` to `2026-10-31`; `today` is the day after each.

## Definitions

`safeToSpendDefinition`, copied from the engine output: "safeToSpendBeforeEverydaySpending = balance (after the statement's last transaction, on asOf) minus every committed payment (recurring direct debit, standing order or same-amount card payment) and every BNPL instalment predicted after asOf and before nextPayday. safeToSpend = safeToSpendBeforeEverydaySpending minus predictedSpendingUntilPayday.mean, the Bayesian model's (bayes.py) expected everyday card spending from the day after asOf to the day before nextPayday; card spending between asOf and today is part of that prediction."

`predictedSpendingUntilPayday.definition`: "Everyday (discretionary) card spending predicted from the day after asOf to the day before nextPayday by bayes.py (population prior from net pay, updated with this statement's daily card spending): posterior predictive mean and central 80% interval, for non-negative spending max(0, F), where F is the Student-t predictive."

Since task T15, safe-to-spend deducts the predicted everyday spending until payday (Bayesian posterior predictive mean);
before T15 it did not, and the earlier counts were correspondingly generous.

`affordableDefinition`, copied from the engine output: "An option is affordable when safeToSpend minus what it takes from the account before nextPayday is at least 0 (payNow, bnplPot, cardPaidInFull: the full price; bnplPlain: the instalments due before payday), and, for bnplPlain, a month's income less committed payments, existing BNPL and typical everyday spending (monthly.leftOver) is at least one later instalment. leftAfter = safeToSpend minus what the option takes before nextPayday. What an option takes before payday includes anything due today, even when today is payday. These quantities and affordability are null when assessmentStatus is incomplete; assessmentWarnings explains the missing information. An estimated assessment can also carry warnings, about estimates weaker than usual."

`monthly.definition`, copied from the engine output: "afterCommitted = income (latest salary credit) - committed (one month of recurring payments) - bnpl (existing BNPL instalments due in the month after asOf); leftOver = afterCommitted - typicalCardSpending (median monthly everyday card spending over the full calendar months in the statement, excluding BNPL and committed card payments; when there is none, monthsUsed is 0 and it is bayes.py's posterior mean monthly budget, with a warning in assessmentWarnings)."

Option rules in `assess()` for a price P (instalments are P/3, rounded to the penny, the first due on `today` and the
others one and two months later). `payNow` is affordable when `safeToSpend - P >= 0`. `bnplPot` and `cardPaidInFull`
are affordable under the same condition; the engine's note on the pot reads: "The pot takes the same money as paying now, so it is affordable exactly when paying now is." `bnplPlain` is affordable when
`safeToSpend` minus the instalments due before `nextPayday` is at least 0 and `monthly.leftOver - P/3 >= 0` (T15; before
T15 the second test used `monthly.afterCommitted`, which does not deduct everyday spending). The `card0` option has no
data and is not used here. `today` is the engine default, the day after each statement's last transaction (asOf).

## Plotted data

| Price [GBP] | Can pay now (or with the BNPL pot) (`payNow`) | Only with plain pay-in-3 (`bnplPlainOnly`) | Neither (`neither`) | Total |
|---|---|---|---|---|
| 50 | 91 | 0 | 9 | 100 |
| 100 | 91 | 0 | 9 | 100 |
| 200 | 90 | 0 | 10 | 100 |
| 300 | 90 | 0 | 10 | 100 |
| 500 | 89 | 0 | 11 | 100 |
| 750 | 87 | 0 | 13 | 100 |
| 1,000 | 85 | 0 | 15 | 100 |
| 1,500 | 79 | 0 | 21 | 100 |

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

At GBP 50, 91 of 100 households can pay now, 0 only with plain pay-in-3 and 9
neither. At GBP 1,500, the counts are 79, 0 and 21. Safe-to-spend deducts the predicted
everyday spending until payday, so a household counted under `payNow` is expected to stay at or above zero until payday
on average; `shortfallProbability` in the engine output gives the chance that it does not. The mock statements are
synthetic, so the counts describe the generator's households, not real customers.
