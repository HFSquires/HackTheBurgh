# Money saved on each catalogue product, by source

Files: `savings_comparison.pdf`, `savings_comparison.svg` (this file: `savings_comparison.md`), written by `affordability_figures.py` (task T15).

## Source data

[`data/retail_prices_2026-11-07.csv`](../../data/retail_prices_2026-11-07.csv) (retailer prices collected on 07 November 2026; mainstream
retailers: Amazon UK, Argos, Currys, John Lewis, AO, Very; marketplace and third-party sellers are excluded) and
[`data/boe_bank_rate_IUDBEDR_2026-11-07.csv`](../../data/boe_bank_rate_IUDBEDR_2026-11-07.csv) (Bank of England Bank Rate, series IUDBEDR), via
`affordability.py` at commit `2c5e080` and `affordability_figures.py`
at commit `2c5e080` or later. Plotted data:
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
| P01 <bound method Series.prod of product_id                                          P01
product                Amazon Echo Dot (5th generation)
n_mainstream_prices                                   3
dearest_retailers          Amazon UK; Argos; John Lewis
dearest                                           79.99
cheapest_retailers         Amazon UK; Argos; John Lewis
cheapest                                          79.99
bank_rate                                           4.0
bank_rate_date                               2026-11-05
cheapest_saving                                     0.0
cashback                                            0.8
pot                                                0.27
card                                               0.35
Name: 0, dtype: object> | 3 | 79.99 (Amazon UK; Argos; John Lewis) | 79.99 (Amazon UK; Argos; John Lewis) | 0.00 | 0.80 | 0.27 | 0.35 |
| P02 <bound method Series.prod of product_id                                                           P02
product                Sony WH-1000XM5 wireless noise-cancelling head...
n_mainstream_prices                                                    4
dearest_retailers                                      John Lewis; Argos
dearest                                                           229.99
cheapest_retailers                                             Amazon UK
cheapest                                                           199.0
bank_rate                                                            4.0
bank_rate_date                                                2026-11-05
cheapest_saving                                                    30.99
cashback                                                             2.3
pot                                                                 0.76
card                                                                1.01
Name: 1, dtype: object> | 4 | 229.99 (John Lewis; Argos) | 199.00 (Amazon UK) | 30.99 | 2.30 | 0.76 | 1.01 |
| P03 <bound method Series.prod of product_id                                                    P03
product                Apple iPad 11-inch (A16, 2025) 128GB Wi-Fi
n_mainstream_prices                                             3
dearest_retailers                                  AO; John Lewis
dearest                                                     409.0
cheapest_retailers                                      Amazon UK
cheapest                                                    399.0
bank_rate                                                     4.0
bank_rate_date                                         2026-11-05
cheapest_saving                                              10.0
cashback                                                     4.09
pot                                                          1.36
card                                                         1.79
Name: 2, dtype: object> | 3 | 409.00 (AO; John Lewis) | 399.00 (Amazon UK) | 10.00 | 4.09 | 1.36 | 1.79 |
| P04 <bound method Series.prod of product_id                                                P04
product                Samsung Galaxy S25 5G 128GB (12GB RAM)
n_mainstream_prices                                         1
dearest_retailers                                   Amazon UK
dearest                                                 458.0
cheapest_retailers                                  Amazon UK
cheapest                                                458.0
bank_rate                                                 4.0
bank_rate_date                                     2026-11-05
cheapest_saving                                           0.0
cashback                                                 4.58
pot                                                      1.52
card                                                     2.01
Name: 3, dtype: object> | 1 | 458.00 (Amazon UK) | 458.00 (Amazon UK) | 0.00 | 4.58 | 1.52 | 2.01 |
| P05 <bound method Series.prod of product_id                                                        P05
product                Apple MacBook Air 15-inch (2025) M4 16GB 256GB
n_mainstream_prices                                                 2
dearest_retailers                                                  AO
dearest                                                        1044.0
cheapest_retailers                                             Currys
cheapest                                                       854.97
bank_rate                                                         4.0
bank_rate_date                                             2026-11-05
cheapest_saving                                                189.03
cashback                                                        10.44
pot                                                              3.47
card                                                             4.58
Name: 4, dtype: object> | 2 | 1044.00 (AO) | 854.97 (Currys) | 189.03 | 10.44 | 3.47 | 4.58 |

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
7.38 GBP and a credit card cleared in full 9.74 GBP, at Bank Rate 4.00%. For
P01, P04 the catalogue lists no price difference between mainstream retailers,
so only the other three sources save money. The float interest on a few hundred pounds over one to two months is a
few pounds at most. These are facts about five products on one day, not a recommendation.
