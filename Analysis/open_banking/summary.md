# Open Banking synthetic data: summary

Written by `ob_generator.py` (seed 20261107, N = 100); 1 November 2025 to 31 October 2026, pending payments on 1 and 2 November 2026. Synthetic data, not real bank records.

## Accounts held

| Accounts per person | 1 | 2 | 3 | 4 | 5 | 6 | 7 |
|---|---|---|---|---|---|---|---|
| Persons | 3 | 15 | 29 | 33 | 18 | 1 | 1 |

| Account | Persons holding | Mean model probability | FLS 2024 UK adults (total) |
|---|---|---|---|
| Current account | 100 | 1.000 | 0.97 (any current account) |
| Current account (other provider) | 38 | 0.351 | 0.27 (derived lower bound) |
| Joint current account | 31 | 0.310 | not available (synthetic rule) |
| Easy-access savings | 57 | 0.616 | 0.57 |
| Cash ISA | 31 | 0.321 | 0.32 |
| Credit cards, 0 / 1 / 2 | 18 / 66 / 16 | 0.749 (any card) | 0.65 (any card) |

## Balances and behaviour

| Quantity | Value |
|---|---|
| Main current account below zero at any time | 10 |
| Main current account overdrawn at the end of at least one day, after any top-up from savings | 6 |
| Topped up from savings or ISA at least once | 6 |
| In unarranged overdraft at least one day (flagged) | 4 |
| Persons with foregone payments (count) | 10 (1967) |
| Persons with declined payments (count) | 1 (1) |
| Persons with returned payments (count) | 1 (8) |
| Savings or ISA standing order | 30 |
| BNPL plans (persons) | 34 |
| Synthetic lumpy purchases | 100 |
| Booked transactions | 67886 |
| Pending transactions | 349 |
| Main current-account end balance [GBP], min / lower quartile / median / upper quartile / max | -1743.76 / 6115.82 / 12068.90 / 18137.32 / 51968.01 |

Seasonal factors (ONS retail sales J5AH, mean of 2021 to 2025 with each year scaled to mean 1):

| Jan | Feb | Mar | Apr | May | Jun | Jul | Aug | Sep | Oct | Nov | Dec |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 0.8744 | 0.9053 | 0.9510 | 0.9805 | 0.9978 | 0.9930 | 1.0063 | 0.9726 | 0.9637 | 1.0199 | 1.1366 | 1.1989 |
