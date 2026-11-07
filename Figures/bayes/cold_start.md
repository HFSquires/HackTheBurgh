# Cold start: the posterior as days of spending are observed

Plot: `cold_start.pdf` / `.svg`. Written by `bayes.py`; regenerate with it.

## Source and transformations

Source: the 100 statements in `Analysis/mock_statements/`, via `bayes.py` (which reuses `forecast.py` and `affordability.py`). Discretionary spending as in `affordability.card_spend` (card payments that are neither BNPL instalments nor committed payments), committed payments detected on the rows up to 30 September 2026. Every model is fitted on the rows up to 30 September only (August and September); each person's prior comes from a fit on the other persons, by person-level 10-fold cross-validation with forecast.py's folds (seed 20261107). October is used only to score. Statements last changed in commit `e01f34f`; `bayes.py` at commit `22804b4`; `forecast.py` at commit `22804b4`; `affordability.py` at commit `2c5e080` (or later, if uncommitted changes were run).

Model (full derivation in the docstring of `bayes.py`): daily discretionary spending, Gaussian on the raw scale; within a calendar month of D days each day has mean beta / D (beta: the person's monthly budget) and variance sigma^2, and two days of the same month have correlation (phi - 1) / (D - 1), so a month's total has variance phi D sigma^2. Normal-Inverse-Gamma prior on (beta, sigma^2) centred on a population regression of ln budget on ln net pay; exact conjugate update after each day; Student-t predictive for the sum over any set of future days. The independent-days model is the same with phi fixed at 1.

Two example persons, chosen by rule: the persons whose prior mean budget is closest to (persona073) and furthest from (persona061) their posterior mean after 30 September (absolute log ratio). For t = 0 (prior only) to 61 days observed from 1 August, the monthly-budget posterior after the first t days: posterior mean of beta (line), 95 % central credible interval of beta (dark band), and 95 % central posterior predictive interval of the October total (light band; budget uncertainty plus October's own variation). Dashed: the generator's expected October discretionary spending (`forecast.generator_mean`, a reference using the generator's internals); dotted: the actual October total; grey vertical line: end of August. Each person's prior comes from the cross-validation fold that excludes them. Units GBP. n = 1 person per panel, 62 posteriors each.

## Values at selected days

| Person | Days observed | Prior mean [GBP] | Posterior mean budget [GBP] | 95 % credible [GBP] | Width [GBP] | 95 % predictive, October total [GBP] | Width [GBP] | a (posterior shape) |
|---|---|---|---|---|---|---|---|---|
| persona073 | 0 | 735.31 | 735.31 | 537.86 to 932.76 | 394.90 | 534.52 to 936.09 | 401.57 | 23.8 |
| persona073 | 7 | 735.31 | 753.53 | 573.16 to 933.91 | 360.75 | 569.66 to 937.40 | 367.73 | 27.3 |
| persona073 | 14 | 735.31 | 733.57 | 575.88 to 891.26 | 315.38 | 572.13 to 895.01 | 322.87 | 30.8 |
| persona073 | 30 | 735.31 | 652.09 | 597.05 to 707.14 | 110.09 | 587.54 to 716.65 | 129.11 | 38.8 |
| persona073 | 61 | 735.31 | 733.18 | 708.37 to 757.98 | 49.61 | 689.74 to 776.62 | 86.88 | 54.3 |
| persona061 | 0 | 458.01 | 458.01 | 337.62 to 578.40 | 240.78 | 335.33 to 580.69 | 245.35 | 24.3 |
| persona061 | 7 | 458.01 | 434.67 | 326.30 to 543.04 | 216.74 | 323.95 to 545.39 | 221.44 | 27.8 |
| persona061 | 14 | 458.01 | 401.20 | 305.40 to 497.00 | 191.59 | 302.88 to 499.53 | 196.65 | 31.3 |
| persona061 | 30 | 458.01 | 313.01 | 279.30 to 346.73 | 67.44 | 273.15 to 352.88 | 79.73 | 39.3 |
| persona061 | 61 | 458.01 | 306.65 | 293.35 to 319.95 | 26.60 | 283.34 to 329.96 | 46.62 | 54.8 |

| Person | Generator mean, October [GBP] | Actual October [GBP] | Net monthly pay [GBP] |
|---|---|---|---|
| persona073 | 718.20 | 729.44 | 2297.93 |
| persona061 | 308.41 | 305.28 | 1198.45 |

Random seed: not applicable.

## Interpretation

With no data the interval is the population prior (its width set by tau^2, the between-person spread left after net pay). During the first days the data barely move it, because a few days' spending says little about a month's total. As the first month fills, each day becomes more informative, since under the budget model the days still to come in a month must make up its total; the credible interval collapses near the end of August and narrows again through September. The predictive interval for October cannot shrink below October's own variation, phi D sigma^2. Days on which one day's spending moved the posterior mean outside its previous 95 % credible interval: persona073: after day 31 (2026-08-31, spending 101.05 GBP) the posterior mean moved from 652.09 to 724.44 GBP, outside the previous 95 % credible interval (597.05 to 707.14). Single days are right-skewed (a few large card payments), which the Gaussian likelihood ignores, so near the end of a month one large day can move the estimate further than the interval allowed.

## What these data can and cannot show

`mock_statements.py` draws each persona's card spending in each of nine ONS categories, each month, as the modelled
monthly mean (ONS Family Spending for the persona's region, household type and income decile) multiplied by an independent
factor drawn uniformly between 0.9 and 1.1, less any BNPL instalment charged to that category that month; transaction days
are uniform over the month and amounts are split by lognormal weights. The factors are independent across months and
categories, so a persona has no habit beyond its deterministic mean, no trend, no seasonality, no irregular large purchase
and no change of income. The best possible forecast of October is therefore the generator mean less the BNPL instalments
due in October (the reference), whose error is October's own noise; a forecast that averages August and September adds
those months' noise (error variance 1.5 times the reference's once the BNPL schedule is accounted for; last month alone,
2 times). The naive baselines are thus close to the best achievable apart from BNPL, and a learned model can gain only by
reading the BNPL schedule and by shrinking a two-month mean towards a pooled estimate. This backtest measures how well the
models recover the generator's process, not how real customers behave.
