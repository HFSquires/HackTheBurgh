# HackTheBurgh 2026

Code and records for the HackTheBurgh hackathon, started 7 November 2026. The topic had not been announced when this repository was set up. Current state: scaffold only, with no code yet.

`CLAUDE.md` (read by Claude Code) and `AGENTS.md` (read by Astra and other agents) are identical. Whoever edits one copies it over the other in the same commit. Every other folder in this repository that gets a `CLAUDE.md` gets an identical `AGENTS.md` beside it, and the reverse. Both files are self-contained, so do not rely on `@` imports or on instruction files in parent folders.

## Key files

| File | Purpose |
| --- | --- |
| `BRIEF.md` | The challenge: theme, rules, judging criteria, submission requirements, team. Fill this in as soon as the topic is announced |
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
5. Commit small, self-contained changes often. Commit code only after running or testing it. If code has to be committed untested, start the message with `Untested:`. End each commit message with a line naming the agent (for example `Agent: Astra`).
6. When a task runs, merge its branch into `main` (`git merge --no-ff tNN-short-name`) and remove the worktree. If the merge conflicts with another agent's work, stop and ask the user rather than resolving it by guesswork.
7. When you finish a task, set its status to `done` in `TASKS.md` and add a one-line dated entry to the `README.md` log naming the agent. Record any choice of scope, architecture or library in `DECISIONS.md`. Update `USER_GUIDE.md` if setup, commands or outputs changed.
8. Never commit secrets: API keys and tokens go in `.env`. Never push without the user's go-ahead. Write `unknown` for anything the brief or the user has not stated; do not invent requirements, rules or judging criteria. Ask the user instead.

## Design style

Everything that is shown (plots, slides, documents and any interface) uses Harrison's house style. Write in British English.

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
fig.savefig("figures/example.pdf")
fig.savefig("figures/example.svg")
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
| Export | PDF and SVG (the style outlines SVG text for Illustrator), saved to `figures/` |
| Statistics | Uncertainties as `(estimate ± SE)`; percentage changes as a rounded `(estimate ± SE)%` |

Every plot has a companion Markdown file with the same base name in the same folder (`figures/example.md`), written by the same script that makes the plot and regenerated with it. It contains: the plot title and filename; the source data; filters, transformations and units; the plotted data (a table, or summaries plus a link to the exact data file); `n` for every series; the descriptive statistics, with error bars defined; any fits or tests, with parameters, uncertainties, test statistics and p-values; random seeds; and a short factual interpretation. Write `not applicable` for categories that do not apply, and never include a statistic the code did not calculate. A plot is not finished until its companion file exists and has been checked against the data.

### Slides

The style is 16:9, CMU Serif, a cream background `#F7F1E6`, headings in red `#D50032` and black body text. Use a Morph transition (0.5 s) only when objects move. Claude uses the `texformat-powerpoint` skill.

### Interfaces and web pages

There is no established app style yet. Until the user decides otherwise, use the same palette: cream background `#F7F1E6`, black text, red `#D50032` headings and accents, DeepTeal `#005F73` as the base or link colour, the `tf.CYCLE` hex values for data series, and a serif face (CMU Serif or Computer Modern, falling back to a standard serif). Interactive charts follow the plot conventions above. If the brief or a sponsor requires its own branding, that takes precedence; record the choice in `DECISIONS.md`.

### Documents

LaTeX documents follow the house style in `~/.agents/skills/latex-house-style/references/style-guide.md`: author Harrison F. Squires, a month-year date, and "Experimental Brief" as the first section.

## Open items

The topic, rules, judging criteria, deadline and team are not yet known (see `BRIEF.md`). There is no GitHub remote yet. The web and interface palette above was extrapolated by an agent and has not yet been confirmed by the user.

## Log

- 2026-11-07 (Claude): Set up the repository: local git, `.gitignore`, and tracking files (`BRIEF.md`, `TASKS.md`, `DECISIONS.md`, `README.md`, `USER_GUIDE.md`), with `CLAUDE.md` and an identical `AGENTS.md` for Astra. Added the parallel-agent rules and the design style on the user's instruction. On the user's instruction, plots import the shared TeXFormat module from `03_code/TeXFormat` and load its master `TeXFormat.mplstyle`, without project copies. Test-rendered a plot from this folder with `py -3`: the shared module was imported (TeXFormat commit `556865b`), LaTeX rendered in Computer Modern, and PDF and SVG were written.
