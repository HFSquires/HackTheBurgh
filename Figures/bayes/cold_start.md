# Cold start: the posterior as days of spending are observed

Plot: `cold_start.pdf` / `.svg`. Written by `bayes.py`; regenerate with it.

## Source and transformations

Source: the 100 statements in `Analysis/mock_statements/`, via `bayes.py` (which reuses `forecast.py` and `affordability.py`). Discretionary spending as in `affordability.card_spend` (card payments that are neither BNPL instalments nor committed payments), committed payments detected on the rows up to 30 September 2026. Every model is fitted on the rows up to 30 September only (August and September); each person's prior comes from a fit on the other persons, by person-level 10-fold cross-validation with forecast.py's folds (seed 20261107). October is used only to score. Statements last changed in commit `4617bf4`; `bayes.py` at commit `7098d56`; `forecast.py` at commit `f209ff6`; `affordability.py` at commit `7098d56` (or later, if uncommitted changes were run).

Model (full derivation in the docstring of `bayes.py`): daily discretionary spending, Gaussian on the raw scale; within a calendar month of D days each day has mean beta / D (beta: the person's monthly budget) and variance sigma^2, and two days of the same month have correlation (phi - 1) / (D - 1), so a month's total has variance phi D sigma^2. Normal-Inverse-Gamma prior on (beta, sigma^2) centred on a population regression of ln budget on ln net pay; exact conjugate update after each day; Student-t predictive for the sum over any set of future days. The independent-days model is the same with phi fixed at 1.

Two example persons, chosen by rule: the persons whose prior mean budget is closest to (persona012) and furthest from (persona061) their posterior mean after 30 September (absolute log ratio). For t = 0 (prior only) to 61 days observed from 1 August, the monthly-budget posterior after the first t days: posterior mean of beta (line), 95 % central credible interval of beta (dark band), and 95 % central posterior predictive interval of the October total (light band; budget uncertainty plus October's own variation). Dashed: the generator's expected October discretionary spending (`forecast.generator_mean`, a reference using the generator's internals); dotted: the actual October total; grey vertical line: end of August. Each person's prior comes from the cross-validation fold that excludes them. Units GBP. n = 1 person per panel, 62 posteriors each.

## Values at selected days

| Person | Days observed | Prior mean [GBP] | Posterior mean budget [GBP] | 95 % credible [GBP] | Width [GBP] | 95 % predictive, October total [GBP] | Width [GBP] | a (posterior shape) |
|---|---|---|---|---|---|---|---|---|
| persona012 | 0 | 869.82 | 869.82 | 632.34 to 1107.31 | 474.97 | 628.28 to 1111.37 | 483.08 | 31.8 |
| persona012 | 7 | 869.82 | 859.71 | 637.31 to 1082.11 | 444.80 | 632.94 to 1086.48 | 453.54 | 35.3 |
| persona012 | 14 | 869.82 | 827.86 | 635.19 to 1020.53 | 385.33 | 630.51 to 1025.20 | 394.69 | 38.8 |
| persona012 | 30 | 869.82 | 843.28 | 776.96 to 909.61 | 132.65 | 765.17 to 921.39 | 156.22 | 46.8 |
| persona012 | 61 | 869.82 | 871.26 | 842.30 to 900.22 | 57.92 | 820.54 to 921.98 | 101.44 | 62.3 |
| persona061 | 0 | 456.18 | 456.18 | 336.70 to 575.65 | 238.95 | 334.42 to 577.94 | 243.52 | 24.3 |
| persona061 | 7 | 456.18 | 433.21 | 325.62 to 540.81 | 215.20 | 323.27 to 543.15 | 219.88 | 27.8 |
| persona061 | 14 | 456.18 | 400.18 | 305.01 to 495.35 | 190.34 | 302.48 to 497.88 | 195.39 | 31.3 |
| persona061 | 30 | 456.18 | 312.94 | 279.36 to 346.52 | 67.16 | 273.24 to 352.64 | 79.40 | 39.3 |
| persona061 | 61 | 456.18 | 306.64 | 293.38 to 319.89 | 26.51 | 283.41 to 329.87 | 46.46 | 54.8 |

| Person | Generator mean, October [GBP] | Actual October [GBP] | Net monthly pay [GBP] |
|---|---|---|---|
| persona012 | 846.28 | 812.48 | 2973.19 |
| persona061 | 308.41 | 305.28 | 1242.77 |

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
