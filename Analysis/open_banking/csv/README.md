# Analysis/open_banking/csv/

Written by `ob_generator.py` (task T20): each persona's main current account (MockBank), 1 November 2025 to 31 October 2026, booked transactions only, in the statement layout of `mock_statements.py` (Transaction Date, Transaction Type, Sort Code, Account Number, Transaction Description, Debit Amount, Credit Amount, Balance), so that `affordability.parse` and the existing tools read it. Other accounts (second current account, joint account, savings, cash ISA, credit cards) are only in the JSON files one level up; payments to them appear here as standing orders, direct debits (card repayments) and transfers. Transaction types beyond the original four: `CHG` (overdraft interest) and `TFR` (top-up from savings or ISA). Never edit by hand.

## Log

- 2026-11-07 (Claude, T20 sub-agent): first generation; `--check` confirms that every file parses and that salary and committed payments are detected.
