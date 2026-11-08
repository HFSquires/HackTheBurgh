# Analysis/forecast/

Output of `forecast.py` (repository root, task T12): an October 2026 backtest of spending forecasts fitted on August and September of the 100 mock statements. `predictions_october.csv` has one row per persona (actual October discretionary card spending, each model's prediction and error, and total debits); `curves_october.csv` has the cumulative discretionary spending by day of October with the two curve forecasts and the generator-mean reference; `backtest_summary.md` gives total debits, merchant groups and the BNPL schedule check. Written by code; never edit by hand. Regenerate with `.venv\Scripts\python -X utf8 forecast.py`.

## Log

- 2026-11-07 (Claude, T12 sub-agent): first run (seed 20261107, 10 person-level folds). No model beat the naive Aug-Sep mean detectably; the statements' noise is independent each month, so this was expected (see `Figures/forecast/forecast_errors.md`). The generator-mean reference is computed with `mock_statements.spend_model` per persona; the statements were not regenerated (coordinator's instruction).
- 2026-11-07 (Claude, T15 sub-agent): rerun on the regenerated statements. Primary comparison, pooled regression minus Aug-Sep mean: -0.32 ± 0.90 GBP in absolute error (paired t p = 0.72); no model differs detectably from either baseline after Holm correction.
- 2026-11-07 (Claude, T15b sub-agent): regenerated on the wage-uprated statements; `forecast.py` takes the income decile from the table's gross salary divided by the AWE factor (April 2025 pay), as in `mock_statements.build`.
- 2026-11-07 (Claude, T24 sub-agent): regenerated on the corrected statements (rent scaled by regional gross rent, council tax limited to the council-tax share of ONS 13.1, package holidays out of the recreation pool). Pooled-regression October MAE 14.61 ± 1.28 GBP (was 17.08 ± 1.49).
