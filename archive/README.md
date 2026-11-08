# archive/

The old spending model and affordability engine, retired on 7 November 2026 (task T29) when Harrison chose Andrew's model (`model outline/`) and a simpler back end: "scrap old model implementations and clean / archive old files related to this. we intend to simplify the back-end." Kept for reference; not maintained, and not meant to run from here (the scripts import each other and expect to sit at the repository root, and need `scipy`, now removed from `requirements.txt`). Git history before T29 has them at the root and runnable.

| Path | What it was | Task |
| --- | --- | --- |
| `affordability.py` | Full old engine and HTTP API: safe to spend before payday, pay options (pay now, BNPL with pot, plain BNPL, 0% card, card cleared in full), card and pot interest, Section 75 notes, price catalogue and sale notes, `/assess`, `/personas`, `/health` | T07, T15, T16, T18, T19, T21, T23 |
| `bayes.py` | Bayesian (Normal-Inverse-Gamma) model of daily everyday spending and the probability of going below zero before payday | T17 |
| `forecast.py` | October spending-forecast backtest on the generation-1 statements | T12 |
| `affordability_figures.py` | Affordability-by-price, safe-to-spend and savings-comparison figures | T15 |
| `Analysis/affordability`, `Analysis/bayes`, `Analysis/forecast`, `Analysis/value` | Their derived tables | |
| `Figures/affordability`, `Figures/bayes`, `Figures/forecast`, `Figures/value` | Their figures with companion statistics files | |
| `Figures/open_banking/` (`where_the_money_goes`, `monthly_spending_by_category`, `top_merchants`) and `Analysis/open_banking_figures/` (`where_the_money_goes.csv`, `monthly_by_category*.csv`, `merchants.csv`) | Synthetic-data figures that are not inputs to the model: category shares (with the pie chart Harrison asked for), monthly spending by category and tenure, top merchants. `ob_figures.py` at commit `dd145f1` draws them | T25, archived in T31 |

The parser and the salary, payday, BNPL and committed-payment detectors were not archived: they are `statements.py` at the root, copied verbatim, because `mock_bank.py` and `ob_generator.py` use them and Andrew's model needs them. Work on unmerged branches was not copied here: `t22-learning-test` (learning test of the old models on the Open Banking data), `t22b-engine-accounts` (unfinished all-accounts engine) and `t26-extension-api` (the old engine answering the extension's `/analyze` and `/action`, tested, parked as reference for the front-end merge).

## Log

- 2026-11-07 (Claude, T29): created; files moved with `git mv`, unchanged.
- 2026-11-07 (Claude, T31): added three synthetic-data figures and their tables, on Harrison's instruction to keep only current figures; `ob_figures.py` no longer draws them (it did at `dd145f1`).
