# extension/src

Content scripts and background services.

- 2026-11-08 (Codex, T34): Ported the savings/overdraft UI and explicit pay-in-3 comparison onto frontend-extension; setup is in the root USER_GUIDE.md.

- 2026-11-08 (Codex): On user request, shortened buyer-facing warnings to a headline and one sentence. Forecast explanation, chart, figures and repayment schedule are collapsed under Explain; Compare pay in 3 remains visible. Existing frontend checks and syntax checks pass.

- 2026-11-08 (Codex): Replaced Pause for 24 hours with the primary View instalment options action, opening the existing pay-in-3 comparison. Removed the duplicate secondary comparison button.

- 2026-11-08 (Codex): Moved Explain to a muted pill at the top right of the financial result, with an accessible expand/collapse toggle.

- 2026-11-08 (Codex): Explain toggles its label to Hide explain while expanded.

- 2026-11-08 (Codex): Fixed demo verdict buttons being overwritten by the bank forecast. Explicit mock overrides bypass bank/cached answers and surface mock errors; bank/goal controls restore model mode. Mock results are labelled and displayed for every verdict. Regression checks pass.

- 2026-11-08 (Codex): Payment comparison now uses visible enabled checkout payment controls, follows the selected option, names the offered pay-in-3 provider, and shows repayment amounts and same-horizon minima outside Explain. Unsupported terms are not silently treated as pay-now. Selecting a payment in the demo leaves mock-override mode. Detector, adapter and model regression checks pass, including red-to-amber improvement and later-instalment overdraft cases.

- 2026-11-08 (Codex): Show current month-end cash balances in the upfront payment comparison, keeping the full-horizon minimum under Explain with its end date. Regression check confirms a £153.07 purchase paid in three leaves £102.05 more cash at the first month-end.
