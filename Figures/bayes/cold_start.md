# Cold start: the posterior as days of spending are observed

Plot: `cold_start.pdf` / `.svg`. Written by `bayes.py`; regenerate with it.

## Source and transformations

Source: the 100 statements in `Analysis/mock_statements/`, via `bayes.py` (which reuses `forecast.py` and `affordability.py`). Discretionary spending as in `affordability.card_spend` (card payments that are neither BNPL instalments nor committed payments), committed payments detected on the rows up to 30 September 2026. Every model is fitted on the rows up to 30 September only (August and September); each person's prior comes from a fit on the other persons, by person-level 10-fold cross-validation with forecast.py's folds (seed 20261107). October is used only to score.

Model (full derivation in the docstring of `bayes.py`): daily discretionary spending, Gaussian on the raw scale; within a calendar month of D days each day has mean beta / D (beta: the person's monthly budget) and variance sigma^2, and two days of the same month have correlation (phi - 1) / (D - 1), so a month's total has variance phi D sigma^2. Normal-Inverse-Gamma prior on (beta, sigma^2) centred on a population regression of ln budget on ln net pay; exact conjugate update after each day; Student-t predictive for the sum over any set of future days. The independent-days model is the same with phi fixed at 1.

Two example persons, chosen by rule: the persons whose prior mean budget is closest to (persona073) and furthest from (persona061) their posterior mean after 30 September (absolute log ratio). For t = 0 (prior only) to 61 days observed from 1 August, the monthly-budget posterior after the first t days: posterior mean of beta (line), 95 % central credible interval of beta (dark band), and 95 % central posterior predictive interval of the October total (light band; budget uncertainty plus October's own variation). Dashed: the generator's expected October discretionary spending (`forecast.generator_mean`, a reference using the generator's internals); dotted: the actual October total; grey vertical line: end of August. Each person's prior comes from the cross-validation fold that excludes them. Units GBP. n = 1 person per panel, 62 posteriors each.

## Values at selected days

| Person | Days observed | Prior mean [GBP] | Posterior mean budget [GBP] | 95 % credible [GBP] | Width [GBP] | 95 % predictive, October total [GBP] | Width [GBP] | a (posterior shape) |
|---|---|---|---|---|---|---|---|---|
| persona073 | 0 | 695.52 | 695.52 | 508.72 to 882.31 | 373.59 | 505.56 to 885.48 | 379.92 | 23.6 |
| persona073 | 7 | 695.52 | 711.59 | 540.96 to 882.22 | 341.26 | 537.65 to 885.52 | 347.87 | 27.1 |
| persona073 | 14 | 695.52 | 693.26 | 543.92 to 842.59 | 298.67 | 540.38 to 846.13 | 305.76 | 30.6 |
| persona073 | 30 | 695.52 | 616.04 | 563.81 to 668.27 | 104.45 | 554.84 to 677.24 | 122.40 | 38.6 |
| persona073 | 61 | 695.52 | 693.76 | 670.26 to 717.25 | 46.99 | 652.61 to 734.90 | 82.30 | 54.1 |
| persona061 | 0 | 434.36 | 434.36 | 320.07 to 548.64 | 228.58 | 317.90 to 550.82 | 232.92 | 24.1 |
| persona061 | 7 | 434.36 | 412.38 | 309.50 to 515.26 | 205.76 | 307.27 to 517.49 | 210.21 | 27.6 |
| persona061 | 14 | 434.36 | 380.44 | 289.50 to 471.38 | 181.88 | 287.10 to 473.78 | 186.67 | 31.1 |
| persona061 | 30 | 434.36 | 296.63 | 264.52 to 328.74 | 64.22 | 258.70 to 334.57 | 75.87 | 39.1 |
| persona061 | 61 | 434.36 | 290.59 | 277.96 to 303.21 | 25.25 | 268.46 to 312.71 | 44.26 | 54.6 |

| Person | Generator mean, October [GBP] | Actual October [GBP] | Net monthly pay [GBP] |
|---|---|---|---|
| persona073 | 679.54 | 690.08 | 2297.93 |
| persona061 | 292.45 | 289.73 | 1198.45 |

Random seed: not applicable.

## Interpretation

With no data the interval is the population prior (its width set by tau^2, the between-person spread left after net pay). During the first days the data barely move it, because a few days' spending says little about a month's total. As the first month fills, each day becomes more informative, since under the budget model the days still to come in a month must make up its total; the credible interval collapses near the end of August and narrows again through September. The predictive interval for October cannot shrink below October's own variation, phi D sigma^2. Days on which one day's spending moved the posterior mean outside its previous 95 % credible interval: persona073: after day 31 (2026-08-31, spending 96.91 GBP) the posterior mean moved from 616.04 to 685.67 GBP, outside the previous 95 % credible interval (563.81 to 668.27). Single days are right-skewed (a few large card payments), which the Gaussian likelihood ignores, so near the end of a month one large day can move the estimate further than the interval allowed.

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
