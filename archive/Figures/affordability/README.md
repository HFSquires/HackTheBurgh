# Figures/affordability/

Pitch figures from the affordability engine over the 100 mock statements, written by `affordability_figures.py` (task T07b), each as PDF and SVG with a companion statistics `.md`: `affordability_by_price` (households that can pay now, only with plain pay-in-3, or neither, at eight prices) and `safe_to_spend_vs_income` (`safeToSpend` and `monthly.leftOver` against monthly net income, by tenure). Written by code; never edit or move by hand.

## Log

- 2026-11-07 (Claude, T07b sub-agent): first written. Everyday spending until payday is not deducted from `safeToSpend`, so the "can pay now" counts are generous; all 6 households with negative `safeToSpend`, and 11 of the 12 with negative `monthly.leftOver`, are private renters. The Spearman p-values use a normal approximation (no SciPy) and are reported only as far below 0.001.
- 2026-11-07 (Claude, T15 sub-agent): regenerated on the new definitions. `payNow` counts fall from 93 to 83 at 50 GBP and from 80 to 71 at 1,500 GBP; no household is affordable only with plain pay-in-3 at any test price, because every household that could cover the first instalment but not the full price has a negative `monthly.leftOver` (under the old `afterCommitted` test there would be 1, 2 and 6 at 50, 300 and 1,200 GBP).
- 2026-11-07 (Claude, T15b sub-agent): figures regenerated on the wage-uprated statements.
- 2026-11-07 (Claude, T23 sub-agent): regenerated (T23): companion files name current commits and quote the current engine definitions; counts and figures unchanged.
- 2026-11-07 (Claude, T24 sub-agent): regenerated on the corrected statements (rent scaled by regional gross rent, council tax limited to the council-tax share of ONS 13.1, package holidays out of the recreation pool). `payNow` at 50 / 300 / 1,500 GBP: 91 / 90 / 79 (was 86 / 83 / 74); households with negative `safeToSpend` 7 (was 14), all private renters.
