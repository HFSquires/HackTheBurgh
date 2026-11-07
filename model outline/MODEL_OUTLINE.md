# Model outline: spending forecast and checkout decision

Status: design only, not implemented (Harrison, 7 November 2026: "dont implement yet"). This document builds on Andrew's outline, `HackTheBurgh.md` in this folder, which is kept unchanged. It maps each part of that outline onto the data and code that already exist, says what the 100 personas can and cannot train, records where the outline conflicts with the extension's contract, and lists the decisions the team must take before anything is built. Statements about the existing code and results are taken from the files named; everything marked "proposal" is Claude's and needs the team's agreement.

## 1. Notation

| Symbol | Meaning | Unit |
| --- | --- | --- |
| $n$ | calendar month index; $m(n) \in \{1,\dots,12\}$ its month of the year | |
| $s_n$, $i_n$ | salary and other income received in month $n$ | GBP |
| $\mathrm{reg}_n$ | regular (committed) payments in month $n$: rent or mortgage, bills, subscriptions, BNPL instalments | GBP |
| $r_n$ | "random" (everyday) spending in month $n$ | GBP |
| $\hat r_n$ | forecast of $r_n$ | GBP |
| $w_{m}$ | Andrew's seasonal weight of month of the year $m$: share of a year's spending that falls in it, $\sum_{m=1}^{12} w_m = 1$ | dimensionless |
| $f_m = 12\,w_m$ | the same weight rescaled to mean 1 (seasonal factor) | dimensionless |
| $k$ | number of past months averaged | months |
| $d$, $D$ | days elapsed in the current month, length of the month | days |
| $g$ | user's chosen growth rate of net worth (minimum: inflation) | per year |

## 2. Andrew's components mapped onto what exists

| Component (Andrew) | Existing code or data | State |
| --- | --- | --- |
| Infer salary $s_n$ | `affordability.detect_income` (largest regular credit; payday) | Built, rule-based |
| Infer other income $i_n$ | Not separated; savings interest exists in the Open Banking data (`ob_generator.py`, savings and ISA accounts) | Gap |
| Infer regular payments $\mathrm{reg}_n$ | `affordability.detect_committed` and `detect_bnpl`; with all accounts, the uncommitted T22 engine work (`accounts_view`, branch `t22b-engine-accounts`) adds joint-account shares and own-account transfers | Built for the main account; all-accounts version in progress |
| Categories of random spending | Seven merchant-category groups plus Other (T25 definition, `ob_figures.EVERYDAY`) | Built |
| Average of last $k$ months | `ob_learning.py` "mean of history" and "last month" baselines (branch `t22-learning-test`) | Built as baselines, not as the product's forecast |
| Seasonal weights $w_m$ | ONS retail-sales profile `ob_generator.season()` (from `data/ons_drsi_retail_sales_value_nsa_J5AH.csv`) | Exists as data; not used by the engine |
| Within-month remainder | `bayes.py`: posterior predictive of spending until payday, updated day by day, and the probability of going below zero | Built; pay-cycle, not calendar-month, horizon |
| Net-worth trend and goal | Balances of every account are in the customer picture (`mock_bank.fetch_customer`); CPI series in `data/ons_mm23_cpi_index_*.csv` | Data available; no model |
| Decision colours | Extension contract, `extension/README.md`: `verdict` good / caution / reconsider / neutral; separate `alternatives` and price-outlook cards | Built (Auro) |

## 3. Forecast of everyday spending

### 3.1 Correction to the weighting formula (proposal)

As written, Andrew's forecast is $\hat r_n = w_{m(n)} \cdot \frac{1}{k}\sum_{j=1}^{k} r_{n-j}$. Two problems: $w_m$ sums to 1 over the year, so this is too small by a factor of 12; and the average itself is seasonal (an average over November and December is inflated by Christmas). The consistent form deseasonalises each past month before averaging and reseasonalises for the target month:

$$\hat r_n = f_{m(n)} \cdot \frac{1}{k}\sum_{j=1}^{k} \frac{r_{n-j}}{f_{m(n-j)}}, \qquad f_m = 12\,w_m .$$

This is the "mean × ONS season" model already scored in `ob_learning.py`.

### 3.2 Evidence from the T22 learning test

From `Figures/learning/learning_curve.md` on branch `t22-learning-test` (rolling origin, forecast months 3 to 12, 100 personas, all accounts; MAE ± SE across persons):

| Model | MAE [GBP] |
| --- | --- |
| Mean of history × ONS season (the form in 3.1) | 59.00 ± 2.62 |
| Last month | 72.27 ± 2.86 |
| Mean of history | 82.14 ± 3.71 |
| Bayesian NIG (`bayes.py`) | mean of history + 0.40 ± 0.59 (Holm p = 0.43) |

The seasonal model's advantage is partly circular: the generator multiplies every month by the same ONS factor, so the model is being told the rule that made the data. On these data the result shows what knowing the season is worth, not that it was learnt. On real data the weights would have to come from a source independent of the user (ONS retail sales, or aggregated real statements). The same file notes that "last month" benefits from the generator's month-to-month persistence (AR(1) coefficient 0.3 to 0.7 per person).

### 3.3 What training on the 100 personas can and cannot do

Andrew proposes estimating $w_m$ separately for groups (living alone, with dependants, with a partner, age). In the synthetic data every persona has the same seasonal profile by construction, so group-specific weights fitted to them would differ only by noise and would demonstrate nothing. Training on the 100 personas is meaningful for quantities the generator varies per person, which `ground_truth.csv` records:

| Learnable from the personas | Ground truth to test against | Not learnable (fixed by the generator) |
| --- | --- | --- |
| Spending level by net pay (the `bayes.py` prior already does this) | `ons_monthly_cat*`, `mult_cat*` | Seasonal profile $w_m$ (same ONS index for all) |
| Category mix per person | `mult_cat1` to `mult_cat12` | Group differences in seasonality |
| Payday share (spending concentrated after payday) | `payday_share` | |
| Month-to-month persistence | `ar_rho`, `ar_sd` | |
| Holdings from age, household, income | `accounts`, `p_*` columns | |

Habit recovery (`Figures/learning/habit_recovery.md`): category multipliers correlate with the truth at r = 0.904 after one month and 0.979 after twelve for persons without foregone spending; payday share at r = 0.963 in that subset. Seventeen persons have purchases foregone while overdrawn, which pulls these correlations down (r = 0.469 for multipliers at twelve months, all persons), because their spending measures a constraint, not a habit.

Proposal: train on persons and test on different persons (for example 80 train, 20 test, or five-fold across persons), and within each person forecast only months after the training window (rolling origin). Report MAE against the three baselines above with paired tests, as `ob_learning.py` already does.

### 3.4 Within-month remainder

Andrew: remaining spend $= \frac{D-d}{D}\,\hat r_n$. This assumes spending is spread evenly through the month and ignores what has already been spent. Two alternatives exist in the code base: the remainder $\max(0, \hat r_n - \text{spent so far})$, or `bayes.py`'s posterior predictive, which conditions on the days already seen and gives an interval and the probability of going below zero before payday. The payday share in the data means spending is front-loaded after payday, so the linear rule will over-predict late in a pay cycle. Decision needed (section 6).

## 4. Net worth and the goal

Net worth at month end: $W_n = \sum_{\text{accounts}} \text{balance} - \text{credit-card balances owed} - \text{outstanding BNPL}$. All terms are available from the customer picture once `bank.allAccounts` is used. The T22 visibility test shows why the main account alone is not enough: forecasting everyday spending from the main account gives MAE 297.25 GBP against 82.14 GBP from all accounts, because credit cards, second and joint accounts hold spending the statement does not show.

Goal: the user picks $g \ge$ CPI inflation (12-month CPI change from `data/ons_mm23_cpi_index_D7BT.csv`; which CPI series to use is to be confirmed). The month's target is $W_n^{\ast} = W_{n-1}(1+g)^{1/12}$. The forecast end-of-month net worth without the purchase is $\hat W_n = W_{\text{now}} + (\text{income still due}) - (\text{committed still due}) - \text{remaining } \hat r_n$, and with it $\hat W_n - P$ for price $P$ (or minus only the instalments due this month for pay-in-3, with the rest carried into later months' targets).

## 5. Decision at checkout

### 5.1 Andrew's four outcomes against the extension contract

| Andrew | Extension contract (`extension/README.md`) | Conflict |
| --- | --- | --- |
| 1. Meets goal: green if well above, orange if it meets the goal only without the item | `verdict` good (green) / caution (amber) | Andrew's orange case ("cannot afford it if they want to meet their goal") reads as a fail, which is `reconsider` |
| 2. Misses goal: red | `verdict` reconsider (red) | none |
| 3. Misses goal but investing the money instead keeps net worth: blue, "affordable in N days" | Blue is `neutral`, defined as "no budget known" | Colour clash; the contract has no "invest and wait" verdict |
| 4. Rainbow: cheaper option found | Cheaper options go in `alternatives` as a green card and must never change `verdict` | Consistent if "rainbow" is a card, not a verdict |

Proposal, keeping Auro's contract unchanged: map margin above the goal to `good` (margin above a threshold) or `caution` (meets the goal with a small margin); a miss to `reconsider`; express Andrew's case 3 as an action (`actions`, for example "Save towards it: affordable in N days") with its own card, not as a verdict; and case 4 as the existing `alternatives` card. The thresholds between good and caution are a team decision.

### 5.2 "Affordable in N days" (case 3)

The outline does not yet define $N$. One definition (proposal): the smallest $N$ such that, with the money set aside each day from the forecast surplus $\hat W_n - W_n^{\ast}$ earning the ISA or savings rate, the purchase no longer breaks the goal. The current engine already computes interest on a set-aside pot (`affordability.pot_interest`, Bank Rate as a proxy).

## 6. Decisions needed before implementation

| # | Decision | Options |
| --- | --- | --- |
| 1 | Forecast form | 3.1 deseasonalised mean (proposal); Andrew's literal formula; last month |
| 2 | Source of seasonal weights | ONS retail sales for everyone; group-specific weights (no information in the synthetic data, 3.3) |
| 3 | Value of $k$ | Andrew leaves open; the learning curve gives MAE by months of history |
| 4 | Within-month remainder | Linear $\frac{D-d}{D}\hat r_n$; $\hat r_n$ minus spent so far; `bayes.py` predictive |
| 5 | Horizon | Calendar month (Andrew) or pay cycle (current engine) |
| 6 | Net worth definition | Which accounts and liabilities count; whether pensions or investments outside Open Banking are asked for |
| 7 | Inflation measure | CPI all items (series to confirm) or CPIH |
| 8 | Colour mapping and thresholds | 5.1 proposal; changing Auro's contract instead |
| 9 | Definition of $N$ in case 3 | 5.2 proposal or another |
| 10 | Train/test split | Across persons and forward in time (proposal) |

## 7. Limitations

All results above are on synthetic data from `ob_generator.py` and say nothing about real customers' spending. The seasonal advantage is circular (3.2). Seventeen personas have constrained spending (3.3). Other income $i_n$ is not separated by any existing code. Nothing here is financial advice; the extension describes options and does not recommend.

## Log

- 2026-11-07 (Claude): outline written from Andrew's `HackTheBurgh.md` (commit `1d8ad2d`), the existing engine and the unmerged T22 learning results (`t22-learning-test`, commit `5404760`). Not implemented, by Harrison's instruction.
