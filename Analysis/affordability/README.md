# Analysis/affordability/

Output of `affordability_figures.py` (repository root, task T07b): `households.csv`, one row per mock-statement persona (id, tenure, region, household, detected monthly net income, next payday, balance, `safeToSpend`, `monthly.leftOver`, and the outcome category at each test price: `payNow`, `bnplPlainOnly` or `neither`). Written by code; never edit by hand. Regenerate with `.venv\Scripts\python -X utf8 affordability_figures.py`.

## Log

- 2026-11-07 (Claude, T07b sub-agent): first written from the 100 statements in `Analysis/mock_statements/` with the engine's default `today` (day after each statement's last transaction). `safeToSpend` does not deduct everyday spending until payday, so it is generous.
- 2026-11-07 (Claude, T15 sub-agent): regenerated from the CPI-uprated, 2026/27-tax statements. `safeToSpend` now deducts the Bayesian predicted everyday spending until payday (`bayes.py`); new columns `safeToSpendBeforeEverydaySpending` and `predictedSpendingMean`. `bnplPlain` also needs `monthly.leftOver` to cover one later instalment. Median `safeToSpend` 3,468.49 GBP (was 4,440.77); 16 households below 0 (was 6).
- 2026-11-07 (Claude, T15b sub-agent): regenerated on statements with pay uprated by AWE (factor 1.0490). Households unable to pay GBP 50 now 14 of 100 (T15: 17).
