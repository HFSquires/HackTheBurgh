# Analysis/open_banking_figures/

Derived tables behind the seven figures in `Figures/open_banking/`, written by `ob_figures.py` (task T25) from the Open Banking synthetic data in `Analysis/open_banking/`. Written by code; never edit by hand. Regenerate with `.venv\Scripts\python -X utf8 ob_figures.py`; verify with `--check`. Synthetic data, so the tables describe the generator, not real customers.

| File | Contents |
|---|---|
| `where_the_money_goes.csv` | Everyday card spending by category group: total, share, transactions, mean per household-month |
| `monthly_by_category.csv`, `monthly_by_category_per_person.csv` | Mean and SE of monthly spending per category, all and by tenure; the per-person values |
| `spending_through_the_year.csv` | Mean and SE per month of everyday, one-off and total spending per person |
| `accounts_per_person.csv`, `account_holdings.csv` | Accounts per person; holdings against model probabilities and FCA Financial Lives 2024 |
| `merchants.csv` | Every merchant: total, everyday, one-off, transactions, persons |
| `payday_effect.csv` | Mean and SE of everyday spending by day relative to payday (-5 to +10) |
| `main_balance_daily.csv`, `overdraft_by_month.csv` | Daily quartiles of the main-account balance; persons overdrawn per month |

## Log

- 2026-11-07 (Claude, T25 sub-agent): first version. Everyday spending is defined in each companion file in `Figures/open_banking/`. Three lumpy purchases listed in `ground_truth.csv` never appear in the transactions (the generator foregoes card purchases while the main account is overdrawn) and are skipped.
- 2026-11-07 (Claude, T24 sub-agent): regenerated on the corrected statements (rent scaled by regional gross rent, council tax limited to the council-tax share of ONS 13.1, package holidays out of the recreation pool). Mean everyday spending 661.26 GBP a month (was 653.81); 6 persons overdrawn at a day end (was 12), 3 beyond the arranged limit (was 5).
