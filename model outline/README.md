# model outline/

Design of the spending-forecast model and the checkout decision. Not implemented.

| File | Contents | Author |
| --- | --- | --- |
| `HackTheBurgh.md` | Andrew's original outline (income and regular payments inferred, seasonal weights, within-month remainder, net-worth goal, four colour-coded outcomes) | Andrew Pietraszkiewicz; kept unchanged |
| `MODEL_OUTLINE.md` | Andrew's outline mapped onto the existing code and data, what the 100 personas can train, conflicts with the extension contract, and the decisions needed | Claude |

## Log

- 2026-11-07 (Andrew): `HackTheBurgh.md` created (commit `1d8ad2d`).
- 2026-11-07 (Claude): `MODEL_OUTLINE.md` written on Harrison's request for a model outline. Harrison: "dont implement yet". Found while writing it: Andrew's forecast formula is a factor of 12 too small as written and averages seasonal months without deseasonalising (section 3.1); group-specific seasonal weights carry no information in the synthetic data, since every persona shares the ONS profile (3.3); his blue "invest" outcome clashes with the extension's blue `neutral` verdict (5.1). Ten decisions are open (section 6).
