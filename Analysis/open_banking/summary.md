# Open Banking synthetic data: summary

Written by `ob_generator.py` (seed 20261107, N = 100); 1 November 2025 to 31 October 2026, pending payments on 1 and 2 November 2026. Synthetic data, not real bank records.

| Quantity | Value |
|---|---|
| Personas | 100 |
| Accounts held | 263 (current 100, savings 100, credit card 63) |
| Credit-card holders paying in full | 39 of 63 |
| Current account below zero at any time | 16 |
| Overdrawn at the end of at least one day, after any top-up from savings | 4 |
| Topped up from savings at least once | 16 |
| In unarranged overdraft at least one day (flagged) | 4 |
| Persons with foregone payments (count) | 16 (1832) |
| Persons with declined payments (count) | 3 (5) |
| Persons with returned payments (count) | 0 (0) |
| Savings standing order | 52 |
| BNPL plans (persons) | 34 |
| Synthetic lumpy purchases | 91 |
| Booked transactions | 66641 |
| Pending transactions | 344 |
| Current-account end balance [GBP], min / lower quartile / median / upper quartile / max | -3418.91 / 4877.76 / 10065.05 / 15184.99 / 28483.44 |
| Savings end balance [GBP], median | 6220.82 |
| Card end balance owed [GBP], median over holders | 893.88 |

Seasonal factors (ONS retail sales J5AH, mean of 2021 to 2025 with each year scaled to mean 1):

| Jan | Feb | Mar | Apr | May | Jun | Jul | Aug | Sep | Oct | Nov | Dec |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 0.8744 | 0.9053 | 0.9510 | 0.9805 | 0.9978 | 0.9930 | 1.0063 | 0.9726 | 0.9637 | 1.0199 | 1.1366 | 1.1989 |
