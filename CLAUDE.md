# HackTheBurgh 2026

Code and records for the HackTheBurgh hackathon, started 7 November 2026. The topic had not been announced when this repository was set up. Current state: challenge and idea recorded; no code yet.

`CLAUDE.md` (read by Claude Code) and `AGENTS.md` (read by Astra and other agents) are identical. Whoever edits one copies it over the other in the same commit. Every other folder in this repository that gets a `CLAUDE.md` gets an identical `AGENTS.md` beside it, and the reverse. Both files are self-contained: they restate the rules from Harrison's skills and from the PhD workspace `CLAUDE.md` (`C:\Users\s2191671\OneDrive - University of Edinburgh\PhD\CLAUDE.md`) that apply here, so do not rely on `@` imports or on instruction files in parent folders.

## Key files

| File | Purpose |
| --- | --- |
| `BRIEF.md` | The challenge: theme, rules, judging criteria, submission requirements, team. Fill this in as soon as the topic is announced |
| Notion page "hacktheburgh" (https://app.notion.com/p/hacktheburgh-411b2fb4d76580188ba4e5d313f4861a) | Harrison's own notes on the sponsor challenges. Harrison edits it; it is authoritative for his shortlist. Agents with Notion access re-read it at the start of each session and before editing `BRIEF.md`, and carry any changes into `BRIEF.md` with the date read. Agents without Notion access ask Harrison whether it has changed. Do not edit the Notion page unless asked; when asked, keep Harrison's wording and label agent material as such. During a Claude session a recurring 5-minute job first runs the cheap `notion-watch` sub-agent (Haiku; `.claude/agents/notion-watch.md`), which only compares the page's edit time with the one in `BRIEF.md`; only if it has changed does it run the `notion-keeper` sub-agent (Sonnet; `.claude/agents/notion-keeper.md`, which holds the full procedure), which, on the user's instruction, keeps it organised by moving new material into the right section, never deleting anything Harrison wrote |
| `TASKS.md` | Task board. Agents claim tasks here before starting |
| `DECISIONS.md` | Log of design and scope decisions, who made each one and why |
| `README.md` | What the project is, plus the dated work log |
| `USER_GUIDE.md` | Setup, how to run it, inputs, outputs, limitations. Write it from the code as it exists |
| `.env.example` | Names of required environment variables (create it when the first one is needed); real values go in `.env`, which is gitignored |

## Parallel agents

Several agents work in this repository at once: Claude Code (and any sub-agents it starts), Astra, and the user, Harrison. Each one is identified by name in the Owner column of `TASKS.md` (`Claude`, `Astra`, `Harrison`, or a teammate's name).

1. Before starting, read this file, `BRIEF.md`, `TASKS.md`, the last few entries of `DECISIONS.md` and the log in `README.md`.
2. Claim a task in `TASKS.md` before working on it: set the owner, change the status to `in progress`, add the branch name, and commit immediately. Do not take a task someone else has claimed. If what you need is not on the board, add it as a new task first.
3. The main checkout always stays on `main`; nobody checks out a task branch there. Do each task on its own branch, `tNN-short-name`, in its own worktree: `git worktree add .worktrees/tNN-short-name -b tNN-short-name main`. Claude sub-agents may use `isolation: "worktree"` instead, which places worktrees under `.claude/worktrees/`. Both locations are gitignored.
4. Edit the tracking files (`TASKS.md`, `DECISIONS.md`, the `README.md` log, `BRIEF.md`, `USER_GUIDE.md`, `CLAUDE.md`/`AGENTS.md`) only on `main`, in the main checkout, never on a task branch. Immediately before editing, re-read the file. Change only your own rows or append new ones, then commit at once, so that two agents never hold uncommitted edits to the same file.
5. Commit small, self-contained changes often, and commit your own completed changes at the end of every task so that nothing is left uncommitted. Commit uncommitted changes you did not make only after asking the user. Commit code only after running or testing it. If code has to be committed untested, start the message with `Untested:`. End each commit message with a line naming the agent (for example `Agent: Astra`).
6. When a task runs, merge its branch into `main` (`git merge --no-ff tNN-short-name`) and remove the worktree. If the merge conflicts with another agent's work, stop and ask the user rather than resolving it by guesswork.
7. When you finish a task, set its status to `done` in `TASKS.md` and add a one-line dated entry to the `README.md` log naming the agent. Record any choice of scope, architecture or library in `DECISIONS.md`. Update `USER_GUIDE.md` if setup, commands or outputs changed.
8. Never commit secrets: API keys and tokens go in `.env`. Pushing needs the user's go-ahead each time, but must not be left undone: before finishing a task that leaves unpushed commits, ask the user whether to push. Never force-push.

## Skills

Harrison's skills apply in this repository. Claude invokes them with the Skill tool. Astra and other agents read the skill file before doing the corresponding work. The essentials are restated in the sections below.

| Skill | Use whenever | File |
| --- | --- | --- |
| `ponytail` | Writing, modifying, refactoring, reviewing or debugging any code | `C:\Users\s2191671\.agents\skills\ponytail\SKILL.md` |
| `plot-companion-stats` | Creating or materially changing runnable code, plots or statistical figures | `C:\Users\s2191671\.agents\skills\plot-companion-stats\SKILL.md` |
| `latex-house-style` | Writing any LaTeX document | `C:\Users\s2191671\.agents\skills\latex-house-style\SKILL.md` |
| `texformat-powerpoint` | Making or editing slides | `C:\Users\s2191671\.claude\skills\texformat-powerpoint\SKILL.md` |
| `phd-onedrive` | Resolving any PhD path | `C:\Users\s2191671\.agents\skills\phd-onedrive\SKILL.md` |

## Coding discipline (`ponytail`)

Be a lazy senior developer: lazy means efficient, not careless, and the best code is the code never written. First understand the problem: read the task and the code it touches, and trace the real flow end to end. Then, before writing any code, stop at the first of these that holds:

1. Does it need to be built at all?
2. Does it already exist in this repository? Reuse it.
3. Does the standard library do it?
4. Does a native platform feature cover it?
5. Does an already-installed dependency solve it?
6. Can it be one line?
7. Only then, write the minimum code that works.

Fix bugs at the root cause, not the symptom: search every caller of the function you touch, and fix the shared function once when that is the right level. Add no abstractions that were not requested, no avoidable dependencies and no boilerplate. Prefer deletion to addition, boring to clever, and the fewest files possible. The shortest working diff wins, but only once the problem is understood. Question complex requests ("Do you actually need X, or does Y cover it?"). When two standard approaches are the same size, pick the one that handles edge cases correctly. Mark a deliberate simplification with a known ceiling with a `ponytail:` comment naming the ceiling and the upgrade path. Never skimp on understanding the problem, input validation at trust boundaries, error handling that prevents data loss, security, accessibility, or anything explicitly requested. Non-trivial logic leaves behind one small runnable check that fails if the logic breaks (an assert-based self-check or one small test file), with no frameworks or fixtures. Trivial one-liners need no test.

## File organisation

| Location | Contents |
| --- | --- |
| Top level | The tracking records listed above, the dependency file, `.gitignore` and `.env.example`, and nothing else unless the chosen stack requires it |
| Code | Wherever the chosen stack expects it, in as few files as possible; record the layout in `DECISIONS.md` |
| `data/` | Raw inputs exactly as received, never edited. `data/README.md` records each file's source (URL or origin), licence and the date it was obtained |
| `Analysis/[<group>/]` | Derived tables and intermediate outputs, written by code |
| `Figures/[<group>/]` | Plots (PDF and SVG), each with its companion statistics `.md` |
| `Presentation/` | The demo deck, if there is one |

Create a folder only when it is first needed. Outputs are written into `Figures/` and `Analysis/` by code and are never moved by hand. New dated folders are named `YYYY-MM-DD_Name`.

Every folder an agent creates or modifies has a brief `README.md`, created if absent and updated in the same task: what the folder is, then a dated log. Record what was discussed with the user and anything strange (deviations, unknowns, user decisions) rather than routine detail. A sub-project large enough to need its own rules gets its own `CLAUDE.md` with an identical `AGENTS.md`.

The repository has exactly one `USER_GUIDE.md`, at the root, updated in the same change as any runnable code and written from the code as it actually exists. It covers purpose and expected result, requirements and setup, inputs (formats, units, required files), exact run commands, options and defaults, outputs and their locations, one minimal example where it helps, limitations, and troubleshooting. There are no per-script guides, and no plot statistics go in it.

Records are updated in the same task as the work. Dated entries state what was done, the evidence, and what remains unresolved; historical entries are kept, not rewritten. Keep source-backed facts, user decisions, assumptions and model outputs distinct. Write `unknown` for anything not stated, and never invent data, results, citations, requirements, rules or judging criteria: ask the user. Preserve originals and provenance, and do not change other people's or other agents' work outside your own task. Large data files and model weights are not committed: gitignore them, and record how to obtain them in `data/README.md` and `USER_GUIDE.md`.

## Environment

Windows 11, PowerShell, VS Code. This folder is inside OneDrive. Use `py -3`, not `python3`. Install without admin rights only, and use `uv --no-cache`. A project virtual environment, when needed, is `.venv` (Python 3.12, gitignored) and needs a `texformat.pth` (see Plots). Never write to `/Volumes/HFSPhD2026/PhD` unless the user names that exact location.

## Writing

Write in British English, formally and directly: no flattery, hype or emojis. In documents and reports, prefer prose and tables to bullet lists. Use `\boldsymbol` for vectors.

## Design style

Everything that is shown (plots, slides, documents and any interface) uses Harrison's house style.

### Plots

Every plot uses Matplotlib with the shared house module `TeXFormat.py` and its style `TeXFormat.mplstyle`, both in `C:\Users\s2191671\OneDrive - University of Edinburgh\PhD\03_code\TeXFormat` (the parent `03_code` folder; guide: `USER_GUIDE.md` there). Import the module from there, and load the master style file beside it by path:

```python
from pathlib import Path
import matplotlib.pyplot as plt
import TeXFormat as tf

plt.style.use(Path(tf.__file__).with_name("TeXFormat.mplstyle"))
fig, ax = plt.subplots()
tf.bar(ax, [0, 1], [3.0, 2.1], tf.UniBlue, width=0.4, yerr=[0.2, 0.1], capsize=3, label="Example")
ax.set_ylabel(r"Intensity [a.u.]")
ax.legend(frameon=True, fancybox=False, fontsize=tf.fontsizeSmall)
fig.savefig("Figures/example.pdf")
fig.savefig("Figures/example.svg")
```

`import TeXFormat` works through a `texformat.pth` file in the environment's `site-packages` that contains that folder's path. `py -3` already has one. For a new virtual environment, add one (PowerShell, with the environment active: `$site = python -c "import site; print(site.getsitepackages()[-1])"; Set-Content -Encoding utf8 (Join-Path $site 'texformat.pth') 'C:\Users\s2191671\OneDrive - University of Edinburgh\PhD\03_code\TeXFormat'`). Check with `python -c "import TeXFormat; print(TeXFormat.__file__)"`, which must print that folder's path. Never copy `TeXFormat.py` or `TeXFormat.mplstyle` into this repository, and do not edit them from here: style changes are made in the TeXFormat repository. The style renders text with real LaTeX, so a LaTeX installation must be on the PATH (MiKTeX on Harrison's PC).

The plot conventions are as follows:

| Convention | Rule |
| --- | --- |
| Text | Real LaTeX rendering (`text.usetex: True`) in Computer Modern, set by the style. Never fall back silently to another font: if LaTeX fails, stop and report it |
| Colours | Series take colours in the order of `tf.CYCLE`: UniBlue `#041E42`, UniRed `#D50032`, DeepTeal `#005F73`, OldRose `#B8858D`, Cerulean `#0091B5`, Burgundy `#A50034`, LightBlue `#8FAED0`, SoftPink `#FF9DB5`, UniYellow `#E0B400`, Jade `#487A7B`. Use `tf.CYCLE` in code and do not retype the order. Beyond six series, add markers or line styles (colours 7 to 9 are pale) |
| Bars | `tf.bar()`: a translucent fill with a solid outline in the same colour, and a gap between neighbouring bars. Never use `ax.bar(..., alpha=...)` |
| Legends | Square frames: `frameon=True, fancybox=False` |
| Axes | No grid lines. Units in square brackets, for example `Time [s]` |
| Font sizes | `tf.fontsize`, `tf.fontsizeSmall`, `tf.fontsizeTiny` |
| Export | PDF and SVG (the style outlines SVG text for Illustrator), saved to `Figures/[<group>/]` |
| Statistics | Uncertainties as `(estimate ± SE)`; percentage changes as a rounded `(estimate ± SE)%` |

Every plot has a companion Markdown file with the same base name in the same folder (`Figures/example.md`), written by the same script that makes the plot and regenerated with it. A plot shown without an image file gets a stable descriptive name and its `.md` in `Analysis/`. The companion file contains: the plot title and filename; the source data; filters, transformations and units; the plotted data (a table, or summaries plus a link to the exact data file); `n` for every series; the descriptive statistics, with error bars defined; any fits or tests, with parameters, uncertainties, test statistics and p-values; random seeds; and a short factual interpretation. Write `not applicable` for categories that do not apply, and never include a statistic the code did not calculate. A plot is not finished until its companion file exists and has been checked against the data.

### Slides

The style is 16:9, CMU Serif, a cream background `#F7F1E6`, headings in red `#D50032` and black body text. Use a Morph transition (0.5 s) only when objects move. Edit a separately named copy of an existing deck, keeping the user's geometry, notes and animations. Claude uses the `texformat-powerpoint` skill.

### Interfaces and web pages

There is no established app style yet. Until the user decides otherwise, use the same palette: cream background `#F7F1E6`, black text, red `#D50032` headings and accents, DeepTeal `#005F73` as the base or link colour, the `tf.CYCLE` hex values for data series, and a serif face (CMU Serif or Computer Modern, falling back to a standard serif). Interactive charts follow the plot conventions above. If the brief or a sponsor requires its own branding, that takes precedence; record the choice in `DECISIONS.md`.

### Documents

LaTeX documents follow the `latex-house-style` skill and its style guide (`C:\Users\s2191671\.agents\skills\latex-house-style\references\style-guide.md`): author Harrison F. Squires, a month-year date, and "Experimental Brief" as the first section. Build with `latexmk -pdf -interaction=nonstopmode -halt-on-error -outdir=build <file>.tex` and copy the PDF beside the source.

## Open items

The challenge is Bank of Scotland's "Smart Cost of Living"; the idea is an affordability browser extension with an opt-in buy-now-pay-later float, whose scope is still open (see `BRIEF.md`, `DECISIONS.md`). The rules, judging criteria, deadline and team are not yet known. There is no GitHub remote yet. The web and interface palette above was extrapolated by an agent and has not yet been confirmed by the user.

## Log

- 2026-11-07 (Claude): Set up the repository: local git, `.gitignore`, and tracking files (`BRIEF.md`, `TASKS.md`, `DECISIONS.md`, `README.md`, `USER_GUIDE.md`), with `CLAUDE.md` and an identical `AGENTS.md` for Astra. Added the parallel-agent rules and the design style on the user's instruction. On the user's instruction, plots import the shared TeXFormat module from `03_code/TeXFormat` and load its master `TeXFormat.mplstyle`, without project copies. Test-rendered a plot from this folder with `py -3`: the shared module was imported (TeXFormat commit `556865b`), LaTeX rendered in Computer Modern, and PDF and SVG were written.
- 2026-11-07 (Claude): On the user's instruction, added the Skills table (`ponytail`, `plot-companion-stats`, `latex-house-style`, `texformat-powerpoint`, `phd-onedrive`, with paths so that Astra can read them), restated the `ponytail` discipline, and added file organisation, environment and writing rules adapted from the PhD workspace `CLAUDE.md`. The figure folder is now `Figures/`, in line with the workspace convention.
- 2026-11-07 (Claude): On the user's instruction, added the Notion page "hacktheburgh" to the key files, to be re-read each session; recorded its challenge shortlist in `BRIEF.md`.
- 2026-11-07 (Claude): On the user's instruction, reorganised the Notion page "hacktheburgh" around the chosen idea and set a session-only job to re-read it every 30 minutes (changed to every 5 minutes on the user's instruction the same day).
- 2026-11-07 (Claude): With the user's agreement, moved the Notion check into a `notion-keeper` sub-agent (Sonnet), so that the 5-minute checks do not fill the main conversation; `.claude/agents/` is now tracked in git.
- 2026-11-07 (Claude): On the user's instruction, split the Notion check into a Haiku change detector (`notion-watch`) and the Sonnet `notion-keeper`, which now runs only when the page has changed; one Sonnet check had cost about 68,000 tokens. Both agents are limited to the tools they need.
