# Forecast error by model, and by day of October for the cumulative curve

Plot: `forecast_errors.pdf` / `.svg`. Written by `forecast.py`; regenerate with it.

## Source and transformations

Source: the 100 statements in `Analysis/mock_statements/` (persona CSVs and `personas.md`), via `forecast.py`. Target: October 2026 discretionary card spending per persona [GBP], i.e. card (DEB) payments that are neither BNPL instalments nor committed payments, with committed payments detected by `affordability.detect_committed` on the rows up to 30 September (so the fixed football-ticket card payments of 24 personas, which need three months to be detected, count as discretionary in every month). Models are fitted on August and September only; October is used only to score. Per-persona data: `Analysis/forecast/predictions_october.csv`.

Panel (a): mean absolute error of each model's October forecast across the 100 personas; error bars are ± one standard error of the mean absolute error across persons; the hatched bar is the generator mean, a reference that uses the generator's internals and is not a forecast. Panel (b): mean absolute error of the predicted cumulative discretionary spending on days 1 to d of October, for d = 1 to 31; bands are ± one standard error across persons. Per-day data: `Analysis/forecast/curves_october.csv`.

## Models (all fitted on August and September only)

Last month: October = September. Mean Aug-Sep: October = mean of August and September. Mean + BNPL schedule: mean of August and September card spending with their BNPL instalments added back, less the instalments that `affordability.detect_bnpl` schedules for October from the rows up to 30 September. Pooled regression: ordinary least squares across persons of September discretionary spending on [intercept, household type (3 dummies, reference: lives alone), tenure (2 dummies, reference: owned outright), August card spending with BNPL added back, BNPL instalments scheduled for September from the rows up to 31 August, net monthly pay]; applied to October with the August-September mean of card spending with BNPL added back, the instalments scheduled for October, and September's net pay. Shrinkage: each person's mean log card spending (BNPL added back) over August and September, shrunk towards a pooled least-squares prediction from household type, tenure and log net pay, with weight w = tau^2 / (tau^2 + s^2/2), where s^2 is the within-person variance of one month's log spending (from the August-September differences) and tau^2 the between-person residual variance less s^2/2; exp of the result, less the BNPL instalments scheduled for October. The regression and shrinkage are fitted with person-level 10-fold cross-validation (seed 20261107): each person's prediction comes from a fit that excludes that person. No parameter was tuned; October enters only the scores.

Within-month curves: mean of the August and September cumulative curves at the same day d; or the pooled regression's October total times d/31 (a constant daily rate); the generator-mean reference times d/31.

## Panel (a): October totals

| Model | n | MAE [GBP] (± SE) | RMSE [GBP] (± SE) | MAPE [%] (± SE) | Mean error [GBP] (± SE) |
|---|---|---|---|---|---|
| Last month (Sep) | 100 | 18.23 ± 1.51 | 23.60 ± 1.78 | 2.58 ± 0.20 | -0.07 ± 2.37 |
| Mean Aug-Sep | 100 | 16.50 ± 1.37 | 21.38 ± 1.68 | 2.30 ± 0.17 | 1.26 ± 2.15 |
| Mean + BNPL schedule | 100 | 16.67 ± 1.34 | 21.33 ± 1.65 | 2.33 ± 0.17 | 1.18 ± 2.14 |
| Pooled regression | 100 | 16.12 ± 1.42 | 21.45 ± 1.61 | 2.22 ± 0.18 | -1.44 ± 2.15 |
| Shrinkage | 100 | 16.32 ± 1.32 | 20.97 ± 1.58 | 2.28 ± 0.17 | 0.85 ± 2.11 |
| Generator mean (reference) | 100 | 12.36 ± 1.07 | 16.28 ± 1.34 | 1.74 ± 0.14 | 1.08 ± 1.63 |

Ratio of each model's RMSE to the reference's: Last month (Sep) 1.45, Mean Aug-Sep 1.31, Mean + BNPL schedule 1.31, Pooled regression 1.32, Shrinkage 1.29. Under the generator, a two-month mean that accounts for BNPL should give about 1.22 (square root of 1.5) and last month alone about 1.41 (square root of 2), before BNPL effects.

Paired comparisons of absolute error (model minus baseline; negative means the model is better), per person, n = 100. Pre-specified primary comparison: pooled regression versus mean Aug-Sep. Holm correction over the 6 comparisons, separately for each test. The Wilcoxon signed-rank test (scipy default, two-sided) drops pairs with zero difference: Mean + BNPL schedule equals Mean Aug-Sep for every persona whose October BNPL instalments match the August-September average.

| Model | Baseline | Mean difference in absolute error [GBP] (± SE) | Paired t | df | p (t) | p (t, Holm) | Wilcoxon W | Non-zero pairs | p (W) | p (W, Holm) | Wilcoxon, Holm, 0.05 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Mean + BNPL schedule | Last month (Sep) | -1.56 ± 1.18 | -1.33 | 99 | 0.19 | 0.75 | 2204 | 100 | 0.27 | 0.83 | no detectable difference |
| Mean + BNPL schedule | Mean Aug-Sep | 0.16 ± 0.36 | 0.45 | 99 | 0.66 | 1 | 130 | 24 | 0.56 | 0.83 | no detectable difference |
| Pooled regression | Last month (Sep) | -2.11 ± 1.43 | -1.47 | 99 | 0.14 | 0.72 | 2067 | 100 | 0.12 | 0.69 | no detectable difference |
| Pooled regression | Mean Aug-Sep | -0.38 ± 0.86 | -0.45 | 99 | 0.66 | 1 | 2214 | 100 | 0.28 | 0.83 | no detectable difference |
| Shrinkage | Last month (Sep) | -1.92 ± 1.19 | -1.61 | 99 | 0.11 | 0.66 | 2080 | 100 | 0.13 | 0.69 | no detectable difference |
| Shrinkage | Mean Aug-Sep | -0.19 ± 0.40 | -0.48 | 99 | 0.63 | 1 | 2159 | 100 | 0.21 | 0.83 | no detectable difference |

Pooled-regression coefficients (mean ± SD over the 10 fold fits):

| Term | Coefficient |
|---|---|
| intercept | 13.7 ± 1.9 |
| couple | -7.986 ± 1.7 |
| lone parent | -10.75 ± 2.8 |
| couple with children | -1.269 ± 2.1 |
| social rented | -0.9225 ± 2.9 |
| private rented | 0.3823 ± 2.8 |
| prior card spend incl. BNPL [GBP] | 0.9416 ± 0.0094 |
| BNPL due in target month [GBP] | -1.228 ± 0.1 |
| net monthly pay [GBP] | 0.01259 ± 0.0021 |

Shrinkage, mean over folds: w = 0.9782, s^2 = 0.000662, tau^2 = 0.0149 (log scale).

## Panel (b): cumulative spending at selected days (all days are in the CSV)

n = 100 at every day; uncertainties ± one standard error across persons; MAPE uses the actual cumulative spending on that day.

| Curve | Day | MAE [GBP] (± SE) | RMSE [GBP] (± SE) | MAPE [%] (± SE) |
|---|---|---|---|---|
| Mean of Aug and Sep curves | 7 | 56.33 ± 4.24 | 70.37 ± 5.13 | 40.4 ± 4.2 |
| Mean of Aug and Sep curves | 14 | 72.79 ± 5.87 | 93.30 ± 6.61 | 24.7 ± 2.2 |
| Mean of Aug and Sep curves | 21 | 69.25 ± 6.40 | 94.11 ± 9.33 | 15.3 ± 1.5 |
| Mean of Aug and Sep curves | 28 | 45.18 ± 4.33 | 62.39 ± 5.74 | 7.1 ± 0.7 |
| Pooled regression x d/31 | 7 | 44.49 ± 3.59 | 57.03 ± 4.33 | 32.8 ± 3.6 |
| Pooled regression x d/31 | 14 | 59.98 ± 4.52 | 74.98 ± 5.35 | 20.1 ± 1.5 |
| Pooled regression x d/31 | 21 | 53.39 ± 5.21 | 74.44 ± 7.07 | 11.6 ± 1.2 |
| Pooled regression x d/31 | 28 | 37.18 ± 3.16 | 48.67 ± 4.57 | 6.0 ± 0.5 |
| Generator mean x d/31 (reference) | 7 | 44.26 ± 3.56 | 56.69 ± 4.27 | 32.8 ± 3.6 |
| Generator mean x d/31 (reference) | 14 | 59.35 ± 4.43 | 73.90 ± 5.25 | 20.0 ± 1.5 |
| Generator mean x d/31 (reference) | 21 | 52.48 ± 5.06 | 72.76 ± 6.93 | 11.5 ± 1.2 |
| Generator mean x d/31 (reference) | 28 | 34.61 ± 3.01 | 45.80 ± 4.22 | 5.6 ± 0.5 |

## Interpretation

Mean + BNPL schedule against Last month (Sep): -1.56 ± 1.18 GBP in absolute error (Wilcoxon p = 0.27, Holm 0.83). Mean + BNPL schedule against Mean Aug-Sep: +0.16 ± 0.36 GBP in absolute error (Wilcoxon p = 0.56, Holm 0.83). Pooled regression against Last month (Sep): -2.11 ± 1.43 GBP in absolute error (Wilcoxon p = 0.12, Holm 0.69). Pooled regression against Mean Aug-Sep: -0.38 ± 0.86 GBP in absolute error (Wilcoxon p = 0.28, Holm 0.83). Shrinkage against Last month (Sep): -1.92 ± 1.19 GBP in absolute error (Wilcoxon p = 0.13, Holm 0.69). Shrinkage against Mean Aug-Sep: -0.19 ± 0.40 GBP in absolute error (Wilcoxon p = 0.21, Holm 0.83). No model differs detectably from either baseline after Holm correction. Reading the BNPL schedule changes the Aug-Sep mean for only 24 personas, by 5.07 GBP on average (largest 16.26 GBP), small beside the month-to-month noise, so it cannot help much here. The RMSE ratios to the reference (above) are close to the values the generator implies, so most of the remaining error is October's own random variation. Within the month, the constant daily rate from the pooled regression has a lower MAE than the mean of the August and September curves at days 7, 14, 21, 28, and is close to the generator-mean reference: transaction days are drawn uniformly over the month, so the expected cumulative curve is a straight line, while averaging two realised curves keeps their timing noise.

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
