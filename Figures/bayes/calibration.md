# Calibration of the posterior predictive intervals, October 2026

Plot: `calibration.pdf` / `.svg`. Written by `bayes.py`; regenerate with it.

## Source and transformations

Source: the 100 statements in `Analysis/mock_statements/`, via `bayes.py` (which reuses `forecast.py` and `affordability.py`). Discretionary spending as in `affordability.card_spend` (card payments that are neither BNPL instalments nor committed payments), committed payments detected on the rows up to 30 September 2026. Every model is fitted on the rows up to 30 September only (August and September); each person's prior comes from a fit on the other persons, by person-level 10-fold cross-validation with forecast.py's folds (seed 20261107). October is used only to score. Statements last changed in commit `7fa4ca1`; `bayes.py` at commit `7098d56`; `forecast.py` at commit `f209ff6`; `affordability.py` at commit `7098d56` (or later, if uncommitted changes were run).

Model (full derivation in the docstring of `bayes.py`): daily discretionary spending, Gaussian on the raw scale; within a calendar month of D days each day has mean beta / D (beta: the person's monthly budget) and variance sigma^2, and two days of the same month have correlation (phi - 1) / (D - 1), so a month's total has variance phi D sigma^2. Normal-Inverse-Gamma prior on (beta, sigma^2) centred on a population regression of ln budget on ln net pay; exact conjugate update after each day; Student-t predictive for the sum over any set of future days. The independent-days model is the same with phi fixed at 1.

For each person, central posterior predictive intervals (50 %, 80 %, 95 %) of cumulative October discretionary spending on days 1 to d (d = 7, 14, 21, 28) and of the October total (d = 31), from the posterior after 30 September; empirical coverage = fraction of the 100 persons whose actual value lies inside the interval. Points: empirical coverage against nominal level, offset slightly along x by horizon for legibility; error bars ± one binomial standard error, sqrt(p (1 - p) / n), which is 0 when p = 1. Dashed line: perfect calibration. The 15 points of a panel use the same 100 persons and are not independent. Per-person intervals: `Analysis/bayes/intervals_october.csv`.

## Hyperparameters

| Hyperparameter | Monthly budget, mean ± SD over the 10 folds | Independent days (phi = 1), mean ± SD over folds | Default for live use (all 100 statements, Aug-Oct) |
|---|---|---|---|
| c0 (intercept, ln GBP) | 0.4635 ± 0.1578 | 0.4635 ± 0.1578 | 0.4558 |
| c1 (slope on ln net pay) | 0.7753 ± 0.0198 | 0.7753 ± 0.0198 | 0.7757 |
| tau^2 (between-person variance of ln budget) | 0.01915 ± 0.0008124 | 0.002014 ± 0.0007825 | 0.01879 |
| r (daily variance / budget^2) | 0.001147 ± 6.224e-06 | 0.001147 ± 6.224e-06 | 0.001144 |
| a0 | 24.553 ± 1.568 | 24.553 ± 1.568 | 38.900 |
| kappa0 = r / tau^2 | 0.05996 ± 0.002435 | 0.6648 ± 0.292 | 0.06088 |
| phi | 0.0199 ± 0.0008 | 1.0000 ± 0.0000 | 0.0180 |
| persons used per fit | 90 ± 0 | 90 ± 0 | 100 |

## Coverage and mean interval width

Width: mean ± SE across persons [GBP].

| Model | Horizon | Nominal | Empirical coverage (± binomial SE) | n | Mean width [GBP] (± SE) |
|---|---|---|---|---|---|
| Monthly budget (phi fitted) | days 1 to 7 | 0.50 | 0.50 ± 0.05 | 100 | 73.9 ± 1.9 |
| Monthly budget (phi fitted) | days 1 to 7 | 0.80 | 0.76 ± 0.04 | 100 | 140.8 ± 3.7 |
| Monthly budget (phi fitted) | days 1 to 7 | 0.95 | 0.96 ± 0.02 | 100 | 216.5 ± 5.6 |
| Monthly budget (phi fitted) | days 1 to 14 | 0.50 | 0.42 ± 0.05 | 100 | 88.6 ± 2.3 |
| Monthly budget (phi fitted) | days 1 to 14 | 0.80 | 0.71 ± 0.05 | 100 | 168.9 ± 4.4 |
| Monthly budget (phi fitted) | days 1 to 14 | 0.95 | 0.97 ± 0.02 | 100 | 259.6 ± 6.8 |
| Monthly budget (phi fitted) | days 1 to 21 | 0.50 | 0.49 ± 0.05 | 100 | 84.7 ± 2.2 |
| Monthly budget (phi fitted) | days 1 to 21 | 0.80 | 0.83 ± 0.04 | 100 | 161.4 ± 4.2 |
| Monthly budget (phi fitted) | days 1 to 21 | 0.95 | 0.92 ± 0.03 | 100 | 248.1 ± 6.5 |
| Monthly budget (phi fitted) | days 1 to 28 | 0.50 | 0.53 ± 0.05 | 100 | 58.6 ± 1.5 |
| Monthly budget (phi fitted) | days 1 to 28 | 0.80 | 0.84 ± 0.04 | 100 | 111.6 ± 2.9 |
| Monthly budget (phi fitted) | days 1 to 28 | 0.95 | 0.95 ± 0.02 | 100 | 171.6 ± 4.5 |
| Monthly budget (phi fitted) | October total | 0.50 | 0.62 ± 0.05 | 100 | 29.8 ± 0.8 |
| Monthly budget (phi fitted) | October total | 0.80 | 0.85 ± 0.04 | 100 | 56.7 ± 1.5 |
| Monthly budget (phi fitted) | October total | 0.95 | 0.97 ± 0.02 | 100 | 87.2 ± 2.3 |
| Independent days (phi = 1) | days 1 to 7 | 0.50 | 0.50 ± 0.05 | 100 | 82.8 ± 2.2 |
| Independent days (phi = 1) | days 1 to 7 | 0.80 | 0.81 ± 0.04 | 100 | 157.8 ± 4.1 |
| Independent days (phi = 1) | days 1 to 7 | 0.95 | 0.94 ± 0.02 | 100 | 242.6 ± 6.3 |
| Independent days (phi = 1) | days 1 to 14 | 0.50 | 0.55 ± 0.05 | 100 | 117.8 ± 3.1 |
| Independent days (phi = 1) | days 1 to 14 | 0.80 | 0.81 ± 0.04 | 100 | 224.4 ± 5.9 |
| Independent days (phi = 1) | days 1 to 14 | 0.95 | 0.98 ± 0.01 | 100 | 344.9 ± 9.0 |
| Independent days (phi = 1) | days 1 to 21 | 0.50 | 0.57 ± 0.05 | 100 | 145.1 ± 3.8 |
| Independent days (phi = 1) | days 1 to 21 | 0.80 | 0.89 ± 0.03 | 100 | 276.4 ± 7.2 |
| Independent days (phi = 1) | days 1 to 21 | 0.95 | 0.99 ± 0.01 | 100 | 424.8 ± 11.1 |
| Independent days (phi = 1) | days 1 to 28 | 0.50 | 0.66 ± 0.05 | 100 | 168.4 ± 4.4 |
| Independent days (phi = 1) | days 1 to 28 | 0.80 | 0.94 ± 0.02 | 100 | 320.9 ± 8.4 |
| Independent days (phi = 1) | days 1 to 28 | 0.95 | 1.00 ± 0.00 | 100 | 493.2 ± 12.9 |
| Independent days (phi = 1) | October total | 0.50 | 0.71 ± 0.05 | 100 | 177.6 ± 4.6 |
| Independent days (phi = 1) | October total | 0.80 | 0.95 ± 0.02 | 100 | 338.4 ± 8.8 |
| Independent days (phi = 1) | October total | 0.95 | 1.00 ± 0.00 | 100 | 520.1 ± 13.6 |

Mean actual October total: 689.55 GBP.

Random seed: not applicable (no sampling; fold assignment seed 20261107).

## Interpretation

Monthly budget: 14 of 15 coverages lie within two binomial standard errors of nominal; independent days: 6 of 15. The independent-days model treats a month's total as the sum of 31 independent days, which on these statements makes its intervals for the October total about 6.0 times as wide as the budget model's (80 % level), so it covers almost everyone. The budget model's phi, estimated from August and September, carries the generator's fixed monthly totals into the intervals; at 7 days the two models differ little, because a week's spending varies nearly as independent days would.

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
