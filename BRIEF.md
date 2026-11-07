# Brief

Fill this in when the challenge is announced. Keep `unknown` wherever the organisers have not said. Harrison's own shortlist of sponsor challenges is kept in the Notion page "hacktheburgh" (https://app.notion.com/p/hacktheburgh-411b2fb4d76580188ba4e5d313f4861a); re-read it before updating this file. Last read: 7 November 2026 14:02 UTC, page last edited 2026-11-07T13:58:10.523Z (Harrison's further edits to the section "Notes on spendings and investments"; the notion-keeper made no edit to the page).

| Item | Detail |
| --- | --- |
| Event | HackTheBurgh 2026 |
| Dates and hacking window | unknown (repository set up 7 November 2026) |
| Final submission deadline | unknown |
| Theme or tracks | Sponsor challenges, as shortlisted in Harrison's Notion page "hacktheburgh" (read 7 November 2026): ruled out Instanlily (spelling as written; unclear), JetBrains, Viridien; broad HRT (making decisions based on data), G-Research (making hidden data visible), Wordsmith (end-to-end browser based); narrow Bank of Scotland. Official track list and wording unknown |
| Track or challenge chosen | "Smart Cost of Living: Build boldly. Solve something real." (challenge slide supplied by Harrison, 7 November 2026) |
| Team | Harrison F. Squires; others unknown |
| Team size limit | unknown |
| Rules on pre-written code and libraries | unknown |
| Rules on AI tools | unknown |
| Judging criteria | unknown |
| Submission platform and format (repo, video, demo, slides) | unknown |
| Sponsor APIs, datasets or prizes worth targeting | The challenge belongs to Bank of Scotland (Harrison's Notion page lists it as the narrow track; the black horse on the slide is the Lloyds Banking Group mark, and Bank of Scotland is part of that group). An earlier agent guess of Lloyds alone is superseded. Whether the browser extension could also be entered for Wordsmith (end-to-end browser based) or HRT (decisions based on data) depends on the rules on multiple entries, which are unknown. No APIs or data are mentioned on the slide |

## Problem statement

Verbatim from the challenge slide (supplied by Harrison, 7 November 2026):

> Everyday financial decisions involve trade-offs. The cheapest option might take longer, the most convenient might cost more, and the most sustainable choice may not always be the easiest.
>
> **Your challenge:** create a solution that helps customers navigate these trade-offs and make better decisions around their money and everyday lives.
>
> How you approach this is up to you. You could experiment with AI, optimisation, behavioural nudges, personalised recommendations, challenges or rewards, gamification, data visualisation, or something completely different.
>
> Think creatively about what "better" means. Could your solution help someone spend less, save towards a goal, make more sustainable choices, free up time, or find the right balance between several priorities?

## Ideas considered

Proposed by Claude, 7 November 2026; verdicts are Harrison's to make.

| Idea | For | Against | Verdict |
| --- | --- | --- | --- |
| Trade-off navigator: for one everyday decision, list the options scored on cost, time and carbon, show the Pareto front, and let the user weight their priorities with sliders to get a recommendation | Mirrors the brief's wording almost exactly; one strong visual; optimisation done honestly; works on hand-entered or synthetic data | Needs believable option data for each decision type; risks looking like a calculator unless the demo story is good | open |
| Goal-cost lens on spending: from a (synthetic) transaction history, translate each recurring spend into days of delay to a savings goal, and suggest swaps with their money, time and carbon effect | Bank-native (transactions are what the sponsor holds); behavioural nudge; personal | Categorising transactions well takes time; synthetic data must be credible | open |
| Affordability extension with BNPL float (Harrison, 7 November 2026): a browser extension, connected to the bank and to monthly income, that detects the product being bought and shows live whether it is affordable. As a separate opt-in, when a buy-now-pay-later plan is used, the full price is moved into a cash or investment ISA and each instalment is paid from it automatically, so the money earns interest in the meantime; the extension tracks all of this. Must be easy to integrate and secure | Live affordability check at the point of purchase is concrete, bank-native and demo-able; the opt-in pot guarantees the instalments are covered | Agent estimate: interest on the float is about £1 per £300 purchase at an assumed 4% AER (pay in 3 or pay in 30 days; £0.69 for pay in 4), so it is not the selling point. Investing for two months risks a loss with probability about 0.43 (assumed 0.6% mean, 4.5% s.d. monthly equity return), which could leave instalments short. Promoting BNPL may sit badly with a bank sponsor judging financial wellbeing. Real bank access and money movement need regulated Open Banking providers, so the hackathon version must use sandbox or synthetic data. Harrison's notes (Notion, 7 November 2026) cite MoneySavingExpert's guide to BNPL tools and a Zilch snooze fee (75p per instalment snoozed 4 days, £1.50 for 8, as quoted by Harrison from that source), observing that fixed late fees not scaling with the debt may make investing the money a better financial decision than repaying the debt, and quoting MoneySavingExpert that a 0% credit card or overdraft might be a better way to borrow; a screenshot is also on the page and not read here | chosen by Harrison; scope of the float feature open |
| Weekly shop optimiser: choose shops and products to meet a list, trading price against travel time and carbon | Concrete and relatable | Live supermarket prices are hard to obtain legitimately; scraping may break rules | open |
| Commute and travel planner for Edinburgh: bus, train, bike, car and taxi compared on fare, time and carbon | Easy local demo | Crowded space; less connected to banking | open |

## Submission checklist

Requirements will be added once known. A typical set is: code pushed to the required repository, `USER_GUIDE.md` lets a judge run it, demo recorded or rehearsed, submission form completed before the deadline.
