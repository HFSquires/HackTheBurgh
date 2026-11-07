# Forecast error of everyday spending by months averaged

Files: `forecast_errors.pdf`, `forecast_errors.svg` (this file: `forecast_errors.md`), written by `model.py` (task T30).

**The data are synthetic** (`ob_generator.py`), so these errors describe how well the model recovers the generator's process, not real customers.

## Source data

The 100 customer pictures read through the v2 mock bank (`mock_bank.fetch_customer`) from `Analysis/open_banking/persona*.json` (written by `ob_generator.py`, commit `0aff08f`), scored against `Analysis/open_banking/ground_truth_monthly.csv` (`booked`, summed over categories). Code: `model.py` (commit `0ef5018`). Every forecast and actual value: [`Analysis/model/backtest.csv`](../../Analysis/model/backtest.csv).

## Filters, transformations and units

Everyday spending per person and calendar month [GBP]: card purchases (rows with a merchant category code) on every account, less regular card payments detected at the forecast origin (same description and amount, the same number of times, in at least three months) and one-offs (merchant category [4722] or a single purchase of GBP 250 or more). Rolling origin: each target month from February to October 2026 (9 months) is forecast from the full months before it only; with fewer than k months available, all are used. Deseasonalised mean: f_target × mean(r_j / f_j) over the last k months, f the ONS retail-sales seasonal factor (`market_data.seasonality`, mean over 2021 to 2025, mean 1). Plain mean: mean of the last k months (k = 1 is last month). Actual: the generator's booked everyday spending (`ground_truth_monthly.csv`) less the BNPL instalments booked that month, which the model treats as regular payments.

## Plotted data

Per person, the absolute error is averaged over the 9 target months (one value per person); the plot shows the mean of these across persons, with error bars ± SE = s / sqrt(n), ddof = 1. Points for the two models are offset by ±0.04 in k for legibility.

| k | Deseasonalised mean (Andrew, corrected): MAE ± SE [GBP] | Plain mean (k = 1: last month): MAE ± SE [GBP] | n |
|---|---|---|---|
| 1 | 55.98 ± 2.19 | 57.01 ± 2.25 | 100 |
| 2 | 55.93 ± 2.24 | 60.86 ± 2.55 | 100 |
| 3 | 57.84 ± 2.32 | 64.84 ± 2.68 | 100 |
| 4 | 57.74 ± 2.43 | 65.97 ± 2.87 | 100 |
| 5 | 58.05 ± 2.49 | 66.89 ± 2.97 | 100 |
| 6 | 58.67 ± 2.57 | 67.58 ± 3.13 | 100 |

## Sample size

n = 100 persons for every point; 9 target months each (900 person-months).

## Statistics and tests

| Comparison (A minus B) | Mean paired difference ± SE [GBP] | n | p (sign-flip) | p (Holm) |
|---|---|---|---|---|
| seasonal_k3 minus plain_k1 | +0.83 ± 1.53 | 100 | 0.59 | 0.59 |
| seasonal_k3 minus plain_k3 | -6.99 ± 1.37 | 100 | 5e-05 | 0.0001 |

Test: two-sided paired sign-flip permutation test on the per-person differences in MAE (20000 random sign assignments, seed 20261107); p = (1 + count) / (20000 + 1). Holm correction over the two comparisons.

## Validation of steps 1 and 2 (same run)

Everyday totals for the 12 months to 31 October 2026 against the generator's booked spending: 970 of 1200 person-months equal to the penny; 230 differ only by lumpy purchases below GBP 250 (everyday to the model, one-off to the generator) and BNPL instalments (regular payments to the model, everyday to the generator); 0 unexplained. Salary equal to `ground_truth.csv` `net_monthly`: 100 of 100.

## Seed and parameters

Permutation seed 20261107; K = 3 is the proposed default; ONE_OFF_GBP = 250. No other random numbers.

## Interpretation

The lowest mean absolute error among the models plotted is the deseasonalised mean with k = 2 (55.93 ± 2.24 GBP). Across k = 1 to 6 the deseasonalised mean ranges from 55.93 to 58.67 GBP and the plain mean from 57.01 to 67.58 GBP; differences between values of k were not tested. The deseasonalised mean with k = 3 differs from last month by +0.83 ± 1.53 GBP (Holm p = 0.59) and from the plain 3-month mean by -6.99 ± 1.37 GBP (Holm p = 0.0001). The seasonal factors are the same ONS profile the generator used to make the data, so the seasonal model's advantage shows what knowing the season is worth, not that the model learnt it; on real data the factors would come from the same public ONS series, independent of the customer.
