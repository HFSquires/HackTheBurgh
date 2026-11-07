# Calibration of the posterior predictive intervals, October 2026

Plot: `calibration.pdf` / `.svg`. Written by `bayes.py`; regenerate with it.

## Source and transformations

Source: the 100 statements in `Analysis/mock_statements/`, via `bayes.py` (which reuses `forecast.py` and `affordability.py`). Discretionary spending as in `affordability.card_spend` (card payments that are neither BNPL instalments nor committed payments), committed payments detected on the rows up to 30 September 2026. Every model is fitted on the rows up to 30 September only (August and September); each person's prior comes from a fit on the other persons, by person-level 10-fold cross-validation with forecast.py's folds (seed 20261107). October is used only to score. Statements last changed in commit `4617bf4`; `bayes.py` at commit `22804b4`; `forecast.py` at commit `4617bf4`; `affordability.py` at commit `2c5e080` (or later, if uncommitted changes were run).

Model (full derivation in the docstring of `bayes.py`): daily discretionary spending, Gaussian on the raw scale; within a calendar month of D days each day has mean beta / D (beta: the person's monthly budget) and variance sigma^2, and two days of the same month have correlation (phi - 1) / (D - 1), so a month's total has variance phi D sigma^2. Normal-Inverse-Gamma prior on (beta, sigma^2) centred on a population regression of ln budget on ln net pay; exact conjugate update after each day; Student-t predictive for the sum over any set of future days. The independent-days model is the same with phi fixed at 1.

For each person, central posterior predictive intervals (50 %, 80 %, 95 %) of cumulative October discretionary spending on days 1 to d (d = 7, 14, 21, 28) and of the October total (d = 31), from the posterior after 30 September; empirical coverage = fraction of the 100 persons whose actual value lies inside the interval. Points: empirical coverage against nominal level, offset slightly along x by horizon for legibility; error bars ± one binomial standard error, sqrt(p (1 - p) / n), which is 0 when p = 1. Dashed line: perfect calibration. The 15 points of a panel use the same 100 persons and are not independent. Per-person intervals: `Analysis/bayes/intervals_october.csv`.

## Hyperparameters

| Hyperparameter | Monthly budget, mean ± SD over the 10 folds | Independent days (phi = 1), mean ± SD over folds | Default for live use (all 100 statements, Aug-Oct) |
|---|---|---|---|
| c0 (intercept, ln GBP) | 0.4514 ± 0.1642 | 0.4514 ± 0.1642 | 0.4421 |
| c1 (slope on ln net pay) | 0.7879 ± 0.0205 | 0.7879 ± 0.0205 | 0.7885 |
| tau^2 (between-person variance of ln budget) | 0.01904 ± 0.000921 | 0.001907 ± 0.0008769 | 0.01867 |
| r (daily variance / budget^2) | 0.001145 ± 5.834e-06 | 0.001145 ± 5.834e-06 | 0.001142 |
| a0 | 24.420 ± 2.722 | 24.420 ± 2.722 | 36.995 |
| kappa0 = r / tau^2 | 0.06027 ± 0.002758 | 0.768 ± 0.4554 | 0.06114 |
| phi | 0.0190 ± 0.0007 | 1.0000 ± 0.0000 | 0.0179 |
| persons used per fit | 90 ± 0 | 90 ± 0 | 100 |

## Coverage and mean interval width

Width: mean ± SE across persons [GBP].

| Model | Horizon | Nominal | Empirical coverage (± binomial SE) | n | Mean width [GBP] (± SE) |
|---|---|---|---|---|---|
| Monthly budget (phi fitted) | days 1 to 7 | 0.50 | 0.52 ± 0.05 | 100 | 80.6 ± 2.1 |
| Monthly budget (phi fitted) | days 1 to 7 | 0.80 | 0.79 ± 0.04 | 100 | 153.6 ± 4.1 |
| Monthly budget (phi fitted) | days 1 to 7 | 0.95 | 0.95 ± 0.02 | 100 | 236.1 ± 6.2 |
| Monthly budget (phi fitted) | days 1 to 14 | 0.50 | 0.41 ± 0.05 | 100 | 96.6 ± 2.6 |
| Monthly budget (phi fitted) | days 1 to 14 | 0.80 | 0.74 ± 0.04 | 100 | 184.1 ± 4.9 |
| Monthly budget (phi fitted) | days 1 to 14 | 0.95 | 0.97 ± 0.02 | 100 | 283.0 ± 7.5 |
| Monthly budget (phi fitted) | days 1 to 21 | 0.50 | 0.51 ± 0.05 | 100 | 92.3 ± 2.4 |
| Monthly budget (phi fitted) | days 1 to 21 | 0.80 | 0.82 ± 0.04 | 100 | 175.9 ± 4.6 |
| Monthly budget (phi fitted) | days 1 to 21 | 0.95 | 0.90 ± 0.03 | 100 | 270.4 ± 7.1 |
| Monthly budget (phi fitted) | days 1 to 28 | 0.50 | 0.51 ± 0.05 | 100 | 63.6 ± 1.7 |
| Monthly budget (phi fitted) | days 1 to 28 | 0.80 | 0.86 ± 0.03 | 100 | 121.2 ± 3.2 |
| Monthly budget (phi fitted) | days 1 to 28 | 0.95 | 0.95 ± 0.02 | 100 | 186.2 ± 4.9 |
| Monthly budget (phi fitted) | October total | 0.50 | 0.60 ± 0.05 | 100 | 31.7 ± 0.8 |
| Monthly budget (phi fitted) | October total | 0.80 | 0.85 ± 0.04 | 100 | 60.4 ± 1.6 |
| Monthly budget (phi fitted) | October total | 0.95 | 0.96 ± 0.02 | 100 | 92.8 ± 2.5 |
| Independent days (phi = 1) | days 1 to 7 | 0.50 | 0.56 ± 0.05 | 100 | 90.3 ± 2.4 |
| Independent days (phi = 1) | days 1 to 7 | 0.80 | 0.82 ± 0.04 | 100 | 172.1 ± 4.6 |
| Independent days (phi = 1) | days 1 to 7 | 0.95 | 0.95 ± 0.02 | 100 | 264.6 ± 7.0 |
| Independent days (phi = 1) | days 1 to 14 | 0.50 | 0.53 ± 0.05 | 100 | 128.4 ± 3.4 |
| Independent days (phi = 1) | days 1 to 14 | 0.80 | 0.81 ± 0.04 | 100 | 244.7 ± 6.5 |
| Independent days (phi = 1) | days 1 to 14 | 0.95 | 0.98 ± 0.01 | 100 | 376.1 ± 10.0 |
| Independent days (phi = 1) | days 1 to 21 | 0.50 | 0.59 ± 0.05 | 100 | 158.1 ± 4.2 |
| Independent days (phi = 1) | days 1 to 21 | 0.80 | 0.89 ± 0.03 | 100 | 301.3 ± 8.0 |
| Independent days (phi = 1) | days 1 to 21 | 0.95 | 0.99 ± 0.01 | 100 | 463.1 ± 12.3 |
| Independent days (phi = 1) | days 1 to 28 | 0.50 | 0.68 ± 0.05 | 100 | 183.5 ± 4.9 |
| Independent days (phi = 1) | days 1 to 28 | 0.80 | 0.94 ± 0.02 | 100 | 349.7 ± 9.3 |
| Independent days (phi = 1) | days 1 to 28 | 0.95 | 1.00 ± 0.00 | 100 | 537.5 ± 14.3 |
| Independent days (phi = 1) | October total | 0.50 | 0.73 ± 0.04 | 100 | 193.5 ± 5.1 |
| Independent days (phi = 1) | October total | 0.80 | 0.94 ± 0.02 | 100 | 368.7 ± 9.8 |
| Independent days (phi = 1) | October total | 0.95 | 0.99 ± 0.01 | 100 | 566.8 ± 15.0 |

Mean actual October total: 751.43 GBP.

Random seed: not applicable (no sampling; fold assignment seed 20261107).

## Interpretation

Monthly budget: 14 of 15 coverages lie within two binomial standard errors of nominal; independent days: 6 of 15. The independent-days model treats a month's total as the sum of 31 independent days, which on these statements makes its intervals for the October total about 6.1 times as wide as the budget model's (80 % level), so it covers almost everyone. The budget model's phi, estimated from August and September, carries the generator's fixed monthly totals into the intervals; at 7 days the two models differ little, because a week's spending varies nearly as independent days would.

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
