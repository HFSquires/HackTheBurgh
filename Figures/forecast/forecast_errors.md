# Forecast error by model, and by day of October for the cumulative curve

Plot: `forecast_errors.pdf` / `.svg`. Written by `forecast.py`; regenerate with it.

## Source and transformations

Source: the 100 statements in `Analysis/mock_statements/` (persona CSVs and `personas.md`), via `forecast.py`. Target: October 2026 discretionary card spending per persona [GBP], i.e. card (DEB) payments that are neither BNPL instalments nor committed payments, with committed payments detected by `affordability.detect_committed` on the rows up to 30 September (so the fixed football-ticket card payments of 24 personas, which need three months to be detected, count as discretionary in every month). Models are fitted on August and September only; October is used only to score. Per-persona data: `Analysis/forecast/predictions_october.csv`. Statements last changed in commit `4617bf4`; `forecast.py` at commit `4617bf4`; `affordability.py` at commit `2c5e080` (or later, if uncommitted changes were run).

Panel (a): mean absolute error of each model's October forecast across the 100 personas; error bars are ± one standard error of the mean absolute error across persons; the hatched bar is the generator mean, a reference that uses the generator's internals and is not a forecast. Panel (b): mean absolute error of the predicted cumulative discretionary spending on days 1 to d of October, for d = 1 to 31; bands are ± one standard error across persons. Per-day data: `Analysis/forecast/curves_october.csv`.

## Models (all fitted on August and September only)

Last month: October = September. Mean Aug-Sep: October = mean of August and September. Mean + BNPL schedule: mean of August and September card spending with their BNPL instalments added back, less the instalments that `affordability.detect_bnpl` schedules for October from the rows up to 30 September. Pooled regression: ordinary least squares across persons of September discretionary spending on [intercept, household type (3 dummies, reference: lives alone), tenure (2 dummies, reference: owned outright), August card spending with BNPL added back, BNPL instalments scheduled for September from the rows up to 31 August, net monthly pay]; applied to October with the August-September mean of card spending with BNPL added back, the instalments scheduled for October, and September's net pay. Shrinkage: each person's mean log card spending (BNPL added back) over August and September, shrunk towards a pooled least-squares prediction from household type, tenure and log net pay, with weight w = tau^2 / (tau^2 + s^2/2), where s^2 is the within-person variance of one month's log spending (from the August-September differences) and tau^2 the between-person residual variance less s^2/2; exp of the result, less the BNPL instalments scheduled for October. The regression and shrinkage are fitted with person-level 10-fold cross-validation (seed 20261107): each person's prediction comes from a fit that excludes that person. No parameter was tuned; October enters only the scores.

Within-month curves: mean of the August and September cumulative curves at the same day d; or the pooled regression's October total times d/31 (a constant daily rate); the generator-mean reference times d/31.

## Panel (a): October totals

| Model | n | MAE [GBP] (± SE) | RMSE [GBP] (± SE) | MAPE [%] (± SE) | Mean error [GBP] (± SE) |
|---|---|---|---|---|---|
| Last month (Sep) | 100 | 19.34 ± 1.59 | 24.98 ± 1.88 | 2.58 ± 0.20 | -0.04 ± 2.51 |
| Mean Aug-Sep | 100 | 17.41 ± 1.44 | 22.56 ± 1.76 | 2.29 ± 0.17 | 1.32 ± 2.26 |
| Mean + BNPL schedule | 100 | 17.59 ± 1.41 | 22.51 ± 1.73 | 2.33 ± 0.17 | 1.23 ± 2.26 |
| Pooled regression | 100 | 17.08 ± 1.49 | 22.64 ± 1.69 | 2.22 ± 0.18 | -1.46 ± 2.27 |
| Shrinkage | 100 | 17.25 ± 1.39 | 22.12 ± 1.66 | 2.28 ± 0.17 | 0.87 ± 2.22 |
| Generator mean (reference) | 100 | 13.10 ± 1.13 | 17.28 ± 1.42 | 1.75 ± 0.14 | 1.11 ± 1.73 |

Ratio of each model's RMSE to the reference's: Last month (Sep) 1.45, Mean Aug-Sep 1.31, Mean + BNPL schedule 1.30, Pooled regression 1.31, Shrinkage 1.28. Under the generator, a two-month mean that accounts for BNPL should give about 1.22 (square root of 1.5) and last month alone about 1.41 (square root of 2), before BNPL effects.

Paired comparisons of absolute error (model minus baseline; negative means the model is better), per person, n = 100. Pre-specified primary comparison: pooled regression versus mean Aug-Sep. Holm correction over the 6 comparisons, separately for each test. The Wilcoxon signed-rank test (scipy default, two-sided) drops pairs with zero difference: Mean + BNPL schedule equals Mean Aug-Sep for every persona whose October BNPL instalments match the August-September average.

| Model | Baseline | Mean difference in absolute error [GBP] (± SE) | Paired t | df | p (t) | p (t, Holm) | Wilcoxon W | Non-zero pairs | p (W) | p (W, Holm) | Wilcoxon, Holm, 0.05 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Mean + BNPL schedule | Last month (Sep) | -1.75 ± 1.24 | -1.42 | 99 | 0.16 | 0.68 | 2186 | 100 | 0.24 | 0.98 | no detectable difference |
| Mean + BNPL schedule | Mean Aug-Sep | 0.18 ± 0.37 | 0.48 | 99 | 0.64 | 1 | 70 | 18 | 0.5 | 0.98 | no detectable difference |
| Pooled regression | Last month (Sep) | -2.27 ± 1.50 | -1.51 | 99 | 0.14 | 0.68 | 2046 | 100 | 0.1 | 0.6 | no detectable difference |
| Pooled regression | Mean Aug-Sep | -0.33 ± 0.90 | -0.37 | 99 | 0.71 | 1 | 2255 | 100 | 0.35 | 0.98 | no detectable difference |
| Shrinkage | Last month (Sep) | -2.10 ± 1.25 | -1.68 | 99 | 0.096 | 0.58 | 2061 | 100 | 0.11 | 0.6 | no detectable difference |
| Shrinkage | Mean Aug-Sep | -0.16 ± 0.41 | -0.40 | 99 | 0.69 | 1 | 2190 | 100 | 0.25 | 0.98 | no detectable difference |

Pooled-regression coefficients (mean ± SD over the 10 fold fits):

| Term | Coefficient |
|---|---|
| intercept | 14.25 ± 2 |
| couple | -8.292 ± 1.8 |
| lone parent | -11.6 ± 2.9 |
| couple with children | -1.362 ± 2.2 |
| social rented | -0.7608 ± 3.1 |
| private rented | 0.5246 ± 2.9 |
| prior card spend incl. BNPL [GBP] | 0.9415 ± 0.0094 |
| BNPL due in target month [GBP] | -1.237 ± 0.1 |
| net monthly pay [GBP] | 0.01288 ± 0.0022 |

Shrinkage, mean over folds: w = 0.9781, s^2 = 0.000661, tau^2 = 0.0148 (log scale).

## Panel (b): cumulative spending at selected days (all days are in the CSV)

n = 100 at every day; uncertainties ± one standard error across persons; MAPE uses the actual cumulative spending on that day.

| Curve | Day | MAE [GBP] (± SE) | RMSE [GBP] (± SE) | MAPE [%] (± SE) |
|---|---|---|---|---|
| Mean of Aug and Sep curves | 7 | 58.99 ± 4.45 | 73.74 ± 5.37 | 40.0 ± 4.2 |
| Mean of Aug and Sep curves | 14 | 76.25 ± 6.14 | 97.70 ± 6.95 | 24.5 ± 2.2 |
| Mean of Aug and Sep curves | 21 | 72.82 ± 6.73 | 98.92 ± 9.84 | 15.2 ± 1.5 |
| Mean of Aug and Sep curves | 28 | 47.54 ± 4.54 | 65.59 ± 6.03 | 7.1 ± 0.7 |
| Pooled regression x d/31 | 7 | 46.74 ± 3.78 | 59.99 ± 4.56 | 32.6 ± 3.6 |
| Pooled regression x d/31 | 14 | 62.87 ± 4.75 | 78.68 ± 5.68 | 19.9 ± 1.5 |
| Pooled regression x d/31 | 21 | 56.29 ± 5.48 | 78.35 ± 7.48 | 11.6 ± 1.2 |
| Pooled regression x d/31 | 28 | 39.15 ± 3.31 | 51.17 ± 4.79 | 5.9 ± 0.5 |
| Generator mean x d/31 (reference) | 7 | 46.55 ± 3.75 | 59.64 ± 4.50 | 32.7 ± 3.6 |
| Generator mean x d/31 (reference) | 14 | 62.12 ± 4.67 | 77.55 ± 5.59 | 19.9 ± 1.5 |
| Generator mean x d/31 (reference) | 21 | 55.38 ± 5.32 | 76.61 ± 7.33 | 11.5 ± 1.2 |
| Generator mean x d/31 (reference) | 28 | 36.34 ± 3.18 | 48.16 ± 4.41 | 5.6 ± 0.5 |

## Interpretation

Mean + BNPL schedule against Last month (Sep): -1.75 ± 1.24 GBP in absolute error (Wilcoxon p = 0.24, Holm 0.98). Mean + BNPL schedule against Mean Aug-Sep: +0.18 ± 0.37 GBP in absolute error (Wilcoxon p = 0.5, Holm 0.98). Pooled regression against Last month (Sep): -2.27 ± 1.50 GBP in absolute error (Wilcoxon p = 0.1, Holm 0.6). Pooled regression against Mean Aug-Sep: -0.33 ± 0.90 GBP in absolute error (Wilcoxon p = 0.35, Holm 0.98). Shrinkage against Last month (Sep): -2.10 ± 1.25 GBP in absolute error (Wilcoxon p = 0.11, Holm 0.6). Shrinkage against Mean Aug-Sep: -0.16 ± 0.41 GBP in absolute error (Wilcoxon p = 0.25, Holm 0.98). No model differs detectably from either baseline after Holm correction. Reading the BNPL schedule changes the Aug-Sep mean for only 18 personas, by 6.92 GBP on average (largest 17.13 GBP), small beside the month-to-month noise, so it cannot help much here. The RMSE ratios to the reference (above) are close to the values the generator implies, so most of the remaining error is October's own random variation. Within the month, the constant daily rate from the pooled regression has a lower MAE than the mean of the August and September curves at days 7, 14, 21, 28, and is close to the generator-mean reference: transaction days are drawn uniformly over the month, so the expected cumulative curve is a straight line, while averaging two realised curves keeps their timing noise.

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
