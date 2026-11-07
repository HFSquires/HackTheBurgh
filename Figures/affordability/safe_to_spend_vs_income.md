# Safe to spend and monthly left over against monthly net income

Files: `safe_to_spend_vs_income.pdf`, `safe_to_spend_vs_income.svg` (this file: `safe_to_spend_vs_income.md`), written by `affordability_figures.py`. Left panel:
`safeToSpend`; right panel: `monthly.leftOver`; both against income, coloured by tenure, with a line at 0.

## Source data

The 100 statement CSVs in [`Analysis/mock_statements/`](../../Analysis/mock_statements/) (last changed in commit `e01f34f`), read by `affordability.py` at commit `2c5e080` (with `bayes.py` at commit `22804b4` for everyday spending), called by `affordability_figures.py` (commit `2c5e080` or later). Tenure, region and household type from `Analysis/mock_statements/personas.md` via `affordability.personas()`. Plot style: `TeXFormat.py` sha256 `a33ce9f67e0a`.

## Filters, transformations and units

No persona is excluded (n = 100). x = `income.monthly`, the latest salary credit detected on the statement (net
pay) [GBP]. y = `safeToSpend` [GBP] and `monthly.leftOver` [GBP] from `assess()` (both independent of the price; the
values come from the call at GBP 50). Tenure is the sampled tenure in `personas.md`. asOf ranges from
`2026-10-28` to `2026-10-31`; `today` is the day after each. Quartiles are linearly interpolated (pandas `quantile`).

## Definitions

`safeToSpendDefinition`, copied from the engine output: "safeToSpendBeforeEverydaySpending = balance (after the statement's last transaction, on asOf) minus every committed payment (recurring direct debit, standing order or same-amount card payment) and every BNPL instalment predicted after asOf and before nextPayday. safeToSpend = safeToSpendBeforeEverydaySpending minus predictedSpendingUntilPayday.mean, the Bayesian model's (bayes.py) expected everyday card spending from the day after asOf to the day before nextPayday; card spending between asOf and today is part of that prediction."

`predictedSpendingUntilPayday.definition`: "Everyday (discretionary) card spending predicted from the day after asOf to the day before nextPayday by bayes.py (population prior from net pay, updated with this statement's daily card spending): posterior predictive mean and central 80% interval, lower end floored at 0."

Since task T15, safe-to-spend deducts the predicted everyday spending until payday (Bayesian posterior predictive mean);
before T15 it did not, and the earlier counts were correspondingly generous.

`affordableDefinition`, copied from the engine output: "An option is affordable when safeToSpend minus what it takes from the account before nextPayday is at least 0 (payNow, bnplPot, cardPaidInFull: the full price; bnplPlain: the instalments due before payday), and, for bnplPlain, a month's income less committed payments, existing BNPL and typical everyday spending (monthly.leftOver) is at least one later instalment. leftAfter = safeToSpend minus what the option takes before nextPayday."

`monthly.definition`, copied from the engine output: "afterCommitted = income (latest salary credit) - committed (one month of recurring payments) - bnpl (existing BNPL instalments due in the month after asOf); leftOver = afterCommitted - typicalCardSpending (median monthly everyday card spending over the full months in the statement, excluding BNPL and committed card payments)."

Option rules in `assess()` for a price P (instalments are P/3, rounded to the penny, the first due on `today` and the
others one and two months later). `payNow` is affordable when `safeToSpend - P >= 0`. `bnplPot` and `cardPaidInFull`
are affordable under the same condition; the engine's note on the pot reads: "The pot takes the same money as paying now, so it is affordable exactly when paying now is." `bnplPlain` is affordable when
`safeToSpend` minus the instalments due before `nextPayday` is at least 0 and `monthly.leftOver - P/3 >= 0` (T15; before
T15 the second test used `monthly.afterCommitted`, which does not deduct everyday spending). The `card0` option has no
data and is not used here. `today` is the engine default, the day after each statement's last transaction (asOf).

## Plotted data

One point per household; all values in
[`Analysis/affordability/households.csv`](../../Analysis/affordability/households.csv) (columns `income`,
`safeToSpend`, `monthly.leftOver`, `tenure`). Income ranges from 956.98 to 5054.23 GBP
(median 2341.84).

## n

All: 100. Owned outright: 22. Social rented: 29. Private rented: 49.

## Descriptive statistics

`safeToSpend` [GBP]:

| Group | n | Median | Q1 | Q3 | IQR | Min | Max | n below 0 |
|---|---|---|---|---|---|---|---|---|
| All | 100 | 3468.49 | 1240.61 | 5251.51 | 4010.90 | -3181.65 | 14241.86 | 16 |
| Owned outright | 22 | 4621.14 | 3662.29 | 6173.81 | 2511.52 | 755.21 | 14241.86 | 0 |
| Social rented | 29 | 4633.93 | 2101.65 | 6626.54 | 4524.89 | -589.08 | 11972.79 | 1 |
| Private rented | 49 | 2002.05 | -496.99 | 3939.12 | 4436.11 | -3181.65 | 6795.17 | 15 |

`monthly.leftOver` [GBP]:

| Group | n | Median | Q1 | Q3 | IQR | Min | Max | n below 0 |
|---|---|---|---|---|---|---|---|---|
| All | 100 | 842.26 | 305.31 | 1289.09 | 983.78 | -804.00 | 3542.14 | 17 |
| Owned outright | 22 | 1142.42 | 923.36 | 1519.03 | 595.67 | 178.13 | 3542.14 | 0 |
| Social rented | 29 | 1126.90 | 496.49 | 1638.06 | 1141.57 | -154.61 | 2961.53 | 2 |
| Private rented | 49 | 485.88 | -159.64 | 954.11 | 1113.75 | -804.00 | 1670.89 | 15 |

Error bars: not applicable (none drawn).

## Fits and tests

Spearman rank correlation with income (average ranks for ties; two-sided p-value from the normal approximation
z = rho sqrt(n - 1)), n = 100. At rho this large the normal and Student t approximations give very different
p-values; read p only as far below 0.001.

| y | rho | p |
|---|---|---|
| `safeToSpend` | 0.805 | 1.13e-15 |
| `monthly.leftOver` | 0.804 | 1.29e-15 |

No fit is drawn.

## Random seed

None (the engine is deterministic; the mock statements were generated with the seed recorded in
`Analysis/mock_statements/personas.md`).

## Interpretation

Median `safeToSpend` is 3468.49 GBP (IQR 4010.90); 16 of
100 households are below 0. Median `monthly.leftOver` is 842.26 GBP; 17 are below 0.
The Spearman correlation of `safeToSpend` with income is 0.805. `safeToSpend` deducts the
predicted everyday spending until payday (median 639.15 GBP); the mock end balances
are still on the high side because several ONS spending items are excluded (`Analysis/mock_statements/README.md`).
