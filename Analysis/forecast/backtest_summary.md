# October backtest: further targets

Written by `forecast.py`; regenerate with it. Figures and the main results: `Figures/forecast/forecast_errors.md` and `forecast_scatter.md`.

## Total debits in October

Last month and mean Aug-Sep as for discretionary spending; the third row is September's committed debits (all debits less discretionary spending and BNPL) plus the BNPL instalments scheduled for October plus the pooled-regression forecast of discretionary spending.

| Forecast | n | MAE [GBP] (± SE) | RMSE [GBP] (± SE) | MAPE [%] (± SE) |
|---|---|---|---|---|
| Last month (Sep) | 100 | 19.70 ± 1.56 | 25.09 ± 1.88 | 1.29 ± 0.11 |
| Mean Aug-Sep | 100 | 17.59 ± 1.41 | 22.51 ± 1.73 | 1.16 ± 0.10 |
| Committed + BNPL schedule + pooled regression | 100 | 17.08 ± 1.49 | 22.64 ± 1.69 | 1.15 ± 0.11 |

## Card spending by merchant group, mean Aug-Sep forecast

Groups come from the merchant names in `mock_statements.MERCH`; TESCO STORES is used for both food (ONS 1) and alcohol (ONS 2), so the two are merged. Personas with no October spending in a group are excluded from that row. BNPL instalments are not card spending here, so a group carrying a BNPL plan varies with the plan's schedule.

| Group | n | Mean October spending [GBP] | MAE [GBP] (± SE) | MAPE [%] (± SE) |
|---|---|---|---|---|
| clothing | 100 | 35.20 | 2.85 ± 0.30 | 8.8 ± 1.0 |
| food and drink | 100 | 190.53 | 9.35 ± 0.69 | 4.9 ± 0.4 |
| football tickets | 24 | 13.21 | 0.00 ± 0.00 | 0.0 ± 0.0 |
| health | 100 | 22.30 | 1.15 ± 0.11 | 5.3 ± 0.4 |
| household goods | 100 | 81.58 | 4.81 ± 0.34 | 6.1 ± 0.4 |
| miscellaneous | 100 | 104.75 | 5.67 ± 0.44 | 5.5 ± 0.4 |
| recreation | 100 | 125.95 | 8.81 ± 0.78 | 6.8 ± 0.5 |
| restaurants | 100 | 79.57 | 4.79 ± 0.42 | 5.8 ± 0.4 |
| transport | 100 | 108.38 | 5.92 ± 0.45 | 5.7 ± 0.4 |

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
