# model outline/

Design of the spending-forecast model and the checkout decision. Not implemented.

| File | Contents | Author |
| --- | --- | --- |
| `HackTheBurgh.md` | Andrew's original outline (income and regular payments inferred, seasonal weights, within-month remainder, net-worth goal, four colour-coded outcomes) | Andrew Pietraszkiewicz; kept unchanged |
| `MODEL_OUTLINE.md` | Andrew's outline mapped onto the existing code and data, what the 100 personas can train, conflicts with the extension contract, and the decisions needed | Claude |
| `IMPLEMENTATION.md` | Step-by-step instructions to build `model.py` on the simplified back end, with proposed defaults for the ten open decisions and done criteria per step | Claude |

## Log

- 2026-11-07 (Andrew): `HackTheBurgh.md` created (commit `1d8ad2d`).
- 2026-11-07 (Claude): `MODEL_OUTLINE.md` written on Harrison's request for a model outline. Harrison: "dont implement yet". Found while writing it: Andrew's forecast formula is a factor of 12 too small as written and averages seasonal months without deseasonalising (section 3.1); group-specific seasonal weights carry no information in the synthetic data, since every persona shares the ONS profile (3.3); his blue "invest" outcome clashes with the extension's blue `neutral` verdict (5.1). Ten decisions are open (section 6).
- 2026-11-07 (Claude): Harrison confirmed Andrew's model as the model, tested on the synthetic Open Banking data, with a simpler back end and no front-end merge by us. After T29 archived the old model, wrote `IMPLEMENTATION.md`; its defaults are proposals awaiting the team.
- 2026-11-07 (Claude): Harrison: "Yes, build it". Built as `model.py` (T30) with the proposed defaults; two choices beyond the instructions are recorded in `DECISIONS.md` (observable one-off rule; BNPL instalments as regular payments, so the backtest's actual is the generator's everyday spending less instalments).
