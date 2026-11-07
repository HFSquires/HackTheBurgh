# Calibration of the posterior predictive intervals, October 2026

Plot: `calibration.pdf` / `.svg`. Written by `bayes.py`; regenerate with it.

## Source and transformations

Source: the 100 statements in `Analysis/mock_statements/`, via `bayes.py` (which reuses `forecast.py` and `affordability.py`). Discretionary spending as in `affordability.card_spend` (card payments that are neither BNPL instalments nor committed payments), committed payments detected on the rows up to 30 September 2026. Every model is fitted on the rows up to 30 September only (August and September); each person's prior comes from a fit on the other persons, by person-level 10-fold cross-validation with forecast.py's folds (seed 20261107). October is used only to score.

Model (full derivation in the docstring of `bayes.py`): daily discretionary spending, Gaussian on the raw scale; within a calendar month of D days each day has mean beta / D (beta: the person's monthly budget) and variance sigma^2, and two days of the same month have correlation (phi - 1) / (D - 1), so a month's total has variance phi D sigma^2. Normal-Inverse-Gamma prior on (beta, sigma^2) centred on a population regression of ln budget on ln net pay; exact conjugate update after each day; Student-t predictive for the sum over any set of future days. The independent-days model is the same with phi fixed at 1.

For each person, central posterior predictive intervals (50 %, 80 %, 95 %) of cumulative October discretionary spending on days 1 to d (d = 7, 14, 21, 28) and of the October total (d = 31), from the posterior after 30 September; empirical coverage = fraction of the 100 persons whose actual value lies inside the interval. Points: empirical coverage against nominal level, offset slightly along x by horizon for legibility; error bars ± one binomial standard error, sqrt(p (1 - p) / n), which is 0 when p = 1. Dashed line: perfect calibration. The 15 points of a panel use the same 100 persons and are not independent. Per-person intervals: `Analysis/bayes/intervals_october.csv`.

## Hyperparameters

| Hyperparameter | Monthly budget, mean ± SD over the 10 folds | Independent days (phi = 1), mean ± SD over folds | Default for live use (all 100 statements, Aug-Oct) |
|---|---|---|---|
| c0 (intercept, ln GBP) | 0.4626 ± 0.1646 | 0.4626 ± 0.1646 | 0.4543 |
| c1 (slope on ln net pay) | 0.7833 ± 0.0206 | 0.7833 ± 0.0206 | 0.7838 |
| tau^2 (between-person variance of ln budget) | 0.01926 ± 0.0009473 | 0.001906 ± 0.0009026 | 0.01887 |
| r (daily variance / budget^2) | 0.00116 ± 6.097e-06 | 0.00116 ± 6.097e-06 | 0.001156 |
| a0 | 24.260 ± 2.699 | 24.260 ± 2.699 | 36.867 |
| kappa0 = r / tau^2 | 0.06034 ± 0.002815 | 0.7992 ± 0.5096 | 0.06127 |
| phi | 0.0188 ± 0.0007 | 1.0000 ± 0.0000 | 0.0178 |
| persons used per fit | 90 ± 0 | 90 ± 0 | 100 |

## Coverage and mean interval width

Width: mean ± SE across persons [GBP].

| Model | Horizon | Nominal | Empirical coverage (± binomial SE) | n | Mean width [GBP] (± SE) |
|---|---|---|---|---|---|
| Monthly budget (phi fitted) | days 1 to 7 | 0.50 | 0.51 ± 0.05 | 100 | 76.7 ± 2.0 |
| Monthly budget (phi fitted) | days 1 to 7 | 0.80 | 0.81 ± 0.04 | 100 | 146.1 ± 3.8 |
| Monthly budget (phi fitted) | days 1 to 7 | 0.95 | 0.96 ± 0.02 | 100 | 224.6 ± 5.9 |
| Monthly budget (phi fitted) | days 1 to 14 | 0.50 | 0.43 ± 0.05 | 100 | 91.9 ± 2.4 |
| Monthly budget (phi fitted) | days 1 to 14 | 0.80 | 0.73 ± 0.04 | 100 | 175.1 ± 4.6 |
| Monthly budget (phi fitted) | days 1 to 14 | 0.95 | 0.98 ± 0.01 | 100 | 269.2 ± 7.1 |
| Monthly budget (phi fitted) | days 1 to 21 | 0.50 | 0.51 ± 0.05 | 100 | 87.8 ± 2.3 |
| Monthly budget (phi fitted) | days 1 to 21 | 0.80 | 0.81 ± 0.04 | 100 | 167.3 ± 4.4 |
| Monthly budget (phi fitted) | days 1 to 21 | 0.95 | 0.90 ± 0.03 | 100 | 257.1 ± 6.8 |
| Monthly budget (phi fitted) | days 1 to 28 | 0.50 | 0.53 ± 0.05 | 100 | 60.4 ± 1.6 |
| Monthly budget (phi fitted) | days 1 to 28 | 0.80 | 0.86 ± 0.03 | 100 | 115.2 ± 3.0 |
| Monthly budget (phi fitted) | days 1 to 28 | 0.95 | 0.94 ± 0.02 | 100 | 177.0 ± 4.7 |
| Monthly budget (phi fitted) | October total | 0.50 | 0.60 ± 0.05 | 100 | 30.0 ± 0.8 |
| Monthly budget (phi fitted) | October total | 0.80 | 0.84 ± 0.04 | 100 | 57.2 ± 1.5 |
| Monthly budget (phi fitted) | October total | 0.95 | 0.96 ± 0.02 | 100 | 87.9 ± 2.3 |
| Independent days (phi = 1) | days 1 to 7 | 0.50 | 0.55 ± 0.05 | 100 | 85.9 ± 2.3 |
| Independent days (phi = 1) | days 1 to 7 | 0.80 | 0.82 ± 0.04 | 100 | 163.7 ± 4.3 |
| Independent days (phi = 1) | days 1 to 7 | 0.95 | 0.95 ± 0.02 | 100 | 251.6 ± 6.6 |
| Independent days (phi = 1) | days 1 to 14 | 0.50 | 0.54 ± 0.05 | 100 | 122.1 ± 3.2 |
| Independent days (phi = 1) | days 1 to 14 | 0.80 | 0.80 ± 0.04 | 100 | 232.7 ± 6.1 |
| Independent days (phi = 1) | days 1 to 14 | 0.95 | 0.98 ± 0.01 | 100 | 357.7 ± 9.4 |
| Independent days (phi = 1) | days 1 to 21 | 0.50 | 0.58 ± 0.05 | 100 | 150.4 ± 4.0 |
| Independent days (phi = 1) | days 1 to 21 | 0.80 | 0.89 ± 0.03 | 100 | 286.5 ± 7.6 |
| Independent days (phi = 1) | days 1 to 21 | 0.95 | 0.99 ± 0.01 | 100 | 440.4 ± 11.6 |
| Independent days (phi = 1) | days 1 to 28 | 0.50 | 0.67 ± 0.05 | 100 | 174.5 ± 4.6 |
| Independent days (phi = 1) | days 1 to 28 | 0.80 | 0.94 ± 0.02 | 100 | 332.5 ± 8.8 |
| Independent days (phi = 1) | days 1 to 28 | 0.95 | 1.00 ± 0.00 | 100 | 511.1 ± 13.5 |
| Independent days (phi = 1) | October total | 0.50 | 0.72 ± 0.04 | 100 | 184.0 ± 4.9 |
| Independent days (phi = 1) | October total | 0.80 | 0.94 ± 0.02 | 100 | 350.6 ± 9.3 |
| Independent days (phi = 1) | October total | 0.95 | 0.99 ± 0.01 | 100 | 539.0 ± 14.2 |

Mean actual October total: 710.45 GBP.

Random seed: not applicable (no sampling; fold assignment seed 20261107).

## Interpretation

Monthly budget: 13 of 15 coverages lie within two binomial standard errors of nominal; independent days: 6 of 15. The independent-days model treats a month's total as the sum of 31 independent days, which on these statements makes its intervals for the October total about 6.1 times as wide as the budget model's (80 % level), so it covers almost everyone. The budget model's phi, estimated from August and September, carries the generator's fixed monthly totals into the intervals; at 7 days the two models differ little, because a week's spending varies nearly as independent days would.

## What these data can and cannot show

`mock_statements.py` draws each persona's card spending in each of nine ONS categories, each month, as the modelled
monthly mean (ONS Family Spending for the persona's region, household type and income decile) multiplied by an independent
factor drawn uniformly between 0.9 and 1.1, less any BNPL instalment charged to that category that month; transaction days
are uniform over the month and amounts are split by lognormal weights. The factors are independent across months and
categories, so a persona has no habit beyond its deterministic mean, no trend, no seasonality, no irregular large purchase
and no change of income. The best possible forecast of October is therefore the generator mean less the BNPL instalments
due in October (the reference), whose error is October's own noise; a forecast that averages August and September adds
those months' noise (error variance 1.5 times the reference's once the BNPL schedule is accounted for; last month alone,
2 times). The naive baselines are thus close to the best achievable apart from BNPL, and a learned model can gain only by
reading the BNPL schedule and by shrinking a two-month mean towards a pooled estimate. This backtest measures how well the
models recover the generator's process, not how real customers behave.
