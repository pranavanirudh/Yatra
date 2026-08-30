# docs/

An index, with a status against each file. The status column is the point of
this page: several of these documents record decisions that were later revised,
and this project keeps superseded reasoning rather than deleting it — for the
same reason `experiments/configs/shocks.yaml` keeps its rejected windows. A
reader who cannot tell a live decision from a retired one gets the worst of that
policy instead of the best of it.

**Current** means it describes the project as it stands. **Superseded in part**
means a specific verdict in it was reversed, and the file names its successor.
**Historical record** means it is evidence of what was believed at a date, kept
deliberately, and is not to be read as current.

## The spec and the working agreement

| Doc | Status | What it is |
|---|---|---|
| [claude_code_brief.md](claude_code_brief.md) | current | The spec. Targets, hard constraints, the failure mode the design guards against. Read first. |
| [../CLAUDE.md](../CLAUDE.md) | current | The working agreement: what to run, where things live, and the settled decisions not to re-litigate. |

## Data and the calendar layer

| Doc | Status | What it is |
|---|---|---|
| [data_schema.md](data_schema.md) | current | The exact files and columns `contract.py` requires, and why `annual.csv` must be an independent published total rather than a sum of the monthly file. |
| [ephemeris.md](ephemeris.md) | current | Why the backend is declared in config and fails loudly, instead of being discovered by catching `ImportError`. |
| [citation_research.md](citation_research.md) | current | Candidate evidence for the declared shock windows — URLs opened and quoted, and the boundaries no reporting evidences. Explicitly **not** verification; it does not set `verified: true`. |

## Using the output

| Doc | Status | What it is |
|---|---|---|
| [operations.md](operations.md) | current | What the crowd-planning briefing can and cannot carry, and why it ships with no resourcing ratios. |
| [framing.md](framing.md) | current | How to present the finding — for talks, abstracts and viva-style questioning — without overstating it. |

## The second site

Read in this order. The criteria came first, the search second, and the decision
third; each narrowed the one before it.

| Doc | Status | What it is |
|---|---|---|
| [site2_criteria.md](site2_criteria.md) | current as to criteria; candidate table superseded | What a second site must provide (C1–C4) and what disqualifies one outright. The criteria still stand and are what later candidates were measured against. Its own candidate table is marked `[UNVERIFIED]` throughout and was written before any page was fetched, so read the two files below for the checked verdicts. Its Sabarimala disqualification is the exception: that one was structural rather than empirical, and it was confirmed rather than overturned. |
| [second_site.md](second_site.md) | superseded in part; otherwise a historical record | The search: five candidates, and why each was rejected. **Its Tirumala verdict is reversed** — see [site2_tirumala.md](site2_tirumala.md), which explains what changed (the question asked of a second site, not the answer about its shocks). Its Kedarnath, Sabarimala, Tamil Nadu and district-tourism sections stand. |
| [site2_tirumala.md](site2_tirumala.md) | current | The live second-site decision: measured archive depth, the pandemic start date, the measurement-window ambiguity, and why the recommendation is to request the figures rather than scrape them. |
| [data_request_tirumala.md](data_request_tirumala.md) | current, unsent | The drafted request to TTD. Placeholders in `[SQUARE BRACKETS]` must be filled before sending. |
| [data_request_kedarnath.md](data_request_kedarnath.md) | current, unsent | The drafted request for month-wise Kedarnath figures. Would settle availability; would not settle the seasonal-zero problem, which is a decision about the modelling frame. |

Nothing in this section has put a figure into `data/raw/`. No second site has
been collected, and none may be until a citable source is in hand.
