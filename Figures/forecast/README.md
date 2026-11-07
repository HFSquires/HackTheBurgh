# Figures/forecast/

Figures from `forecast.py` (task T12), each as PDF and SVG with a companion statistics `.md` written by the same script: `forecast_scatter` (predicted versus actual October discretionary spending, pooled regression; errors of the regression and of the Aug-Sep mean) and `forecast_errors` (MAE by model; MAE of the cumulative within-month curve by day of October). Never edit by hand; regenerate with `.venv\Scripts\python -X utf8 forecast.py`.

## Log

- 2026-11-07 (Claude, T12 sub-agent): first version; rendered with real LaTeX (Computer Modern embedded) through the shared TeXFormat style.
- 2026-11-07 (Claude, T15 sub-agent): rerun on the regenerated statements; companion files now name the statement and code commits. `forecast_errors` panel (b) legend moved to the lower centre, off the curves.
- 2026-11-07 (Claude, T23 sub-agent): regenerated (T23): BNPL-schedule summary and Wilcoxon non-zero pairs ignore floating-point noise; Mean + BNPL schedule against Mean Aug-Sep now 17 non-zero pairs, W 63, p 0.52 (was 18, 70, 0.50); the schedule changes the Aug-Sep mean for 17 personas by 7.32 GBP on average (was 18, 6.92). Commit references updated; plotted data unchanged.
