# October backtest: further targets

Written by `forecast.py`; regenerate with it. Figures and the main results: `Figures/forecast/forecast_errors.md` and `forecast_scatter.md`.

## Total debits in October

Last month and mean Aug-Sep as for discretionary spending; the third row is September's committed debits (all debits less discretionary spending and BNPL) plus the BNPL instalments scheduled for October plus the pooled-regression forecast of discretionary spending.

| Forecast | n | MAE [GBP] (± SE) | RMSE [GBP] (± SE) | MAPE [%] (± SE) |
|---|---|---|---|---|
| Last month (Sep) | 100 | 18.60 ± 1.48 | 23.71 ± 1.77 | 1.32 ± 0.11 |
| Mean Aug-Sep | 100 | 16.67 ± 1.34 | 21.33 ± 1.65 | 1.19 ± 0.10 |
| Committed + BNPL schedule + pooled regression | 100 | 16.12 ± 1.42 | 21.45 ± 1.61 | 1.17 ± 0.11 |

## Card spending by merchant group, mean Aug-Sep forecast

Groups come from the merchant names in `mock_statements.MERCH`; TESCO STORES is used for both food (ONS 1) and alcohol (ONS 2), so the two are merged. Personas with no October spending in a group are excluded from that row. BNPL instalments are not card spending here, so a group carrying a BNPL plan varies with the plan's schedule.

| Group | n | Mean October spending [GBP] | MAE [GBP] (± SE) | MAPE [%] (± SE) |
|---|---|---|---|---|
| clothing | 100 | 34.79 | 2.81 ± 0.29 | 8.8 ± 1.0 |
| food and drink | 100 | 180.35 | 8.86 ± 0.65 | 4.9 ± 0.4 |
| football tickets | 24 | 12.54 | 0.00 ± 0.00 | 0.0 ± 0.0 |
| health | 100 | 20.90 | 1.08 ± 0.11 | 5.3 ± 0.4 |
| household goods | 100 | 80.69 | 4.75 ± 0.34 | 6.1 ± 0.4 |
| miscellaneous | 100 | 98.61 | 5.33 ± 0.41 | 5.5 ± 0.4 |
| recreation | 100 | 119.55 | 8.36 ± 0.74 | 6.8 ± 0.5 |
| restaurants | 100 | 73.69 | 4.44 ± 0.39 | 5.8 ± 0.4 |
| transport | 100 | 98.86 | 5.40 ± 0.41 | 5.7 ± 0.4 |

## BNPL schedule

Personas with a BNPL plan: 34. The instalments scheduled for October from the rows up to 30 September equal the instalments actually charged in October for 100 of 100 personas.

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
