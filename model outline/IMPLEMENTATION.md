# Implementing Andrew's model: instructions

Status: instructions only; nothing here is built yet. Read `HackTheBurgh.md` (Andrew's model) and `MODEL_OUTLINE.md` (the mapping onto our code, the evidence and the open decisions) first. These instructions are for whoever implements the model, a teammate or an agent, and assume the repository as it stands after task T29 (7 November 2026): the old Bayesian model and engine are in `archive/`, and the back end is to stay simple.

## 1. Scope

| In scope | Out of scope |
| --- | --- |
| One new module, `model.py`, implementing Andrew's model on Open Banking-style data | Joining the back end to Auro's extension (the team does this itself; branch `t26-extension-api` shows how the old engine answered the extension's contract) |
| A backtest of the model on the synthetic Open Banking data, scored against the generator's ground truth | Real bank connections, accounts, authentication |
| A small local JSON endpoint so the team can call the model | Price comparison and catalogue (the extension already searches for cheaper options) |
| `--check` self-tests; figures with companion statistics files | Any Bayesian or machine-learnt forecast beyond Andrew's averaging |

## 2. Decisions to confirm before step 3

`MODEL_OUTLINE.md` section 6 lists ten open decisions. The table gives a proposed default for each so that work can start; every default is a parameter in code, so a later change is a one-line edit. The team should confirm or change them; record the outcome in `DECISIONS.md`.

| # | Decision | Proposed default | Why |
| --- | --- | --- | --- |
| 1 | Forecast form | Deseasonalised mean (outline 3.1): $\hat r_n = f_{m(n)} \cdot \frac{1}{k}\sum_{j=1}^{k} r_{n-j}/f_{m(n-j)}$ | Andrew's formula as written is too small by 12 and carries Christmas into January |
| 2 | Seasonal weights | ONS retail-sales profile, the same for everyone: $f_m$ from `market_data.seasonality()` (mean over 2021 to 2025 of each month, each year scaled to mean 100, divided by 100) | Group-specific weights carry no information in the synthetic data (outline 3.3) |
| 3 | $k$ | 3, with the backtest reporting $k = 1$ to 6 | Choose from the learning curve, not by assumption |
| 4 | Within-month remainder | $\max(0,\ \hat r_n - \text{spent so far this month})$; the linear $\frac{D-d}{D}\hat r_n$ also reported | Uses what has already been spent; spending is front-loaded after payday |
| 5 | Horizon | Calendar month (Andrew) | Simplest; pay-cycle horizon is a later refinement |
| 6 | Net worth | Sum of booked balances of every account in the customer picture (current, savings, cash ISA; joint current at half; credit cards negative when owed) minus outstanding BNPL scheduled payments | All in the mock bank's picture; joint share is a stated simplification |
| 7 | Inflation | 12-month change of CPI all items (`data/ons_mm23_cpi_index_D7BT.csv`) at the latest month available | Already in `data/` and read by `market_data.py` |
| 8 | Verdict and thresholds | `good` if forecast net worth after the purchase exceeds the month's goal by at least 10% of monthly net salary; `caution` if it meets the goal by less; `reconsider` if it misses; `neutral` if no salary is detected | Matches the extension's four verdicts without changing Auro's contract (outline 5.1) |
| 9 | "Affordable in N days" (Andrew's case 3) | $N = \lceil \text{shortfall} / \text{daily surplus} \rceil$, where shortfall is how far the purchase takes net worth below the goal and daily surplus is the forecast month-end net worth above the goal (without the purchase) divided by the days in the month; no interest; "not within 90 days" if the surplus is zero or negative | Simple and explainable; interest is a later refinement (`statements.bank_rate()` is available) |
| 10 | Testing | Rolling origin in time (fit on months before the target month only) for all 100 personas; across-person splits only where something is fitted across persons (nothing is, with these defaults) | No look-ahead; nothing is trained on the test persons |

## 3. Data and what to reuse

Inputs come from the mock bank's customer picture, not from files read directly, so the same code later reads a real aggregator: start the mock bank with `.venv\Scripts\python -X utf8 mock_bank.py --serve --source v2` and read a persona with `mock_bank.fetch_customer("http://127.0.0.1:8766", persona="persona072")`, or validate a request's `bank` object with `mock_bank.from_request(...)`. The picture's accounts carry `type` (`current`, `jointCurrent`, `savings`, `cashIsa`, `creditCard`), `balances`, `creditLines`, `standingOrders` (with `toOwnAccountId` for transfers to the customer's own accounts), `scheduledPayments` (BNPL), `pending`, and `transactions` in `statements.parse` format with `transactionDetails` (merchant, `mcc`) aligned item by item. The data run from 1 November 2025 to 31 October 2026, with pending card payments on 1 and 2 November 2026; regenerate with `ob_generator.py` if the gitignored JSON is missing (`USER_GUIDE.md`).

| Model step (Andrew) | Reuse | New code |
| --- | --- | --- |
| Salary $s_n$ | `statements.detect_income` on the main account (`mock_bank.main_account(picture)`) | none |
| Other income $i_n$ | none | Credits on any account that are neither the salary nor transfers between the customer's own accounts (interest, refunds, benefits); list them by description |
| Regular payments $\mathrm{reg}_n$ | `statements.detect_committed` and `statements.detect_bnpl` per current account | Drop standing orders whose `toOwnAccountId` is set (they are saving, not spending); add BNPL `scheduledPayments`; count a joint account's committed payments at half |
| Everyday spending $r_n$ and categories | The T25 definition (`ob_figures.EVERYDAY` text and `ob_figures.GROUPS` merchant-code groups): booked card purchases (codes `DEB`, `PUR`) on all accounts, excluding own-account transfers and one-offs | A function returning calendar-month totals per person, overall and by group |
| Seasonal factors $f_m$ | `market_data.seasonality()` | Average the scaled years per month and divide by 100 (as `ob_generator.season()` does; do not import the generator) |
| Inflation | CPI series read by `market_data.py` | 12-month change of D7BT |
| Net worth | Balances in the picture | Sum per default 6 |

## 4. Steps

Each step ends with its own `--check` assertions passing and a commit (code is committed only after it has run; see `CLAUDE.md`). Work on a task branch in a worktree, claim the task in `TASKS.md` first, and keep tracking-file edits on `main`.

| Step | Build | Done when |
| --- | --- | --- |
| 1 | `model.py` skeleton: load a persona's picture through the mock bank; everyday spending by calendar month and group | Monthly totals equal `ground_truth_monthly.csv` column `booked` summed over categories for every persona and month, to the penny, or every difference is explained (for example, foregone purchases) |
| 2 | Salary, other income, regular payments (section 3 table) | Detected salary equals `ground_truth.csv` `net_monthly` for every persona; every mandate in the JSON appears among regular payments; own-account standing orders are excluded |
| 3 | Forecast $\hat r_n$ (defaults 1 to 3) and remainder (default 4) | A hand-worked example in `--check` (three months of known totals and factors) gives the expected value; corrupting the target month leaves the forecast unchanged (no look-ahead) |
| 4 | Backtest: for each persona and each target month 4 to 12, forecast from earlier months only; compare with last month and the plain mean of $k$ months | `Analysis/model/backtest.csv` and `Figures/model/forecast_errors.{pdf,svg,md}`: MAE ± SE across persons by model and by $k$, paired differences with a stated test and Holm correction; the companion `.md` states that the seasonal factors are the generator's own profile, so the seasonal model's advantage is not evidence of learning (outline 3.2) |
| 5 | Net worth, goal and the decision (defaults 6 to 9), returning a JSON-ready dict: verdict, title, one-line message, the numbers behind it (forecast month-end net worth with and without the purchase, goal, headroom, $N$ days where relevant) and the assumptions used | `--check`: the verdict never improves as the price rises; a persona whose committed payments exceed pay (`ground_truth.csv` `unarranged_overdraft_days` > 0) gets `reconsider` at a moderate price; a missing salary gives `neutral`; the output is strict JSON (no NaN) |
| 6 | Local endpoint: `python model.py --serve [--port 8765]` with `POST /decide` taking `{"bank": {...}, "price": ..., "today": "YYYY-MM-DD", "goalRate": ...}` (the `bank` object exactly as `mock_bank.from_request` accepts it) and `GET /health` | Requests need `Content-Type: application/json`; bad input returns 400 with a message and never echoes bank text; `--check` starts the mock bank and the endpoint and round-trips three personas (comfortable, tight, over budget) |
| 7 | Records | `USER_GUIDE.md` section for `model.py` (commands, inputs, outputs, defaults, limitations); `DECISIONS.md` rows for the confirmed defaults; `TASKS.md` and `README.md` log; this folder's `README.md` log |

## 5. Rules that apply

Follow `CLAUDE.md`: the ponytail discipline (reuse `statements.py`, `mock_bank.py`, `market_data.py`; standard library plus what is already in `requirements.txt`; one file; `ponytail:` comments on stated simplifications such as the joint-account half and the interest-free $N$), TeXFormat figures with companion statistics files written by the same script, outputs only in `Analysis/model/` and `Figures/model/`, British English, and no claims beyond what the synthetic data support. The extension describes options and does not give financial advice; keep the verdict's wording factual.

## 6. Known limits to state in the results

All testing is on synthetic data whose spending follows the ONS seasonal profile, a per-person AR(1) process and fixed category multipliers; good backtest numbers show that the model recovers the generator's process, not that it predicts real customers. Seventeen personas have purchases foregone while overdrawn, so their recorded spending is constrained, not habitual. Pensions and investments outside Open Banking are not in the net worth.

## Log

- 2026-11-07 (Claude): written on Harrison's request after T29; defaults proposed, not yet confirmed by the team.
