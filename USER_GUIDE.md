# User guide

Fill in each section from the code as it actually exists, and update it whenever setup, commands or outputs change. At present the only runnable code is the mock bank-statement generator (`mock_statements.py`, task T05). The browser extension does not exist yet.

## Purpose

`mock_statements.py` writes synthetic bank-statement CSVs for the demo of the affordability extension (Bank of Scotland "Smart Cost of Living" challenge). Each statement belongs to a synthetic Scottish persona from the Hugging Face dataset `nvidia/Nemotron-Personas-UK`; the salary comes from ONS earnings by occupation (ASHE Table 14) and the spending from ONS Family Spending. The output is deterministic: the same inputs give byte-identical files.

## Setup

Windows, from the repository root, without admin rights:

```
uv venv --python 3.12
uv pip install --no-cache -r requirements.txt
```

The only dependency is `openpyxl`. The raw inputs are already committed in `data/`, except the 9.6 MB ASHE zip, which is not needed (the extracted workbook is committed); `data/README.md` gives its download command.

## Inputs

All in `data/` (sources, licences and dates in `data/README.md`): five pages of persona rows (`personas_rows_offset*.json`, 500 rows, 53 Scottish), the ASHE Table 14.7a annual gross pay workbook (2025 revised), and Family Spending workbooks 2 and 3 (financial year ending 2025).

## Commands

```
.venv\Scripts\python mock_statements.py           # write Analysis/mock_statements/
.venv\Scripts\python mock_statements.py --check   # self-check
```

If the console shows encoding errors, add `-X utf8` after `python`.

## Options

`--check` runs the self-check instead of writing outputs: column order, five personas, balances reconcile on every row, a salary credit in each of August, September and October 2026, at least four buy-now-pay-later rows, dates ascending and ending by 31 October 2026, and identical output across two runs. The random seed and the CSV layout (columns, date format, fake sort code) are set in one block at the top of the script.

## Outputs

`Analysis/mock_statements/`: one CSV per persona (`persona<N>_<uuid8>.csv`), three months to 31 October 2026, in the Lloyds Banking Group export layout (Transaction Date, Transaction Type, Sort Code, Account Number, Transaction Description, Debit Amount, Credit Amount, Balance; dates DD/MM/YYYY); and `personas.md`, summarising each persona, the salary used and its source row, and monthly spending by category.

## Limitations

The CSV layout is an unchecked belief about the Lloyds export format. Net pay uses rest-of-UK income tax and National Insurance bands, not Scottish ones. Spending is the Scottish average adjusted by household type and is not scaled to income, so persona 1 goes about £918 overdrawn and persona 3 accumulates about £12,800 over three months. Tenure is sampled, and four of the five personas own outright. Merchant names, transaction dates and buy-now-pay-later schedules are synthetic flavour. Each approximation is marked with a `ponytail:` comment in the code. Fixes are planned as T05b.

## Troubleshooting

If the Hugging Face or ONS files need refreshing, use the URLs in `data/README.md`; the datasets-server `filter` endpoint returned an authentication error on 7 November 2026, so Scottish rows are selected in code from unfiltered pages.
