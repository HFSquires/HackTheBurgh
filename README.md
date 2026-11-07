# HackTheBurgh 2026

Hackathon project, started 7 November 2026. The challenge is "Smart Cost of Living" (see `BRIEF.md`). Setup and usage are in `USER_GUIDE.md`. The rules for agents (Claude Code and Astra, working in parallel) and the design style are in `CLAUDE.md`, which is identical to `AGENTS.md`.

## Log

- 2026-11-07 (Claude): Set up the repository and its tracking files, with the parallel-agent rules and the design style. Plots import the shared TeXFormat module from `03_code/TeXFormat`; a test plot rendered correctly. No project code yet.
- 2026-11-07 (Claude): Restated Harrison's skills (`ponytail` and others, with paths for Astra) and the workspace file-organisation, environment and writing rules in `CLAUDE.md`/`AGENTS.md`.
- 2026-11-07 (Claude): Recorded the "Smart Cost of Living" challenge text in `BRIEF.md` and listed four candidate ideas as proposals; rules, judging criteria and deadline are still unknown.
- 2026-11-07 (Claude): Recorded Harrison's idea (affordability browser extension with an opt-in BNPL float) in `BRIEF.md` and `DECISIONS.md`, with an estimate of the interest the float earns (about £1 per £300 at an assumed 4% AER).
- 2026-11-07 (Claude): Linked Harrison's Notion page "hacktheburgh" (sponsor shortlist) from `CLAUDE.md`/`AGENTS.md` and `BRIEF.md`; corrected the sponsor to Bank of Scotland.
- 2026-11-07 (Claude): Reorganised the Notion page "hacktheburgh" on Harrison's instruction (shortlist, brief, idea, open questions, labelled agent estimates); it is re-read every 30 minutes while a Claude session runs (changed to every 5 minutes the same day, on Harrison's instruction).
- 2026-11-07 (Claude): Added the `notion-keeper` sub-agent (`.claude/agents/notion-keeper.md`), run every 5 minutes to check and organise the Notion page.
- 2026-11-07 (notion-keeper, Claude): Read the Notion page after Harrison added "Notes on spendings and investments" (BNPL source link, Zilch snooze fees, screenshot); page already organised, no edit made; noted in `BRIEF.md`.
- 2026-11-07 (Claude): Added the Haiku `notion-watch` change detector in front of `notion-keeper`, so the Sonnet agent runs only when the Notion page has changed.
- 2026-11-07 (notion-keeper, Claude): Read the Notion page after Harrison's further edits to "Notes on spendings and investments" (sentence on fixed late fees completed; 0% credit card or overdraft quotation added); page already organised, no edit made; `BRIEF.md` updated.
- 2026-11-07 (notion-keeper, Claude): On Harrison's instruction, marked the Notion open question on bank data for the demo as answered (bank API in the real product; CSV input for the hackathon demo) and recorded it in `BRIEF.md` and `DECISIONS.md`.
- 2026-11-07 (notion-keeper, Claude): On Harrison's instruction, added a "Demo data" subsection with his two CSV statements to the Notion page, the agent's demo-data proposals under Open questions and two notes under Notes from Claude; updated `BRIEF.md` and `DECISIONS.md`.
- 2026-11-07 (Claude): Checked Nemotron-Personas-UK's fields (no income field) and recorded it as the persona source; added T05 (mock statement generator).
- 2026-11-07 (notion-keeper, Claude): On Harrison's instruction, marked the demo-data proposals a to f accepted on the Notion page and moved "Notes from Claude" to the new child page "Claude's notes and sources" with a Sources section; `BRIEF.md` updated.
