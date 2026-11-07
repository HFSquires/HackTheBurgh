# Analysis/mock_statements/

Output of `mock_statements.py` (repository root): 100 mock Lloyds-layout statement CSVs (`persona<NNN>_<uuid8>.csv`) (3 months to 31 October 2026) and `personas.md` (persona details, salary source row, modelled monthly spend). Written by code; never edit by hand. Regenerate with `.venv\Scripts\python mock_statements.py`. Merchant names are synthetic flavour. Balances are not realistic for every persona (see the repository README log): 6 of 100 end overdrawn.

## Log

- 2026-11-07 (Claude, T05): first generation, seed 20261107.
- 2026-11-07 (Claude, T05c sub-agent): regenerated with `--n 100` (default): 100 personas from all 12 UK regions, spending from each persona's own region (Family Spending workbook 3). The five T05 files were removed as generated outputs. End balances range from -2,615.43 to 16,586.35 GBP (6 overdrawn). Income tax and spending-to-income scaling unchanged (T05b pending).
