# Tasks

Statuses: `todo`, `in progress`, `review`, `blocked`, `done`. Claim a task by setting its owner (`Claude`, `Astra`, `Harrison` or a teammate), its status and its branch before starting. Edit this file only on `main`.

| ID | Task | Owner | Status | Branch | Notes |
| --- | --- | --- | --- | --- | --- |
| T01 | Record the theme, rules, judging criteria and deadline in `BRIEF.md` | Harrison | in progress | main | Challenge text recorded by Claude, 7 November 2026; rules, judging criteria, deadline and team still unknown |
| T02 | Choose the idea and record the choice in `DECISIONS.md` | Harrison | in progress | main | Idea chosen 7 November 2026 (affordability extension with BNPL float); scope of the float feature to be confirmed |
| T03 | Choose the stack and set up the environment; write setup into `USER_GUIDE.md` | Claude | in progress | main | Back end: Python (see `DECISIONS.md`); front end: Auro's choice, not yet known |
| T04 | Break the idea down into implementation tasks on this board | unassigned | todo | main | Depends on T02 |
| T05 | Mock statement generator: pick personas from Nemotron-Personas-UK, give each a salary and category spending, write one statement CSV per persona | Claude | done | t05-mock-statements | Merged 7 November 2026 (`ff706cc`); self-check passes. Known issues carried to T05b |
| T05b | Mock data fixes: scale spending to income, at least two renters, Scottish income tax bands; keep ASHE 2025 revised | Claude | done | t05b-data-fixes | Merged 7 November 2026 (`871f568`); both self-checks pass. Open: 2026/27 Scottish bands; high median saving |
| T05c | Scale the generator to 100 UK personas from any region (one statement CSV each), using each persona's regional ONS spending | Claude | done | t05c-100-personas | Merged 7 November 2026 (`e48f822`); self-check passes; 6 of 100 end overdrawn, so T05b still relevant |
| T10 | Front end (extension interface) | Auro | in progress |  | Per Harrison, 7 November 2026; stack and branch not yet known to Claude |
| T07 | Back end: affordability engine and local HTTP API for the front end (income, committed outgoings, BNPL detection, safe-to-spend, payment options, sale-calendar note) | Claude | done | t07-backend | Merged 7 November 2026 (`842a6c8`); self-check passes on 100 statements |
| T07b | Analysis over the 100 personas: how many can afford test purchases now, only with the BNPL pot, or neither; house-style plot with companion statistics | unassigned | todo |  | Depends on T07 and T05b |
| T08 | Read the product price at checkout (schema.org product data, manual entry as fallback) | unassigned | todo |  | Front-end side; coordinate with Auro |
| T09 | Better price elsewhere: catalogue of real prices for a few demo products at several UK retailers | Claude | done | t09-price-catalogue | Merged 7 November 2026; `data/retail_prices_2026-11-07.csv` (5 products, 31 prices, mostly via PriceSpy UK) and a 3-month price history. Not yet linked into the back end (T09b) |
| T11 | Demo: test checkout page and scripted walkthrough with chosen personas | unassigned | todo |  | Depends on T07, T10 |
| T09b | Link the price catalogue into the back end: `betterPrice` and a price-history line in `saleNote` | unassigned | todo |  | Depends on T09; awaiting Harrison's choice of mainstream retailers only or all sellers |
