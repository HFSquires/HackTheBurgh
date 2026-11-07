# Forecast error by model, and by day of October for the cumulative curve

Plot: `forecast_errors.pdf` / `.svg`. Written by `forecast.py`; regenerate with it.

## Source and transformations

Source: the 100 statements in `Analysis/mock_statements/` (persona CSVs and `personas.md`), via `forecast.py`. Target: October 2026 discretionary card spending per persona [GBP], i.e. card (DEB) payments that are neither BNPL instalments nor committed payments, with committed payments detected by `affordability.detect_committed` on the rows up to 30 September (so the fixed football-ticket card payments of 24 personas, which need three months to be detected, count as discretionary in every month). Models are fitted on August and September only; October is used only to score. Per-persona data: `Analysis/forecast/predictions_october.csv`. Statements last changed in commit `7fa4ca1`; `forecast.py` at commit `f209ff6`; `affordability.py` at commit `7098d56` (or later, if uncommitted changes were run).

Panel (a): mean absolute error of each model's October forecast across the 100 personas; error bars are ± one standard error of the mean absolute error across persons; the hatched bar is the generator mean, a reference that uses the generator's internals and is not a forecast. Panel (b): mean absolute error of the predicted cumulative discretionary spending on days 1 to d of October, for d = 1 to 31; bands are ± one standard error across persons. Per-day data: `Analysis/forecast/curves_october.csv`.

## Models (all fitted on August and September only)

Last month: October = September. Mean Aug-Sep: October = mean of August and September. Mean + BNPL schedule: mean of August and September card spending with their BNPL instalments added back, less the instalments that `affordability.detect_bnpl` schedules for October from the rows up to 30 September. Pooled regression: ordinary least squares across persons of September discretionary spending on [intercept, household type (3 dummies, reference: lives alone), tenure (2 dummies, reference: owned outright), August card spending with BNPL added back, BNPL instalments scheduled for September from the rows up to 31 August, net monthly pay]; applied to October with the August-September mean of card spending with BNPL added back, the instalments scheduled for October, and September's net pay. Shrinkage: each person's mean log card spending (BNPL added back) over August and September, shrunk towards a pooled least-squares prediction from household type, tenure and log net pay, with weight w = tau^2 / (tau^2 + s^2/2), where s^2 is the within-person variance of one month's log spending (from the August-September differences) and tau^2 the between-person residual variance less s^2/2; exp of the result, less the BNPL instalments scheduled for October. The regression and shrinkage are fitted with person-level 10-fold cross-validation (seed 20261107): each person's prediction comes from a fit that excludes that person. No parameter was tuned; October enters only the scores.

Within-month curves: mean of the August and September cumulative curves at the same day d; or the pooled regression's October total times d/31 (a constant daily rate); the generator-mean reference times d/31.

## Panel (a): October totals

| Model | n | MAE [GBP] (± SE) | RMSE [GBP] (± SE) | MAPE [%] (± SE) | Mean error [GBP] (± SE) |
|---|---|---|---|---|---|
| Last month (Sep) | 100 | 17.52 ± 1.44 | 22.64 ± 1.69 | 2.59 ± 0.21 | 0.04 ± 2.28 |
| Mean Aug-Sep | 100 | 14.97 ± 1.30 | 19.77 ± 1.52 | 2.17 ± 0.18 | 1.04 ± 1.98 |
| Mean + BNPL schedule | 100 | 15.14 ± 1.27 | 19.72 ± 1.48 | 2.20 ± 0.17 | 1.08 ± 1.98 |
| Pooled regression | 100 | 14.61 ± 1.28 | 19.39 ± 1.50 | 2.08 ± 0.17 | -0.72 ± 1.95 |
| Shrinkage | 100 | 14.79 ± 1.25 | 19.30 ± 1.43 | 2.16 ± 0.17 | 0.74 ± 1.94 |
| Generator mean (reference) | 100 | 12.03 ± 1.04 | 15.86 ± 1.32 | 1.74 ± 0.14 | 1.07 ± 1.59 |

Ratio of each model's RMSE to the reference's: Last month (Sep) 1.43, Mean Aug-Sep 1.25, Mean + BNPL schedule 1.24, Pooled regression 1.22, Shrinkage 1.22. Under the generator, a two-month mean that accounts for BNPL should give about 1.22 (square root of 1.5) and last month alone about 1.41 (square root of 2), before BNPL effects.

Paired comparisons of absolute error (model minus baseline; negative means the model is better), per person, n = 100. Pre-specified primary comparison: pooled regression versus mean Aug-Sep. Holm correction over the 6 comparisons, separately for each test. The Wilcoxon signed-rank test (scipy default, two-sided) drops pairs with zero difference: Mean + BNPL schedule equals Mean Aug-Sep for every persona whose October BNPL instalments match the August-September average.

| Model | Baseline | Mean difference in absolute error [GBP] (± SE) | Paired t | df | p (t) | p (t, Holm) | Wilcoxon W | Non-zero pairs | p (W) | p (W, Holm) | Wilcoxon, Holm, 0.05 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Mean + BNPL schedule | Last month (Sep) | -2.38 ± 1.15 | -2.08 | 99 | 0.041 | 0.17 | 2007 | 100 | 0.075 | 0.3 | no detectable difference |
| Mean + BNPL schedule | Mean Aug-Sep | 0.16 ± 0.33 | 0.50 | 99 | 0.62 | 1 | 63 | 17 | 0.52 | 1 | no detectable difference |
| Pooled regression | Last month (Sep) | -2.91 ± 1.35 | -2.15 | 99 | 0.034 | 0.17 | 1919 | 100 | 0.037 | 0.19 | no detectable difference |
| Pooled regression | Mean Aug-Sep | -0.37 ± 0.73 | -0.50 | 99 | 0.61 | 1 | 2367 | 100 | 0.59 | 1 | no detectable difference |
| Shrinkage | Last month (Sep) | -2.73 ± 1.17 | -2.34 | 99 | 0.021 | 0.13 | 1899 | 100 | 0.031 | 0.19 | no detectable difference |
| Shrinkage | Mean Aug-Sep | -0.19 ± 0.37 | -0.51 | 99 | 0.61 | 1 | 2239 | 100 | 0.33 | 0.98 | no detectable difference |

Pooled-regression coefficients (mean ± SD over the 10 fold fits):

| Term | Coefficient |
|---|---|
| intercept | 13.3 ± 2 |
| couple | -8.16 ± 1.7 |
| lone parent | -11.15 ± 2.8 |
| couple with children | -4.111 ± 2.4 |
| social rented | -1.138 ± 2.8 |
| private rented | 0.3417 ± 2.7 |
| prior card spend incl. BNPL [GBP] | 0.9484 ± 0.0093 |
| BNPL due in target month [GBP] | -1.216 ± 0.11 |
| net monthly pay [GBP] | 0.01052 ± 0.0019 |

Shrinkage, mean over folds: w = 0.9788, s^2 = 0.000683, tau^2 = 0.0158 (log scale).

## Panel (b): cumulative spending at selected days (all days are in the CSV)

n = 100 at every day; uncertainties ± one standard error across persons; MAPE uses the actual cumulative spending on that day.

| Curve | Day | MAE [GBP] (± SE) | RMSE [GBP] (± SE) | MAPE [%] (± SE) |
|---|---|---|---|---|
| Mean of Aug and Sep curves | 7 | 55.31 ± 3.98 | 68.02 ± 4.54 | 40.1 ± 3.7 |
| Mean of Aug and Sep curves | 14 | 70.47 ± 5.72 | 90.59 ± 6.54 | 24.6 ± 2.2 |
| Mean of Aug and Sep curves | 21 | 68.40 ± 5.95 | 90.49 ± 8.21 | 15.2 ± 1.4 |
| Mean of Aug and Sep curves | 28 | 43.41 ± 4.00 | 58.88 ± 5.73 | 7.1 ± 0.6 |
| Pooled regression x d/31 | 7 | 44.75 ± 3.40 | 56.12 ± 3.99 | 32.8 ± 3.2 |
| Pooled regression x d/31 | 14 | 57.33 ± 4.50 | 72.72 ± 5.30 | 19.7 ± 1.5 |
| Pooled regression x d/31 | 21 | 52.01 ± 4.77 | 70.44 ± 6.57 | 11.5 ± 1.1 |
| Pooled regression x d/31 | 28 | 35.31 ± 3.00 | 46.27 ± 4.53 | 5.8 ± 0.5 |
| Generator mean x d/31 (reference) | 7 | 44.39 ± 3.39 | 55.73 ± 3.94 | 32.7 ± 3.3 |
| Generator mean x d/31 (reference) | 14 | 56.39 ± 4.41 | 71.42 ± 5.16 | 19.5 ± 1.5 |
| Generator mean x d/31 (reference) | 21 | 50.82 ± 4.65 | 68.75 ± 6.46 | 11.3 ± 1.1 |
| Generator mean x d/31 (reference) | 28 | 33.63 ± 2.88 | 44.20 ± 4.31 | 5.6 ± 0.5 |

## Interpretation

Mean + BNPL schedule against Last month (Sep): -2.38 ± 1.15 GBP in absolute error (Wilcoxon p = 0.075, Holm 0.3). Mean + BNPL schedule against Mean Aug-Sep: +0.16 ± 0.33 GBP in absolute error (Wilcoxon p = 0.52, Holm 1). Pooled regression against Last month (Sep): -2.91 ± 1.35 GBP in absolute error (Wilcoxon p = 0.037, Holm 0.19). Pooled regression against Mean Aug-Sep: -0.37 ± 0.73 GBP in absolute error (Wilcoxon p = 0.59, Holm 1). Shrinkage against Last month (Sep): -2.73 ± 1.17 GBP in absolute error (Wilcoxon p = 0.031, Holm 0.19). Shrinkage against Mean Aug-Sep: -0.19 ± 0.37 GBP in absolute error (Wilcoxon p = 0.33, Holm 0.98). No model differs detectably from either baseline after Holm correction. Reading the BNPL schedule changes the Aug-Sep mean for only 17 personas, by 6.51 GBP on average (largest 16.44 GBP), small beside the month-to-month noise, so it cannot help much here. The RMSE ratios to the reference (above) are close to the values the generator implies, so most of the remaining error is October's own random variation. Within the month, the constant daily rate from the pooled regression has a lower MAE than the mean of the August and September curves at days 7, 14, 21, 28, and is close to the generator-mean reference: transaction days are drawn uniformly over the month, so the expected cumulative curve is a straight line, while averaging two realised curves keeps their timing noise.

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
