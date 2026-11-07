# Analysis/mock_statements/

Output of `mock_statements.py` (repository root): 100 mock Lloyds-layout statement CSVs (`persona<NNN>_<uuid8>.csv`) (3 months to 31 October 2026) and `personas.md` (persona details, salary source row, modelled monthly spend). Written by code; never edit by hand. Regenerate with `.venv\Scripts\python mock_statements.py`. Merchant names are synthetic flavour. Spending is scaled by gross-income decile (T05b); end balances range from -862.41 to 15,910.18 GBP (median 5,214.97; 3 overdrawn), still on the high side because several ONS spending items are excluded (see `USER_GUIDE.md`).

## Log

- 2026-11-07 (Claude, T05): first generation, seed 20261107.
- 2026-11-07 (Claude, T05c sub-agent): regenerated with `--n 100` (default): 100 personas from all 12 UK regions, spending from each persona's own region (Family Spending workbook 3). The five T05 files were removed as generated outputs. End balances range from -2,615.43 to 16,586.35 GBP (6 overdrawn). Income tax and spending-to-income scaling unchanged (T05b pending).
- 2026-11-07 (Claude, T05b sub-agent): regenerated. Spending scaled by gross-income decile (ONS Family Spending workbook 2, Table A4); tenure sampled by age band from English Housing Survey 2024-25 table FA1201 (mortgagors excluded: 22 own outright, 29 social rented, 49 private rented); Scottish personas use 2025/26 Scottish income tax bands. End balances: 3 overdrawn, min -862.41, median 5,214.97, max 15,910.18 GBP.
