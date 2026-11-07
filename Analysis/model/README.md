# Analysis/model/

Written by `model.py` (task T30, Andrew's model); never edit by hand. Regenerate with `.venv\Scripts\python -X utf8 model.py` (about 40 s; needs the 100 persona JSON files in `Analysis/open_banking/`).

| File | Contents |
| --- | --- |
| `backtest.csv` | One row per persona and target month (February to October 2026): the actual everyday spending (generator's booked spending less BNPL instalments) and every forecast (deseasonalised and plain means, k = 1 to 6) |
| `validation.md` | Steps 1 and 2 against the generator's ground truth: everyday totals, salaries, mandates |

## Log

- 2026-11-07 (Claude, T30): first run at commit `0ef5018`. Validation: 970 of 1,200 person-months exact, 230 explained (lumpy purchases below GBP 250 are everyday to the model; BNPL instalments are regular payments to the model), 0 unexplained; salaries 100 of 100; no recent mandate missed.
