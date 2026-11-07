# Decisions

Newest at the bottom. "By" is `user` (or a teammate's name) or `agent` (a proposal until the user confirms it).

| Date | Decision | By | Reason | Alternatives rejected |
| --- | --- | --- | --- | --- |
| 2026-11-07 | Track work in Markdown (`TASKS.md`, `DECISIONS.md`, `README.md` log) in a local git repository; one branch per task; tracking files edited only on `main` | user (setup request) | Lets several agents work in parallel without conflicting | none |
| 2026-11-07 | Claude Code and Astra work in parallel: `CLAUDE.md` and `AGENTS.md` are kept identical; the main checkout stays on `main`; each task runs on its own branch in its own worktree | user | Astra reads `AGENTS.md`; separate worktrees stop the agents overwriting each other | none |
| 2026-11-07 | All plots use the TeXFormat house style, with a companion statistics Markdown file per plot; slides, documents and interfaces use the house palette | user (interface palette extrapolated by agent, unconfirmed) | User instruction | none |
| 2026-11-07 | Plots import the shared TeXFormat module from `03_code/TeXFormat` (through `texformat.pth`) and load its master `TeXFormat.mplstyle` by path; no copies in this repository | user | One master copy, as in the rest of the workspace | Copying both files into the repository (briefly done, then reverted before commit) |
