# Safe to spend and monthly left over against monthly net income

Files: `safe_to_spend_vs_income.pdf`, `safe_to_spend_vs_income.svg` (this file: `safe_to_spend_vs_income.md`), written by `affordability_figures.py`. Left panel:
`safeToSpend`; right panel: `monthly.leftOver`; both against income, coloured by tenure, with a line at 0.

## Source data

The 100 statement CSVs in [`Analysis/mock_statements/`](../../Analysis/mock_statements/) (last changed in commit `7fa4ca1`), read by `affordability.py` at commit `7098d56` (with `bayes.py` at commit `7098d56` for everyday spending), called by `affordability_figures.py` (commit `f209ff6` or later). Tenure, region and household type from `Analysis/mock_statements/personas.md` via `affordability.personas()`. Plot style: `TeXFormat.py` sha256 `a33ce9f67e0a`.

## Filters, transformations and units

No persona is excluded (n = 100). x = `income.monthly`, the latest salary credit detected on the statement (net
pay) [GBP]. y = `safeToSpend` [GBP] and `monthly.leftOver` [GBP] from `assess()` (both independent of the price; the
values come from the call at GBP 50). Tenure is the sampled tenure in `personas.md`. asOf ranges from
`2026-10-28` to `2026-10-31`; `today` is the day after each. Quartiles are linearly interpolated (pandas `quantile`).

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

One point per household; all values in
[`Analysis/affordability/households.csv`](../../Analysis/affordability/households.csv) (columns `income`,
`safeToSpend`, `monthly.leftOver`, `tenure`). Income ranges from 1003.84 to 5258.61 GBP
(median 2442.14).

## n

All: 100. Owned outright: 22. Social rented: 29. Private rented: 49.

## Descriptive statistics

`safeToSpend` [GBP]:

| Group | n | Median | Q1 | Q3 | IQR | Min | Max | n below 0 |
|---|---|---|---|---|---|---|---|---|
| All | 100 | 4638.00 | 1984.94 | 6579.35 | 4594.40 | -2355.02 | 15747.66 | 7 |
| Owned outright | 22 | 5656.18 | 4456.61 | 7174.41 | 2717.80 | 1352.84 | 15747.66 | 0 |
| Social rented | 29 | 5827.90 | 3380.16 | 7784.35 | 4404.19 | 44.69 | 14063.41 | 0 |
| Private rented | 49 | 3135.50 | 936.16 | 4858.69 | 3922.53 | -2355.02 | 8340.54 | 7 |

`monthly.leftOver` [GBP]:

| Group | n | Median | Q1 | Q3 | IQR | Min | Max | n below 0 |
|---|---|---|---|---|---|---|---|---|
| All | 100 | 1145.84 | 485.44 | 1612.31 | 1126.87 | -593.14 | 3916.00 | 8 |
| Owned outright | 22 | 1400.88 | 1114.80 | 1759.91 | 645.11 | 328.43 | 3916.00 | 0 |
| Social rented | 29 | 1425.27 | 831.95 | 1910.67 | 1078.72 | 0.73 | 3481.64 | 0 |
| Private rented | 49 | 767.38 | 210.25 | 1201.02 | 990.77 | -593.14 | 2071.47 | 8 |

Error bars: not applicable (none drawn).

## Fits and tests

Spearman rank correlation with income (average ranks for ties; two-sided p-value from the normal approximation
z = rho sqrt(n - 1)), n = 100. At rho this large the normal and Student t approximations give very different
p-values; read p only as far below 0.001.

| y | rho | p |
|---|---|---|
| `safeToSpend` | 0.792 | 3.33e-15 |
| `monthly.leftOver` | 0.788 | 4.65e-15 |

No fit is drawn.

## Random seed

None (the engine is deterministic; the mock statements were generated with the seed recorded in
`Analysis/mock_statements/personas.md`).

## Interpretation

Median `safeToSpend` is 4638.00 GBP (IQR 4594.40); 7 of
100 households are below 0. Median `monthly.leftOver` is 1145.84 GBP; 8 are below 0.
The Spearman correlation of `safeToSpend` with income is 0.792. `safeToSpend` deducts the
predicted everyday spending until payday (median 585.06 GBP); the mock end balances
are still on the high side because several ONS spending items are excluded (`Analysis/mock_statements/README.md`).
