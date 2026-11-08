# Cold start: the posterior as days of spending are observed

Plot: `cold_start.pdf` / `.svg`. Written by `bayes.py`; regenerate with it.

## Source and transformations

Source: the 100 statements in `Analysis/mock_statements/`, via `bayes.py` (which reuses `forecast.py` and `affordability.py`). Discretionary spending as in `affordability.card_spend` (card payments that are neither BNPL instalments nor committed payments), committed payments detected on the rows up to 30 September 2026. Every model is fitted on the rows up to 30 September only (August and September); each person's prior comes from a fit on the other persons, by person-level 10-fold cross-validation with forecast.py's folds (seed 20261107). October is used only to score. Statements last changed in commit `7fa4ca1`; `bayes.py` at commit `7098d56`; `forecast.py` at commit `f209ff6`; `affordability.py` at commit `7098d56` (or later, if uncommitted changes were run).

Model (full derivation in the docstring of `bayes.py`): daily discretionary spending, Gaussian on the raw scale; within a calendar month of D days each day has mean beta / D (beta: the person's monthly budget) and variance sigma^2, and two days of the same month have correlation (phi - 1) / (D - 1), so a month's total has variance phi D sigma^2. Normal-Inverse-Gamma prior on (beta, sigma^2) centred on a population regression of ln budget on ln net pay; exact conjugate update after each day; Student-t predictive for the sum over any set of future days. The independent-days model is the same with phi fixed at 1.

Two example persons, chosen by rule: the persons whose prior mean budget is closest to (persona091) and furthest from (persona061) their posterior mean after 30 September (absolute log ratio). For t = 0 (prior only) to 61 days observed from 1 August, the monthly-budget posterior after the first t days: posterior mean of beta (line), 95 % central credible interval of beta (dark band), and 95 % central posterior predictive interval of the October total (light band; budget uncertainty plus October's own variation). Dashed: the generator's expected October discretionary spending (`forecast.generator_mean`, a reference using the generator's internals); dotted: the actual October total; grey vertical line: end of August. Each person's prior comes from the cross-validation fold that excludes them. Units GBP. n = 1 person per panel, 62 posteriors each.

## Values at selected days

| Person | Days observed | Prior mean [GBP] | Posterior mean budget [GBP] | 95 % credible [GBP] | Width [GBP] | 95 % predictive, October total [GBP] | Width [GBP] | a (posterior shape) |
|---|---|---|---|---|---|---|---|---|
| persona091 | 0 | 962.21 | 962.21 | 696.76 to 1227.65 | 530.89 | 692.30 to 1232.12 | 539.82 | 23.4 |
| persona091 | 7 | 962.21 | 986.66 | 740.35 to 1232.97 | 492.62 | 735.57 to 1237.75 | 502.18 | 26.9 |
| persona091 | 14 | 962.21 | 978.64 | 760.84 to 1196.44 | 435.60 | 755.60 to 1201.68 | 446.08 | 30.4 |
| persona091 | 30 | 962.21 | 933.18 | 859.71 to 1006.65 | 146.94 | 846.65 to 1019.71 | 173.06 | 38.4 |
| persona091 | 61 | 962.21 | 962.60 | 930.83 to 994.37 | 63.53 | 906.97 to 1018.23 | 111.27 | 53.9 |
| persona061 | 0 | 421.26 | 421.26 | 310.06 to 532.47 | 222.41 | 307.86 to 534.67 | 226.81 | 25.1 |
| persona061 | 7 | 421.26 | 398.74 | 298.23 to 499.25 | 201.03 | 295.96 to 501.52 | 205.56 | 28.6 |
| persona061 | 14 | 421.26 | 369.51 | 280.49 to 458.53 | 178.05 | 278.03 to 460.99 | 182.95 | 32.1 |
| persona061 | 30 | 421.26 | 290.75 | 259.15 to 322.36 | 63.21 | 253.21 to 328.30 | 75.09 | 40.1 |
| persona061 | 61 | 421.26 | 284.46 | 271.76 to 297.17 | 25.41 | 262.19 to 306.74 | 44.55 | 55.6 |

| Person | Generator mean, October [GBP] | Actual October [GBP] | Net monthly pay [GBP] |
|---|---|---|---|
| persona091 | 961.36 | 965.85 | 3814.81 |
| persona061 | 286.10 | 283.53 | 1242.77 |

Random seed: not applicable.

## Interpretation

With no data the interval is the population prior (its width set by tau^2, the between-person spread left after net pay). During the first days the data barely move it, because a few days' spending says little about a month's total. As the first month fills, each day becomes more informative, since under the budget model the days still to come in a month must make up its total; the credible interval collapses near the end of August and narrows again through September. The predictive interval for October cannot shrink below October's own variation, phi D sigma^2. No single day moved the posterior mean outside its previous 95 % credible interval.

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
