# UK retail sales seasonality (non-seasonally adjusted)

Files: `retail_sales_seasonality.pdf`, `retail_sales_seasonality.svg` (this file: `retail_sales_seasonality.md`), written by `market_data.py` (commit `unknown` or later).

## Source data

[`data/ons_drsi_retail_sales_value_nsa_J5AH.csv`](../../data/ons_drsi_retail_sales_value_nsa_J5AH.csv): ONS Retail Sales Index (dataset DRSI), series `J5AH`, "RSI:Value Not seasonally Adjusted:All Retailers inc fuel:All Business Index",
Great Britain, value of sales (current prices), not seasonally adjusted, all retailers including automotive fuel, all
businesses. Release date shown: 23-10-2026. The file's unit field is blank and the index base year is not
stated in it. Open Government Licence v3.0. Plot style: `TeXFormat.py` sha256 `a33ce9f67e0a`.
Store-type breakdowns of the non-seasonally-adjusted value index are not published as index levels in DRSI (only as
percentage changes), so only the total is used.

## Filters, transformations and units

Monthly values for the complete calendar years 2021 to 2025 (n = 5 years; 2026 is partial and
excluded). Within each year the 12 monthly values are divided by that year's mean and multiplied by 100, so every year
has mean 100 (this removes year-to-year growth in the level); the raw index values are in the data file. Bars: mean over
years of the scaled value; error bars: standard error of the mean over years (sample standard deviation divided by
sqrt(n)). Black points: single years. The 2021 data include the early-2021 lockdown closures, which depress
January to April and so raise the other months relative to that year's mean.

## Plotted data

Scaled values (calendar-year mean = 100):

| Year | Jan | Feb | Mar | Apr | May | Jun | Jul | Aug | Sep | Oct | Nov | Dec |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 2021 | 81.28 | 84.17 | 92.41 | 99.42 | 100.87 | 101.76 | 100.54 | 98.09 | 97.53 | 103.66 | 117.35 | 122.92 |
| 2022 | 88.51 | 90.49 | 94.78 | 97.91 | 98.64 | 99.48 | 101.78 | 96.66 | 95.19 | 102.40 | 113.48 | 120.69 |
| 2023 | 88.86 | 92.30 | 95.04 | 98.58 | 100.00 | 99.49 | 99.59 | 97.16 | 95.74 | 101.62 | 114.49 | 117.12 |
| 2024 | 90.12 | 93.02 | 97.13 | 95.33 | 101.34 | 97.94 | 100.54 | 97.44 | 96.13 | 100.34 | 109.77 | 120.89 |
| 2025 | 88.42 | 92.64 | 96.17 | 99.01 | 98.03 | 97.84 | 100.68 | 96.95 | 97.25 | 101.95 | 113.23 | 117.83 |

Mean and SE across years:

| Month | n (years) | Mean | SE |
|---|---|---|---|
| Jan | 5 | 87.44 | 1.57 |
| Feb | 5 | 90.53 | 1.65 |
| Mar | 5 | 95.10 | 0.79 |
| Apr | 5 | 98.05 | 0.73 |
| May | 5 | 99.78 | 0.63 |
| Jun | 5 | 99.30 | 0.71 |
| Jul | 5 | 100.63 | 0.35 |
| Aug | 5 | 97.26 | 0.24 |
| Sep | 5 | 96.37 | 0.44 |
| Oct | 5 | 101.99 | 0.54 |
| Nov | 5 | 113.66 | 1.22 |
| Dec | 5 | 119.89 | 1.07 |

## n

5 years for every month. The replicate is the calendar year (one published value per month and year).

## Descriptive statistics

Uplift of each month over its year's mean, in per cent (estimate ± SE across years):

| Period | November | December |
|---|---|---|
| 2021 to 2025 (n = 5) | (13.7 ± 1.2)% | (19.9 ± 1.1)% |
| 2022 to 2025 (n = 4, excludes 2021) | (12.7 ± 1.0)% | (19.1 ± 1.0)% |

## Fits and tests

Not applicable.

## Random seed

None.

## Interpretation

November sales exceed the annual monthly mean by (13.7 ± 1.2)% and December sales by (19.9 ± 1.1)% (years
2021 to 2025). The figures describe retail sales as a whole, not any single category, and say nothing
about households' ability to pay.
