# Tasks

Statuses: `todo`, `in progress`, `review`, `blocked`, `done`. Claim a task by setting its owner (`Claude`, `Astra`, `Harrison` or a teammate), its status and its branch before starting. Edit this file only on `main`.

| ID | Task | Owner | Status | Branch | Notes |
| --- | --- | --- | --- | --- | --- |
| T01 | Record the theme, rules, judging criteria and deadline in `BRIEF.md` | Harrison | in progress | main | Challenge text recorded by Claude, 7 November 2026; rules, judging criteria, deadline and team still unknown |
| T02 | Choose the idea and record the choice in `DECISIONS.md` | Harrison | in progress | main | Idea chosen 7 November 2026 (affordability extension with BNPL float); scope of the float feature to be confirmed |
| T03 | Choose the stack and set up the environment; write setup into `USER_GUIDE.md` | unassigned | todo |  | Depends on T02 |
| T04 | Break the idea down into implementation tasks on this board | unassigned | todo | main | Depends on T02 |
| T05 | Mock statement generator: pick personas from Nemotron-Personas-UK, give each a salary and category spending, write one statement CSV per persona | Claude | done | t05-mock-statements | Merged 7 November 2026 (`ff706cc`); self-check passes. Known issues carried to T05b |
| T05b | Mock data fixes: scale spending to income, at least two renters, Scottish income tax bands; keep ASHE 2025 revised | unassigned | todo |  | Proposed by Claude; awaiting Harrison's go-ahead |
| T05c | Scale the generator to 100 UK personas from any region (one statement CSV each), using each persona's regional ONS spending | Claude | done | t05c-100-personas | Merged 7 November 2026 (`e48f822`); self-check passes; 6 of 100 end overdrawn, so T05b still relevant |
| T10 | Front end (extension interface) | Auro | in progress |  | Per Harrison, 7 November 2026; stack and branch not yet known to Claude |
