# Analysis/market

Derived market tables, written by `market_data.py` from the ONS series in `data/`. `cpi_uprating_factors.csv`: for the all-items CPI and the 12 COICOP divisions, the mean index over April 2024 to March 2025 (the Family Spending FYE 2025 reference period), the latest month's index and their ratio (`factor`), for uprating the mock statements to current prices in a later task.

## Log

- 2026-11-07 (Claude, T14 sub-agent): created; latest CPI month 2026-09 (ONS release 21 October 2026).
- 2026-11-07 (Claude, T15 sub-agent): `cpi_uprating_factors.csv` is now used by `mock_statements.py` to uprate the mock statements (category c takes division c; rent, energy and water, and council tax take division 04). File unchanged by the rerun.
