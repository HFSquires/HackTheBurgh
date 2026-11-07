# Analysis/affordability/

Output of `affordability_figures.py` (repository root, task T07b): `households.csv`, one row per mock-statement persona (id, tenure, region, household, detected monthly net income, next payday, balance, `safeToSpend`, `monthly.leftOver`, and the outcome category at each test price: `payNow`, `bnplPlainOnly` or `neither`). Written by code; never edit by hand. Regenerate with `.venv\Scripts\python -X utf8 affordability_figures.py`.

## Log

- 2026-11-07 (Claude, T07b sub-agent): first written from the 100 statements in `Analysis/mock_statements/` with the engine's default `today` (day after each statement's last transaction). `safeToSpend` does not deduct everyday spending until payday, so it is generous.
