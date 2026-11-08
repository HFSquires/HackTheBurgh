# Analysis/open_banking/

Output of `ob_generator.py` (task T20): Open Banking-native synthetic data for the same 100 personas as `Analysis/mock_statements/`, 1 November 2025 to 31 October 2026, with pending card payments on 1 and 2 November 2026 (snapshot 2 November 2026, 08:00 London time). Written by code; never edit by hand. Regenerate with `.venv\Scripts\python -X utf8 ob_generator.py` (a few seconds); check with `--check`. Synthetic data, not real bank records; providers (MockBank, MockDigital, MockCards) are fictional.

| File | Contents |
|---|---|
| `persona<NNN>_<uuid8>.json` | One per persona: `{"Providers": [{"Provider", "Data": {Account, Balance, Product, DirectDebit, StandingOrder, ScheduledPayment, Transaction}}], "Meta"}`, field names as in Open Banking Read/Write API v3.1. About 47 MB in all, so gitignored except five samples (persona001, 029, 072, 082, 100) |
| `csv/` | The main current account of each persona in the statement CSV layout of `mock_statements.py` |
| `ground_truth.csv` | One row per persona: holdings and the holding probabilities used, habit parameters (category multipliers, AR(1) coefficient, payday share, trend), synthetic account terms, annual and one-off items, foregone, declined and returned payments, overdraft use, end balances |
| `ground_truth_monthly.csv` | One row per persona, month and spending category: AR factor, trend factor, expected spending (ONS x multiplier x season x trend), realised budget, booked spending (all accounts) and spending not made (foregone or declined) |
| `summary.md` | Distribution of accounts held, comparison with FCA Financial Lives 2024 rates, balances and behaviour, seasonal factors |

## Log

- 2026-11-07 (Claude, T20 sub-agent): first generation (seed 20261107). On Harrison's instruction (via the coordinator), the accounts held vary by person from the persona's age, household type and household income, with probabilities from the FCA Financial Lives 2024 survey where available (savings account, cash ISA, credit card, a second current-account provider) and stated synthetic rules otherwise (joint account for half of couples, a second card). 3, 15, 29, 33, 18, 1 and 1 persons hold 1 to 7 accounts. Two behavioural assumptions were added after the first run showed 11 persons spiralling into unarranged overdraft (to -9,299 GBP): purchases are foregone while the main current account is overdrawn, and an overdrawn main account is topped up from savings, then the ISA. Five persons are still in unarranged overdraft on some days (flagged in `ground_truth.csv`): their committed payments exceed their pay, an artefact of ONS average spending against a single low salary with no benefits modelled. Main current-account end balances are high (median 11,274 GBP, maximum 51,241 GBP) because several ONS spending items are not modelled (as in `Analysis/mock_statements/`).

- 2026-11-08 (Codex, T34): Included the five current sample JSONs and scoring inputs from main for the new model. Other existing CSVs/summary are historical; regenerate the full cohort before using them for analysis.
