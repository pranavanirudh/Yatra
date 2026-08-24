# How to present this

Written for the owner, for talks, abstracts and viva-style questioning.

**No figures are typed into this file.** Every number this project has lives in
the generated block of the README, where a row produced it. Quoting one here
would create a second copy that drifts the first time the pipeline re-runs and
nobody re-reads this file. Where a number is needed, take it from the generated
section at the moment of writing, and take it from there again next time.

---

## 1. The claim, in one sentence

> Choosing a forecasting model by its average error recommends the model that
> fails exactly when a forecast would have mattered.

That is the contribution. Everything else in the repository is the apparatus
that makes it checkable.

## 2. Lead with the method, not the shrine

The instinct is to open with the site — a famous shrine, four decades of data, a
landslide, a pandemic. Resist it. If the first sentence is about a temple, the
first question is *"why do I care about one temple?"*, and the honest answer to
that question is not flattering, because the site-specific results are ordinary.

If the first sentence is about **model selection**, the shrine becomes the
evidence rather than the subject, and the fact that it is one site becomes a
stated limit rather than the whole frame.

| Say | Not |
|---|---|
| "Regime-separated evaluation reveals rank inversions a pooled leaderboard hides." | "I built a forecasting model for Vaishno Devi." |
| "The apparatus is a rolling-origin backtest with one shared denominator." | "I compared nine models and SARIMAX won." |
| "Tested on four decades of pilgrimage footfall containing four differently-shaped disruptions." | "This is a case study of a temple." |

The second column is not wrong. It is just a description of work rather than a
description of a finding, and it invites accuracy questions the numbers cannot
win — the headline error figure is unremarkable, and it is not the point.

## 3. Draft abstract

> Forecasting models are conventionally selected by average error over a holdout
> period. This paper asks whether that selection survives being split by regime.
>
> Using four decades of monthly pilgrimage footfall from a single site, with
> disruptions declared from cited sources and applied only as evaluation labels,
> we score nine forecasting methods on an identical set of rolling origins
> against a single shared denominator. Rankings on ordinary months and on
> disrupted months are compared directly.
>
> The rankings invert. The method with the lowest error on ordinary months falls
> to mid-table during disruptions, and the method that wins during disruptions is
> among the worst on ordinary months. Block-bootstrap resampling of the origin
> set finds the inversion in the large majority of resamples, and it holds at
> every forecast horizon and under an alternative set of disruption boundaries.
>
> Unpooling the disrupted months further shows that "disrupted" is not one
> regime: the winning method differs across the declared windows. That
> comparison rests on a single non-pandemic disruption and cannot separate a
> type effect from one unusual window, which is stated rather than resolved.
>
> The practical implication is that a single averaged leaderboard is not merely
> imprecise but actively misleading for planning, since it recommends the method
> that fails when a forecast is most consequential.

Fill the qualitative phrases with figures from the generated README block when
submitting. Do not write them into this file.

## 4. Questions you should expect, with honest answers

**"Isn't regime-dependent performance already known?"**
Yes, and say so first. Structural breaks and forecasting under instability are
established. What is offered here is not the existence of the effect but a
falsifiable measurement of it: one origin set, one denominator computed per
origin so no model can be flattered by its own scale, labels that never reach a
fit call, and a declared ablation set. The contribution is the apparatus and the
per-window decomposition, not the discovery that regimes matter.

**"Your model is barely better than a seasonal baseline."**
Correct, and it is in the report. The forecast accuracy is not the claim. The
claim is about how models are *chosen*; a mediocre model is perfectly adequate
evidence for a claim about selection procedure, because the inversion is between
rankings and not about any one method being good.

**"Isn't the shock window definition doing the work?"**
That is the right objection and it is pre-empted. The same forecasts are
re-scored under an alternative boundary set; the inversion survives. The
rejected candidate windows are kept in the config with reasons, including one
fatal incident deliberately *not* declared because the monthly series shows no
disruption — severity of an event and disruption of a monthly total are
different quantities.

**"How do you know the models never saw the labels?"**
Structurally, not by assertion. The backtest has no code path passing the regime
frame into a fit call, a test asserts the model modules do not import the
regimes module at all, and the switching model's break detector raises if it
returns a position at or past the forecast origin.

**"Does it generalise?"**
No, and nothing here claims it does. One site. Say this before being asked.

## 5. The two weak points — name them first

Both are easy to find. Raising them yourself reads as rigour; having them raised
for you reads as an oversight.

**The non-pandemic evidence is a single window.** Four of the five declared
windows are subdivisions of one event, so every contrast between pandemic and
non-pandemic disruption is that one window compared repeatedly. The heatmap
renders it as a clean block, and the cleanliness comes from having one window on
one side rather than from the strength of the evidence. Nothing separates
"disruption type matters" from "that window has an unusual winner".

**One window's boundaries are not anchored to anything announced.** Every other
declared window sits against a published event — a suspension, a reopening, a
capacity order, a landslide. The delta-wave window is drawn from the shape of
the series alone, which is a weaker kind of declaration and carries the specific
risk of putting a boundary where the model would most like it.

Both are recorded in the repository already. The second is in
[citation_research.md](citation_research.md), which also records that one
recovery window's start date turns out to be anchored to a published capacity
order after all.

## 6. What not to claim

- Not that any of it transfers to another shrine, state or district.
- Not that `naive` is the model to use in a crisis. It wins the pandemic
  windows; on the one non-pandemic disruption in the record it does not.
- Not that the calendar features are established as harmful during shocks. That
  sign flip is one pair of models on a thin slice, is not resolved by the
  bootstrap, and the report says so.
- Not that the system can size a single day. It is monthly, and the events most
  likely to kill someone are invisible at monthly resolution — which is
  precisely why one fatal incident is a rejected window rather than a declared
  one.

## 7. If asked what would come next

A second site whose disruptions are **not** the pandemic. That is the binding
constraint, not more months and not more models.
[second_site.md](second_site.md) records the search, four rejected candidates
and one open, and [data_request_kedarnath.md](data_request_kedarnath.md) is the
request that would settle whether the open one is usable.

Say the constraint is data availability rather than method: monthly footfall for
Indian pilgrimage sites is largely unpublished, and the one site with four
decades of month-wise figures is the one already in the study.
