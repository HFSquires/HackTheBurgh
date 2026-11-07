# Bayesian spending model: October backtest

Written by `bayes.py`; regenerate with it. Calibration: `Figures/bayes/calibration.md`; cold start: `Figures/bayes/cold_start.md`.

Source: the 100 statements in `Analysis/mock_statements/`, via `bayes.py` (which reuses `forecast.py` and `affordability.py`). Discretionary spending as in `affordability.card_spend` (card payments that are neither BNPL instalments nor committed payments), committed payments detected on the rows up to 30 September 2026. Every model is fitted on the rows up to 30 September only (August and September); each person's prior comes from a fit on the other persons, by person-level 10-fold cross-validation with forecast.py's folds (seed 20261107). October is used only to score.

Model (full derivation in the docstring of `bayes.py`): daily discretionary spending, Gaussian on the raw scale; within a calendar month of D days each day has mean beta / D (beta: the person's monthly budget) and variance sigma^2, and two days of the same month have correlation (phi - 1) / (D - 1), so a month's total has variance phi D sigma^2. Normal-Inverse-Gamma prior on (beta, sigma^2) centred on a population regression of ln budget on ln net pay; exact conjugate update after each day; Student-t predictive for the sum over any set of future days. The independent-days model is the same with phi fixed at 1.

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

## Point forecast of the October total

Posterior predictive mean of the monthly-budget model against T12's forecasts (`forecast.py`), absolute error per person, n = 100; difference = Bayes minus the other (negative: Bayes better); paired t and Wilcoxon signed-rank tests, two-sided, uncorrected.

Bayes posterior predictive mean: MAE 16.13 ± 1.35 GBP, RMSE 21.02 ± 1.62 GBP, mean error +1.27 ± 2.11 GBP.

| T12 forecast | MAE [GBP] (± SE) | Bayes minus it, absolute error [GBP] (± SE) | Paired t | p (t) | Wilcoxon W | p (W) |
|---|---|---|---|---|---|---|
| Last month (Sep) | 18.23 ± 1.51 | -2.10 ± 1.13 | -1.87 | 0.065 | 2074 | 0.12 |
| Mean Aug-Sep | 16.50 ± 1.37 | -0.38 ± 0.18 | -2.16 | 0.034 | 1803 | 0.013 |
| Pooled regression | 16.12 ± 1.42 | +0.01 ± 0.80 | 0.01 | 0.99 | 2365 | 0.58 |
| Shrinkage | 16.32 ± 1.32 | -0.19 ± 0.36 | -0.53 | 0.6 | 2189 | 0.25 |

## Shortfall: probability of going below zero before the October payday

Purchases of GBP 50, 300, 1200 on 2026-10-01, paid in full or by affordability's plain pay-in-3 schedule (first instalment on the day; the others fall after payday), using each statement up to 30 September. Predicted: `shortfall_probability` with the person's cross-validated prior. Observed: whether the actual balance, less the purchase payments then due, fell below zero on any day from 1 October to the day before the detected payday (2026-10-28). Credits in that window across all statements: 0, so the balance only falls and the lowest balance is the last one. Per-person data: `Analysis/bayes/shortfall_october.csv`.

Brier score = mean of (p - outcome)^2 (± SE across persons); reference = Brier score of always predicting the observed frequency, o (1 - o).

| Plan | Price [GBP] | n | Shortfalls observed | Brier (± SE) | Reference o (1 - o) |
|---|---|---|---|---|---|
| pay now | 50 | 100 | 12 | 0.0092 ± 0.0076 | 0.1056 |
| pay-in-3 | 50 | 100 | 11 | 0.0003 ± 0.0002 | 0.0979 |
| pay now | 300 | 100 | 13 | 0.0011 ± 0.0011 | 0.1131 |
| pay-in-3 | 300 | 100 | 13 | 0.0020 ± 0.0018 | 0.1131 |
| pay now | 1200 | 100 | 26 | 0.0000 ± 0.0000 | 0.1924 |
| pay-in-3 | 1200 | 100 | 14 | 0.0102 ± 0.0077 | 0.1204 |
| pay now | all three | 300 | 51 | 0.0034 ± 0.0026 | 0.1411 |
| pay-in-3 | all three | 300 | 38 | 0.0042 ± 0.0026 | 0.1106 |

Reliability, pay now, all three prices pooled (n = 300; observed frequency ± binomial SE):

| Predicted probability | n | Mean predicted | Shortfalls | Observed frequency (± SE) |
|---|---|---|---|---|
| 0.00 to 0.05 | 247 | 0.000 | 0 | 0.000 ± 0.000 |
| 0.05 to 0.20 | 1 | 0.141 | 1 | 1.000 ± 0.000 |
| 0.20 to 0.50 | 2 | 0.378 | 0 | 0.000 ± 0.000 |
| 0.50 to 0.80 | 0 | not applicable | 0 | not applicable |
| 0.80 to 0.95 | 0 | not applicable | 0 | not applicable |
| 0.95 to 1.00 | 50 | 1.000 | 50 | 1.000 ± 0.000 |

Reliability, pay-in-3, all three prices pooled (n = 300; observed frequency ± binomial SE):

| Predicted probability | n | Mean predicted | Shortfalls | Observed frequency (± SE) |
|---|---|---|---|---|
| 0.00 to 0.05 | 257 | 0.000 | 0 | 0.000 ± 0.000 |
| 0.05 to 0.20 | 3 | 0.120 | 0 | 0.000 ± 0.000 |
| 0.20 to 0.50 | 1 | 0.244 | 0 | 0.000 ± 0.000 |
| 0.50 to 0.80 | 2 | 0.565 | 2 | 1.000 ± 0.000 |
| 0.80 to 0.95 | 2 | 0.855 | 1 | 0.500 ± 0.354 |
| 0.95 to 1.00 | 35 | 0.999 | 35 | 1.000 ± 0.000 |

With 100 persons and few shortfalls these figures are noisy: most persons' cushions are far from zero, so most predictions are near 0 or 1 and only a handful test the model's uncertainty.

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
