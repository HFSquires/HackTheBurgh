# October discretionary spending: predicted versus actual

Plot: `forecast_scatter.pdf` / `.svg`. Written by `forecast.py`; regenerate with it.

## Source and transformations

Source: the 100 statements in `Analysis/mock_statements/` (persona CSVs and `personas.md`), via `forecast.py`. Target: October 2026 discretionary card spending per persona [GBP], i.e. card (DEB) payments that are neither BNPL instalments nor committed payments, with committed payments detected by `affordability.detect_committed` on the rows up to 30 September (so the fixed football-ticket card payments of 24 personas, which need three months to be detected, count as discretionary in every month). Models are fitted on August and September only; October is used only to score. Per-persona data: `Analysis/forecast/predictions_october.csv`. Statements last changed in commit `e01f34f`; `forecast.py` at commit `22804b4`; `affordability.py` at commit `2c5e080` (or later, if uncommitted changes were run).

Panel (a): pooled-regression prediction against the actual value, one point per persona (n = 100), with the line y = x; triangles mark the personas with a BNPL plan. Panel (b): prediction error (prediction minus actual) against the actual value for the mean Aug-Sep baseline and the pooled regression. Units GBP. No error bars.

Axis range of (a): 261.77 to 1378.52 GBP. Actual October spending: min 290.85, median 740.69, max 1312.88 GBP.

## Statistics by series

Uncertainties are ± one standard error across persons.

| Model | Personas | n | MAE [GBP] (± SE) | Mean error [GBP] (± SE) |
|---|---|---|---|---|
| Mean Aug-Sep | no BNPL plan | 66 | 18.75 ± 1.88 | 1.29 ± 2.98 |
| Mean Aug-Sep | BNPL plan | 34 | 14.81 ± 2.13 | 1.37 ± 3.34 |
| Pooled regression | no BNPL plan | 66 | 18.24 ± 2.02 | -2.17 ± 3.02 |
| Pooled regression | BNPL plan | 34 | 14.86 ± 1.97 | -0.08 ± 3.25 |

All persons: pooled regression MAE 17.09 ± 1.49 GBP, mean Aug-Sep MAE 17.41 ± 1.44 GBP. Paired comparisons, fits and tests: `forecast_errors.md`.

Random seed 20261107 (assignment of persons to 10 cross-validation folds).

## Interpretation

The points in (a) lie close to y = x: the regression's mean absolute percentage error is 2.2 %. In (b), the errors of the two forecasts are strongly correlated across persons (Pearson r = 0.911), as expected when both are dominated by October's own random variation, which no forecast made on 30 September can anticipate. The table above gives the errors separately for personas with and without a BNPL plan.

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
