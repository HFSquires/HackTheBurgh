# Brief

Fill this in when the challenge is announced. Keep `unknown` wherever the organisers have not said.

| Item | Detail |
| --- | --- |
| Event | HackTheBurgh 2026 |
| Dates and hacking window | unknown (repository set up 7 November 2026) |
| Final submission deadline | unknown |
| Theme or tracks | unknown beyond the challenge below |
| Track or challenge chosen | "Smart Cost of Living: Build boldly. Solve something real." (challenge slide supplied by Harrison, 7 November 2026) |
| Team | Harrison F. Squires; others unknown |
| Team size limit | unknown |
| Rules on pre-written code and libraries | unknown |
| Rules on AI tools | unknown |
| Judging criteria | unknown |
| Submission platform and format (repo, video, demo, slides) | unknown |
| Sponsor APIs, datasets or prizes worth targeting | unknown. The slide's card artwork carries a black horse, which suggests Lloyds Banking Group as the sponsor (agent inference from the artwork, unconfirmed); no APIs or data are mentioned on the slide |

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
| Weekly shop optimiser: choose shops and products to meet a list, trading price against travel time and carbon | Concrete and relatable | Live supermarket prices are hard to obtain legitimately; scraping may break rules | open |
| Commute and travel planner for Edinburgh: bus, train, bike, car and taxi compared on fare, time and carbon | Easy local demo | Crowded space; less connected to banking | open |

## Submission checklist

Requirements will be added once known. A typical set is: code pushed to the required repository, `USER_GUIDE.md` lets a judge run it, demo recorded or rehearsed, submission form completed before the deadline.
