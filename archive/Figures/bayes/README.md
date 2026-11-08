# Figures/bayes/

Plots written by `bayes.py` (task T17), each as PDF and SVG with a companion statistics `.md` written by the same run: `calibration` (nominal against empirical coverage of the October predictive intervals, monthly-budget and independent-days models) and `cold_start` (posterior of the monthly budget and predictive interval of the October total against days observed, for two example personas). Never moved or edited by hand; regenerate with `.venv\Scripts\python -X utf8 bayes.py`.

## Log

- 2026-11-07 (Claude, T17 sub-agent): created. The example personas are chosen by rule (prior closest to and furthest from the posterior after 30 September): persona073 and persona061.
- 2026-11-07 (Claude, T15 sub-agent): rerun on the regenerated statements; companion files now name the statement and code commits. Example personas unchanged (persona073, persona061).
- 2026-11-07 (Claude, T23 sub-agent): regenerated (T23) with current commit references; plotted data unchanged.
- 2026-11-07 (Claude, T24 sub-agent): regenerated on the corrected statements (rent scaled by regional gross rent, council tax limited to the council-tax share of ONS 13.1, package holidays out of the recreation pool). Posterior predictive mean MAE 14.64 ± 1.28 GBP (was 17.02 ± 1.43).
