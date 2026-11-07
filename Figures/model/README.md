# Figures/model/

Figures of `model.py` (task T30, Andrew's model), each PDF and SVG with its companion statistics `.md`; written by code, never edited by hand.

| Figure | Shows |
| --- | --- |
| `forecast_errors` | Mean absolute error of the everyday-spending forecast by months averaged k, deseasonalised (Andrew, corrected) against plain mean, rolling origin over February to October 2026 |

## Log

- 2026-11-07 (Claude, T30): first version at commit `0ef5018`. Deseasonalised mean, k = 3 (proposed default): MAE 57.84 ± 2.32 GBP; last month 57.01 ± 2.25 (no detectable difference, Holm p = 0.59); plain 3-month mean 64.84 ± 2.68 (deseasonalised lower by 6.99 ± 1.37, Holm p = 0.0001). The seasonal factors are the generator's own ONS profile.
