# Figures/affordability/

Pitch figures from the affordability engine over the 100 mock statements, written by `affordability_figures.py` (task T07b), each as PDF and SVG with a companion statistics `.md`: `affordability_by_price` (households that can pay now, only with plain pay-in-3, or neither, at eight prices) and `safe_to_spend_vs_income` (`safeToSpend` and `monthly.leftOver` against monthly net income, by tenure). Written by code; never edit or move by hand.

## Log

- 2026-11-07 (Claude, T07b sub-agent): first written. Everyday spending until payday is not deducted from `safeToSpend`, so the "can pay now" counts are generous; all 6 households with negative `safeToSpend`, and 11 of the 12 with negative `monthly.leftOver`, are private renters. The Spearman p-values use a normal approximation (no SciPy) and are reported only as far below 0.001.
