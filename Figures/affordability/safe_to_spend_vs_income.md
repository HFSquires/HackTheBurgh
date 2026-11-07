# Safe to spend and monthly left over against monthly net income

Files: `safe_to_spend_vs_income.pdf`, `safe_to_spend_vs_income.svg` (this file: `safe_to_spend_vs_income.md`), written by `affordability_figures.py`. Left panel:
`safeToSpend`; right panel: `monthly.leftOver`; both against income, coloured by tenure, with a line at 0.

## Source data

The 100 statement CSVs in [`Analysis/mock_statements/`](../../Analysis/mock_statements/) (last changed in commit `d7ad54d`), read by `affordability.py` at commit `3e4d094`, called by `affordability_figures.py` (commit `5848aa0` or later). Tenure, region and household type from `Analysis/mock_statements/personas.md` via `affordability.personas()`. Plot style: `TeXFormat.py` sha256 `a33ce9f67e0a`.

## Filters, transformations and units

No persona is excluded (n = 100). x = `income.monthly`, the latest salary credit detected on the statement (net
pay) [GBP]. y = `safeToSpend` [GBP] and `monthly.leftOver` [GBP] from `assess()` (both independent of the price; the
values come from the call at GBP 50). Tenure is the sampled tenure in `personas.md`. asOf ranges from
`2026-10-28` to `2026-10-31`; `today` is the day after each. Quartiles are linearly interpolated (pandas `quantile`).

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
| All | 100 | 4440.77 | 1937.41 | 6451.22 | 4513.80 | -2236.75 | 15594.17 | 6 |
| Owned outright | 22 | 5518.45 | 4381.36 | 7209.95 | 2828.59 | 1346.99 | 15594.17 | 0 |
| Social rented | 29 | 5754.86 | 3127.38 | 7796.35 | 4668.97 | 189.77 | 13501.39 | 0 |
| Private rented | 49 | 2992.05 | 844.28 | 5030.54 | 4186.26 | -2236.75 | 7985.29 | 6 |

`monthly.leftOver` [GBP]:

| Group | n | Median | Q1 | Q3 | IQR | Min | Max | n below 0 |
|---|---|---|---|---|---|---|---|---|
| All | 100 | 961.00 | 361.03 | 1407.49 | 1046.46 | -638.48 | 3638.36 | 12 |
| Owned outright | 22 | 1205.86 | 983.49 | 1613.00 | 629.51 | 233.00 | 3638.36 | 0 |
| Social rented | 29 | 1223.10 | 601.97 | 1746.00 | 1144.03 | -42.75 | 3121.18 | 1 |
| Private rented | 49 | 598.60 | 66.09 | 1073.94 | 1007.85 | -638.48 | 1796.84 | 11 |

Error bars: not applicable (none drawn).

## Fits and tests

Spearman rank correlation with income (average ranks for ties; two-sided p-value from the normal approximation
z = rho sqrt(n - 1)), n = 100. At rho this large the normal and Student t approximations give very different
p-values; read p only as far below 0.001.

| y | rho | p |
|---|---|---|
| `safeToSpend` | 0.847 | 3.52e-17 |
| `monthly.leftOver` | 0.828 | 1.78e-16 |

No fit is drawn.

## Random seed

None (the engine is deterministic; the mock statements were generated with the seed recorded in
`Analysis/mock_statements/personas.md`).

## Interpretation

Median `safeToSpend` is 4440.77 GBP (IQR 4513.80); 6 of
100 households are below 0. Median `monthly.leftOver` is 961.00 GBP; 12 are below 0.
The Spearman correlation of `safeToSpend` with income is 0.847. `safeToSpend` is generous
because everyday spending until payday is not deducted, and the mock end balances are on the high side
(`Analysis/mock_statements/README.md`).
