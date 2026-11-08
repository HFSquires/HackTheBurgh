# extension/demo

Synthetic shopping demo pages.

- 2026-11-08 (Codex, T34): Ported the savings/overdraft UI and explicit pay-in-3 comparison onto frontend-extension; setup is in the root USER_GUIDE.md.

- 2026-11-08 (Codex): Fixed demo verdict buttons being overwritten by the bank forecast. Explicit mock overrides bypass bank/cached answers and surface mock errors; bank/goal controls restore model mode. Mock results are labelled and displayed for every verdict. Regression checks pass.

- 2026-11-08 (Codex): Payment comparison now uses visible enabled checkout payment controls, follows the selected option, names the offered pay-in-3 provider, and shows repayment amounts and same-horizon minima outside Explain. Unsupported terms are not silently treated as pay-now. Selecting a payment in the demo leaves mock-override mode. Detector, adapter and model regression checks pass, including red-to-amber improvement and later-instalment overdraft cases.
