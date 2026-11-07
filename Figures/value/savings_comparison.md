# Money saved on each catalogue product, by source

Files: `savings_comparison.pdf`, `savings_comparison.svg` (this file: `savings_comparison.md`), written by `affordability_figures.py` (task T15).

## Source data

[`data/retail_prices_2026-11-07.csv`](../../data/retail_prices_2026-11-07.csv) (retailer prices collected on 07 November 2026; mainstream
retailers: Amazon UK, Argos, Currys, John Lewis, AO, Very; marketplace and third-party sellers are excluded) and
[`data/boe_bank_rate_IUDBEDR_2026-11-07.csv`](../../data/boe_bank_rate_IUDBEDR_2026-11-07.csv) (Bank of England Bank Rate, series IUDBEDR), via
`affordability.py` at commit `7098d56` and `affordability_figures.py`
at commit `f209ff6` or later. Plotted data:
[`Analysis/value/savings_comparison.csv`](../../Analysis/value/savings_comparison.csv).

## Filters, transformations and units

All five catalogue products (n = 5), each at its dearest mainstream price D [GBP] for a purchase on
2026-11-07; Bank Rate in force that day: 4.00% a year (from 2026-11-05). Definitions,
all in GBP and rounded to pence:

| Bar | Definition |
|---|---|
| Buying at the cheapest mainstream price | D minus the cheapest mainstream price for the same product (0 when only one mainstream price is listed or all are equal) |
| 1% cashback card (assumed rate) | 1% of D. The rate is an assumption for illustration, not taken from any card in `data/` |
| Pay-in-3 float interest (pot) | Interest the pay-in-3 pot would earn: D goes into an easy-access pot on the purchase day and three instalments of D/3 leave it on that day and one and two months later; simple daily interest at Bank Rate on the declining balance, 365-day year (`affordability.pot_interest`) |
| Credit-card float interest | Interest on D left in an easy-access account for an assumed 40-day average interest-free period before the card is cleared in full, at Bank Rate (`affordability.card_interest`) |

Bank Rate stands in for an easy-access savings rate; real rates vary. No tax on interest is deducted. The four sources
are not mutually exclusive (one could buy at the cheapest price with a cashback card and earn float interest), so the
bars are not to be added within a product unless a buyer could combine them. Bars are grouped by product; the value of
each bar is printed above it.

## Plotted data

| Product | n mainstream prices | Dearest mainstream [GBP] (retailer) | Cheapest mainstream [GBP] (retailer) | Buying at the cheapest mainstream price [GBP] | 1% cashback card (assumed rate) [GBP] | Pay-in-3 float interest (pot) [GBP] | Credit-card float interest [GBP] |
|---|---|---|---|---|---|---|---|
| P01 Amazon Echo Dot (5th generation) | 3 | 79.99 (Amazon UK; Argos; John Lewis) | 0.00 | 0.80 | 0.27 | 0.35 |
| P02 Sony WH-1000XM5 wireless noise-cancelling headphones | 4 | 199.00 (Amazon UK) | 30.99 | 2.30 | 0.76 | 1.01 |
| P03 Apple iPad 11-inch (A16, 2025) 128GB Wi-Fi | 3 | 399.00 (Amazon UK) | 10.00 | 4.09 | 1.36 | 1.79 |
| P04 Samsung Galaxy S25 5G 128GB (12GB RAM) | 1 | 458.00 (Amazon UK) | 0.00 | 4.58 | 1.52 | 2.01 |
| P05 Apple MacBook Air 15-inch (2025) M4 16GB 256GB | 2 | 854.97 (Currys) | 189.03 | 10.44 | 3.47 | 4.58 |

## n

5 products; one value per product and source (no replicates). The number of mainstream prices behind the
dearest and cheapest prices is given per product.

## Descriptive statistics

Totals over the five products [GBP]: Buying at the cheapest mainstream price 230.02, 1% cashback card (assumed rate) 22.21, Pay-in-3 float interest (pot) 7.38, Credit-card float interest 9.74.
Error bars: not applicable (each value is a single calculation from one collected price).

## Fits and tests

Not applicable.

## Random seed

None.

## Interpretation

Over the five products, buying at the cheapest mainstream price instead of the dearest saves 230.02 GBP
in total, an assumed 1% cashback 22.21 GBP, the pay-in-3 pot's float interest
7.38 GBP and a credit card cleared in full 9.74 GBP, at Bank Rate 4.00%. The
cheapest-price saving is 0 for P01 (the mainstream prices are equal), P04 (only one mainstream price was obtained), so only the other three sources save money on them. The float interest on a few hundred pounds over one to two months is a
few pounds at most. These are facts about five products on one day, not a recommendation.
