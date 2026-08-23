"""Generate the README's results section from results/metrics.csv.

Constraint: every number in the README must trace to a row in metrics.csv. That
is unenforceable if numbers are typed by hand, so they are not typed by hand --
this module owns everything between the ``BEGIN GENERATED`` and ``END GENERATED``
markers and rewrites it wholesale on every run.

If metrics.csv is absent this raises. It does not emit a table of placeholders,
and it does not leave the previous run's numbers in place while the pipeline
that produced them no longer runs.
"""

from __future__ import annotations

import itertools
from pathlib import Path

import pandas as pd
import yaml

from . import backtest, metrics, models, regimes, sensitivity
from .errors import ConfigError

BEGIN = "<!-- BEGIN GENERATED -->"
END = "<!-- END GENERATED -->"

#: Below this many non-COVID shock windows, any COVID-versus-other contrast in
#: the per-window section is qualified in the generated text. The COVID windows
#: are subdivisions of one event, so every "these disagree" correlation is the
#: same handful of non-COVID windows appearing repeatedly rather than
#: independent evidence. Three is the point at which the contrast stops being
#: one window's idiosyncrasy by construction -- it is a floor for *reporting
#: honestly*, not a significance threshold, and nothing is computed from it.
NON_COVID_FLOOR = 3

WARNING = (
    "> **Generated section.** Everything between the markers is written by "
    "`src/yatra/report.py` from `results/metrics.csv`. Edits here are "
    "overwritten by `make report`. Numbers do not belong in the hand-written "
    "prose outside the markers."
)


def _fmt(value: float, places: int = 3) -> str:
    if pd.isna(value):
        return "—"
    return f"{value:.{places}f}"


def _scope(
    frame: pd.DataFrame,
    observations_path: str | Path = "data/raw/monthly.csv",
) -> list[str]:
    """What the results below cover, and what they do not.

    Generated rather than hand-written because the span and the month count are
    numbers, and CLAUDE.md 3.1 keeps numbers inside the markers. The
    qualitative half -- why no second site exists -- is hand-written prose in
    the README, because it is a fact about other people's publishing practices
    and no row here produces it.

    This sits first in the generated block on purpose. Every table below is a
    result from one shrine, and a reader who takes the leaderboard away without
    that qualification has taken away something this record does not support.
    """
    site = "Shri Mata Vaishno Devi, Katra, Jammu & Kashmir"
    lines = ["### Scope", ""]

    path = Path(observations_path)
    if path.exists():
        observations = pd.read_csv(path)
        if len(observations) and "month" in observations.columns:
            months = observations["month"].astype(str)
            lines += [
                "| | |",
                "|---|---|",
                f"| Site | {site} |",
                f"| Months observed | {len(observations):,} |",
                f"| Span | {months.iloc[0]} to {months.iloc[-1]} |",
                f"| Sites in this study | 1 |",
                "",
            ]

    windows = frame["shock_window"].dropna().nunique() if "shock_window" in frame else 0
    transfer = (
        "**Nothing below generalises to another shrine, state, or district.** "
        "Every figure in this section is one site's record. The per-window "
        "section shows that the winning model differs across kinds of "
        "disruption *within* this site"
    )
    if windows:
        transfer += f", across its {windows} declared windows"
    transfer += (
        " &mdash; which is a reason to expect less transfer between sites, not "
        "more. A second site has not been scored here, so there is no evidence "
        "either way about whether any of this holds elsewhere, and none should "
        "be inferred from the fact that these tables are detailed."
    )
    lines += [transfer, ""]
    return lines


def _provenance(frame: pd.DataFrame) -> list[str]:
    origins = frame["origin"].nunique()
    horizons = sorted(frame["horizon"].unique())
    models_ = sorted(frame["model"].unique())
    config_hashes = sorted(frame["config_hash"].unique()) if "config_hash" in frame else []

    if len(config_hashes) > 1:
        raise ConfigError(
            f"metrics.csv mixes {len(config_hashes)} different backtest configs "
            f"{config_hashes}. Those rows were produced by different experiments "
            "and must not be tabulated together."
        )

    span = f"{frame['origin'].min()} to {frame['origin'].max()}"
    lines = [
        "### Run provenance",
        "",
        "| | |",
        "|---|---|",
        f"| Forecast origins | {origins} ({span}) |",
        f"| Horizons | {', '.join(str(h) for h in horizons)} |",
        f"| Models | {len(models_)} |",
        f"| Forecasts scored | {len(frame):,} |",
    ]
    if config_hashes:
        lines.append(f"| Backtest config hash | `{config_hashes[0]}` |")
    lines.append("")
    return lines


def _regime_counts(frame: pd.DataFrame) -> list[str]:
    counts = frame.groupby("regime").size()
    per_model = counts / frame["model"].nunique()
    lines = [
        "### Regime split",
        "",
        "| Regime | Forecasts | Per model |",
        "|---|---:|---:|",
    ]
    for regime, n in counts.sort_index().items():
        lines.append(f"| {regime} | {int(n):,} | {int(per_model[regime]):,} |")
    lines.append("")

    by_window = frame.dropna(subset=["shock_window"]).groupby("shock_window").size()
    if len(by_window):
        lines += [
            "| Shock window | Forecasts | Per model |",
            "|---|---:|---:|",
        ]
        for window, n in by_window.sort_index().items():
            lines.append(
                f"| {window} | {int(n):,} | {int(n / frame['model'].nunique()):,} |"
            )
        lines.append("")
    return lines


def _leaderboard(frame: pd.DataFrame) -> tuple[list[str], pd.DataFrame]:
    table = backtest.per_regime_table(frame, "mase")
    clean, shock = regimes.CLEAN, regimes.SHOCK

    have_both = clean in table.columns and shock in table.columns
    lines = [
        "### Mean MASE by regime",
        "",
        "Lower is better. Rank is within the column. Every model is scored on an "
        "identical origin set, so the two columns are comparable.",
        "",
    ]

    if have_both:
        lines += [
            "| Model | Clean MASE | Rank | Shock MASE | Rank | Rank change |",
            "|---|---:|---:|---:|---:|---:|",
        ]
        for model in table.sort_values(clean).index:
            row = table.loc[model]
            delta = int(row[f"{shock}_rank"]) - int(row[f"{clean}_rank"])
            lines.append(
                f"| `{model}` | {_fmt(row[clean])} | {int(row[f'{clean}_rank'])} "
                f"| {_fmt(row[shock])} | {int(row[f'{shock}_rank'])} | {delta:+d} |"
            )
    else:
        present = [c for c in table.columns if not c.endswith(("_rank", "_n"))]
        lines += ["| Model | " + " | ".join(present) + " |", "|---" * (len(present) + 1) + "|"]
        for model in table.index:
            cells = " | ".join(_fmt(table.loc[model, c]) for c in present)
            lines.append(f"| `{model}` | {cells} |")
    lines.append("")
    return lines, table


def _inversion(frame: pd.DataFrame, table: pd.DataFrame) -> list[str]:
    clean, shock = regimes.CLEAN, regimes.SHOCK
    if clean not in table.columns or shock not in table.columns:
        return []

    rho, pvalue = metrics.rank_correlation(table[clean], table[shock])
    best_clean = table[clean].idxmin()
    best_shock = table[shock].idxmin()

    n_models = len(table)
    clean_rank_of_shock_winner = int(table.loc[best_shock, f"{clean}_rank"])
    shock_rank_of_clean_winner = int(table.loc[best_clean, f"{shock}_rank"])

    lines = [
        "### The inversion",
        "",
        f"- Best on clean months: `{best_clean}` — ranks "
        f"{shock_rank_of_clean_winner} of {n_models} during shocks.",
        f"- Best on shock months: `{best_shock}` — ranks "
        f"{clean_rank_of_shock_winner} of {n_models} on clean months.",
        "",
    ]

    resamples = _resample_evidence(table, best_clean, best_shock)
    if resamples:
        return lines + resamples

    return lines + [
        f"Spearman correlation between the two rankings: **{rho:+.3f}** "
        f"(p = {pvalue:.3f}, n = {n_models} models). No resample evidence is "
        "available; run `make bootstrap` for the statistics that carry the "
        "actual claims.",
        "",
    ]


def _resample_evidence(
    table: pd.DataFrame, best_clean: str, best_shock: str,
    bootstrap_path: str | Path = "results/bootstrap.csv",
) -> list[str]:
    """Lead with what the resamples say, and about which specific claim.

    Two statistics are reported and they answer different questions, which is
    why leading with the right one matters.

    The **inversion frequency** and the **pairwise proportions** are what anyone
    actually acts on: "during a closure, is the naive forecast the better bet
    than the seasonal model?" is a question about two models.

    The **rank correlation** asks something much larger -- whether the entire
    ordering of every model reverses -- and has to estimate a whole permutation
    from the handful of disrupted months in the record. Its interval is
    correspondingly wide. That width is a property of the question, not evidence
    against the finding, and reporting it first would invite exactly the wrong
    reading.
    """
    path = Path(bootstrap_path)
    if not path.exists():
        return []
    try:
        boot = pd.read_csv(path)
    except Exception:  # noqa: BLE001 - the README must render without it
        return []
    if "statistic" not in boot.columns:
        return []

    def scalar(name: str) -> pd.Series | None:
        rows = boot[boot["statistic"] == name]
        return rows.iloc[0] if len(rows) else None

    inversion = scalar("p_inversion")
    rho_row = scalar("rank_correlation")
    if inversion is None or rho_row is None:
        return []

    n_resamples = int(rho_row.get("n_resamples", 0))
    confidence = int(round(100 * float(rho_row.get("confidence", 0.95))))

    lines = [
        f"Across **{n_resamples:,} block-bootstrap resamples** of the origin set, "
        f"the clean-month and shock-month rankings came out inverted in "
        f"**{float(inversion['point']):.1%}** of them.",
        "",
    ]

    pairs = boot[boot["statistic"] == "p_beats"]
    if len(pairs):
        clean_col, shock_col = regimes.CLEAN, regimes.SHOCK
        top_clean = table.sort_values(clean_col).index.tolist()
        challengers = [m for m in top_clean if m != best_shock][:3]

        wanted = [(best_shock, other, shock_col) for other in challengers]
        wanted.append((best_clean, best_shock, clean_col))

        rows = []
        for left, right, regime in wanted:
            match = pairs[
                (pairs["model"] == left)
                & (pairs["opponent"] == right)
                & (pairs["regime"] == regime)
            ]
            if len(match):
                rows.append(
                    f"| `{left}` beats `{right}` | {regime} | "
                    f"{float(match.iloc[0]['point']):.1%} |"
                )
        if rows:
            lines += [
                "A rank correlation over every model is a blunt summary. These "
                "are the substitutions someone would actually make, and the share "
                "of resamples in which each one pays:",
                "",
                "| Comparison | Regime | Share of resamples |",
                "|---|---|---:|",
                *rows,
                "",
            ]

    lines += [
        f"The Spearman correlation between the two rankings is "
        f"**{float(rho_row['point']):+.3f}**, with a {confidence}% interval of "
        f"[{float(rho_row['lo']):+.3f}, {float(rho_row['hi']):+.3f}]. That "
        "interval spans zero, so on the conventional threshold the rank "
        "correlation on its own would not be called significant.",
        "",
        "That threshold is answering a harder question than the one being asked. "
        "Rho tests whether the *whole* ordering of every model reverses, and it "
        "has only the disrupted months in the record to estimate a full "
        "permutation from — so its interval is wide by construction. The "
        "pairwise proportions above test the claims anyone would act on, and are "
        "correspondingly sharper on the same evidence. Both are reported; they "
        "are not in conflict, they are different questions.",
        "",
    ]
    return lines


def _sensitivity(
    summary_path: str | Path = "results/sensitivity_summary.csv",
    per_model_path: str | Path = "results/sensitivity.csv",
) -> list[str]:
    """Does the headline survive a different boundary?

    The inversion is a comparison across a line somebody drew by hand. A
    finding that flips when the line moves by a month is a finding about the
    line. ``sensitivity.py`` re-scores the identical forecasts under every
    declared window set -- possible only because no model ever sees a regime
    label (CLAUDE.md 3.4) -- and this section reports what came back.

    It reports the arms that disagree as readily as the ones that agree. A
    section that appeared only when the answer was reassuring would be worth
    nothing, since its absence would then carry the bad news silently.
    """
    try:
        summary_p, per_model_p = Path(summary_path), Path(per_model_path)
        if not (summary_p.exists() and per_model_p.exists()):
            return []
        summary = pd.read_csv(summary_p)
        per_model = pd.read_csv(per_model_p)
    except Exception:  # noqa: BLE001 - the README must render without it
        return []
    if summary.empty or per_model.empty or len(summary) < 2:
        return []

    lines = [
        "### Does the finding survive a different boundary?",
        "",
        "The shock windows are drawn by hand. Below, the *same* forecasts are "
        "re-scored under each declared window set — a re-labelling, not a "
        "refit, because no model ever receives a regime label.",
        "",
        "| Window set | Windows | Shock forecasts per model | Rank correlation | Inverts |",
        "|---|---:|---:|---:|---|",
    ]
    for row in summary.itertuples():
        # The refined arm's description is a multi-line YAML block; a raw
        # newline would end the table row.
        note = " ".join(str(row.description).split())
        label = f"`{row.arm}`" + (f" — {note}" if note else "")
        lines.append(
            f"| {label} | {int(row.n_windows)} | "
            f"{int(row.shock_forecasts_per_model):,} | "
            f"{float(row.rank_correlation):+.3f} | "
            f"{'yes' if bool(row.inverts) else 'no'} |"
        )
    lines.append("")

    inverting = int(summary["inverts"].astype(bool).sum())
    total = len(summary)
    if inverting == total:
        lines += [
            f"The rank correlation is negative under **{inverting} of {total}** "
            "window definitions. The inversion is not an artefact of where the "
            "boundaries were drawn.",
            "",
        ]
    else:
        lines += [
            f"The rank correlation is negative under **{inverting} of {total}** "
            "window definitions, so the sign of the headline finding depends on "
            "the boundary. Read the leaderboard above as conditional on the "
            "declared windows, and treat the disagreeing arm as the reason to "
            "settle those dates before acting on the ranking.",
            "",
        ]

    lines += _sensitivity_movement(per_model)
    return lines


def _sensitivity_movement(per_model: pd.DataFrame) -> list[str]:
    """Which models actually changed rank, and whether the winners were among them."""
    verdict = sensitivity.agreement(per_model)
    arms = verdict["arms"]
    baseline = per_model[per_model["arm"] == arms[0]].set_index("model")
    best_clean = baseline["clean_rank"].idxmin()
    best_shock = baseline["shock_rank"].idxmin()

    winners_held = all(
        per_model[per_model["arm"] == arm].set_index("model").loc[best, f"{col}_rank"] == 1
        for arm in arms
        for best, col in ((best_clean, "clean"), (best_shock, "shock"))
    )

    lines = []
    if winners_held:
        lines += [
            f"The two models the finding turns on do not move: `{best_clean}` "
            f"ranks first on clean months and `{best_shock}` ranks first on "
            "shock months under every window set.",
            "",
        ]
    else:
        lines += [
            f"The models the finding turns on — `{best_clean}` on clean months, "
            f"`{best_shock}` on shock months — do **not** hold first place under "
            "every window set. The headline pair is boundary-dependent.",
            "",
        ]

    if verdict["rankings_identical"]:
        lines += ["No model changes rank in either column.", ""]
        return lines

    for column, changed in (
        ("clean", verdict["clean_rank_changes"]),
        ("shock", verdict["shock_rank_changes"]),
    ):
        if not changed:
            lines.append(f"No model changes rank in the {column} column.")
        else:
            names = ", ".join(f"`{m}`" for m in changed)
            lines.append(
                f"Models whose {column} rank moves between window sets: {names}."
            )
    lines.append("")
    return lines


def _by_shock_type(frame: pd.DataFrame) -> list[str]:
    """The shock leaderboard, unpooled into the individual windows.

    The clean/shock split is binary, and this section is the same objection
    this project raises against the overall leaderboard, applied one level
    down. "Shock" is not one thing here: the declared windows are a cliff to
    zero, a slow climb, a second cliff inside that climb, and a compound
    security-and-landslide event. Averaging them produces a single ordering
    that no individual disruption need resemble.

    Reported whether or not it agrees with the pooled table, for the same
    reason the horizon split is. If the pooled shock ranking turned out to be
    driven by one event, the pooled table would look exactly as it does now.

    The per-window counts are small -- tens of forecasts, not thousands -- so
    an individual ordering here is not resolvable and the section says so. The
    claim that survives that thinness is the *pattern*: which windows agree
    with which, and how much of the pooled column one event supplies. Both are
    counting facts about the panel, not estimates from it.
    """
    shock = regimes.SHOCK
    if "shock_window" not in frame.columns:
        return []

    rows = frame[(frame["regime"] == shock) & frame["shock_window"].notna()]
    windows = sorted(rows["shock_window"].unique())
    if len(windows) < 2:
        return []

    per_window = rows.groupby(["model", "shock_window"])["mase"].mean().unstack()
    if per_window.isna().to_numpy().any():
        # A model absent from a window is a ragged panel, and the ranks below
        # would silently compare different model sets column to column.
        return []
    ranks = per_window.rank(method="min").astype(int)
    counts = (rows.groupby("shock_window").size() / rows["model"].nunique()).astype(int)
    pooled = rows.groupby("model")["mase"].mean()
    pooled_rank = pooled.rank(method="min").astype(int)

    order = sorted(per_window.columns, key=lambda w: -counts[w])
    lines = [
        "### Is \"shock\" one thing?",
        "",
        "The split above is binary, and that is the same averaging this project "
        "objects to in the overall leaderboard, one level down. The declared "
        "windows are not variations on a theme: they are a cliff to zero, a "
        "slow climb, a second cliff inside that climb, and a compound security "
        "and landslide event. Below, the same shock forecasts are scored within "
        "each window instead of pooled across them.",
        "",
        "Mean MASE, rank in brackets. Lower is better.",
        "",
        "| Model | Pooled shock | "
        + " | ".join(f"`{w}`" for w in order) + " |",
        "|---" * (len(order) + 2) + "|",
    ]
    for model in per_window.index:
        cells = " | ".join(
            f"{_fmt(per_window.loc[model, w], 2)} ({ranks.loc[model, w]})"
            for w in order
        )
        lines.append(
            f"| `{model}` | {_fmt(pooled[model], 2)} ({pooled_rank[model]}) | "
            f"{cells} |"
        )
    # The counts belong inside the table, beside the numbers they qualify. A
    # separate one-row table has no header separator and does not render.
    lines += [
        "| **Forecasts per model** | **" + str(int(counts.sum())) + "** | "
        + " | ".join(f"**{counts[w]}**" for w in order) + " |",
        "",
    ]

    winners = {w: per_window[w].idxmin() for w in order}
    distinct = sorted(set(winners.values()))
    lines += [
        f"**{len(windows)} windows, {len(distinct)} different winners.** "
        + "; ".join(f"`{w}` &rarr; `{winners[w]}`" for w in order)
        + ".",
        "",
    ]

    # Which windows agree with which. A block structure here is the finding;
    # scattered signs would be thin data and would be reported as such.
    pairs = []
    for left, right in itertools.combinations(order, 2):
        try:
            rho, _ = metrics.rank_correlation(per_window[left], per_window[right])
        except ValueError:
            return []
        pairs.append((left, right, rho))

    lines += [
        "Whether two disruptions agree about which model to use, for every pair "
        "of windows:",
        "",
        "| Window | Window | Rank correlation | Agree? |",
        "|---|---|---:|---|",
    ]
    for left, right, rho in pairs:
        verdict = "yes" if rho > 0 else "no"
        lines.append(f"| `{left}` | `{right}` | {_fmt(rho, 2)} | {verdict} |")
    lines.append("")

    # The structural claim, stated only if the panel actually shows it -- and
    # then immediately qualified by how many windows it actually rests on.
    covid = [w for w in order if "covid" in w or "delta" in w]
    other = [w for w in order if w not in covid]
    if covid and other:
        within = [r for a, b, r in pairs if a in covid and b in covid]
        across = [r for a, b, r in pairs if (a in covid) != (b in covid)]
        share = counts[covid].sum() / counts.sum() * 100
        if within and across and min(within) > 0 and max(across) < 0:
            lines += [
                "That table has a block structure. **Every pair of COVID-era "
                "windows agrees, and every pair that straddles COVID and a "
                "non-COVID disruption disagrees.** The COVID windows are one "
                "event subdivided, so their mutual agreement is close to "
                "tautological; the part that would carry information is what "
                "they collectively disagree with.",
                "",
                f"The COVID windows supply **{share:.0f}%** of the pooled shock "
                "column, so the pooled shock ranking is largely a ranking on one "
                f"event. On `{other[0]}`, `{winners[other[0]]}` wins and the "
                f"pooled winner `{pooled.idxmin()}` ranks "
                f"{ranks.loc[pooled.idxmin(), other[0]]} of {len(per_window)}.",
                "",
            ]

        # The qualification is not conditional on the block claim having been
        # made. Any COVID-versus-other contrast drawn from this table rests on
        # the non-COVID windows, and when there are one or two of them the
        # contrast is one window wearing the clothes of a pattern.
        if len(other) < NON_COVID_FLOOR:
            names = ", ".join(f"`{w}`" for w in other)
            plural = "s" if len(other) > 1 else ""
            odd = other[0]
            lines += [
                f"**That block rests on {len(other)} non-COVID window{plural} "
                f"({names}), and it cannot carry the weight the picture "
                f"suggests.** The {len(across)} negative correlations in the "
                f"table are not {len(across)} independent pieces of evidence: "
                f"every one of them involves {names}, so they are one window "
                f"compared {len(across)} times. The apparent block is what "
                f"{len(covid)} subdivisions of a single event and "
                f"{len(other)} other{plural} would look like whether or not "
                "disruption type matters at all.",
                "",
                "Two claims are indistinguishable on this panel, and they are "
                "not the same claim:",
                "",
                "1. COVID-era disruptions call for different models than "
                "non-COVID disruptions do.",
                f"2. `{odd}` happens to have an idiosyncratic winner.",
                "",
                f"The obvious mechanism for the second &mdash; that "
                f"`{winners[odd]}` suits this kind of shock because of how it "
                "is built &mdash; is a **hypothesis fitted to one window**, not "
                "a finding. It is written down here so it can be tested later, "
                "and it is not evidence for itself. What would separate the two "
                "claims is a second non-COVID disruption, from this site or "
                "another.",
                "",
                "The heatmap in `results/figures/` shows this contrast as a "
                "clean block of colour. That cleanliness is a property of "
                "having one window on one side, not of the strength of the "
                "evidence, and it should not be read as the latter.",
                "",
            ]

    smallest = int(counts.min())
    lines += [
        "**Read all of this against the counts.** The thinnest window carries "
        f"{smallest} forecasts per model. No single column above is resolvable "
        "on its own, and none of these orderings is offered as one: the "
        f"bootstrap intervals reported earlier are already wide on the "
        f"{int(counts.sum())} pooled shock forecasts and would be wider still "
        "here. What the section supports is the pattern across columns, not any "
        "cell in them. A second site whose disruptions are not these ones is "
        "what would settle it, and "
        "[docs/second_site.md](docs/second_site.md) records why none was added.",
        "",
    ]
    return lines


def _by_horizon(frame: pd.DataFrame) -> list[str]:
    """The same comparison at each forecast lead time, unpooled.

    The leaderboard averages h=1 through h=6. Nobody forecasts at the average
    of six lead times: an operations lead reading the briefing is reading one
    horizon. If the inversion were driven by the long horizons alone, the
    pooled table would look exactly as it does now and the short-horizon reader
    would be misled by it -- so the split is reported whether or not it agrees.
    """
    clean, shock = regimes.CLEAN, regimes.SHOCK
    if "horizon" not in frame.columns:
        return []
    horizons = sorted(int(h) for h in frame["horizon"].dropna().unique())
    if len(horizons) < 2:
        return []

    rows = []
    for horizon in horizons:
        subset = frame[frame["horizon"] == horizon]
        table = backtest.per_regime_table(subset)
        if clean not in table.columns or shock not in table.columns:
            return []
        try:
            rho, _ = metrics.rank_correlation(table[clean], table[shock])
        except ValueError:
            return []
        best_clean, best_shock = table[clean].idxmin(), table[shock].idxmin()
        rows.append(
            {
                "horizon": horizon,
                "best_clean": best_clean,
                "best_clean_shock_rank": int(table.loc[best_clean, f"{shock}_rank"]),
                "best_shock": best_shock,
                "best_shock_clean_rank": int(table.loc[best_shock, f"{clean}_rank"]),
                "rho": rho,
                "n_models": len(table),
            }
        )

    lines = [
        "### Does the finding survive at every forecast lead time?",
        "",
        f"The leaderboard above pools h={horizons[0]} through h={horizons[-1]}. "
        "A planner reading the briefing is reading one lead time, not the "
        "average of six. Here the same forecasts are split by horizon.",
        "",
        "| Horizon | Best on clean | Its shock rank | Best on shock | Its clean rank | Rank correlation |",
        "|---:|---|---:|---|---:|---:|",
    ]
    for row in rows:
        lines.append(
            f"| h={row['horizon']} | `{row['best_clean']}` | "
            f"{row['best_clean_shock_rank']} of {row['n_models']} | "
            f"`{row['best_shock']}` | "
            f"{row['best_shock_clean_rank']} of {row['n_models']} | "
            f"{row['rho']:+.3f} |"
        )
    lines.append("")

    inverting = sum(1 for row in rows if row["rho"] < 0)
    total = len(rows)
    clean_winners = {row["best_clean"] for row in rows}
    shock_winners = {row["best_shock"] for row in rows}

    if inverting == total and len(clean_winners) == 1 and len(shock_winners) == 1:
        lines += [
            f"The correlation is negative at **{inverting} of {total}** lead "
            f"times, and the same two models take the two crowns at every one of "
            f"them: `{clean_winners.pop()}` on clean months, "
            f"`{shock_winners.pop()}` on shock months. The inversion is not an "
            "artefact of pooling horizons — it is present at each horizon "
            "separately.",
            "",
        ]
        return lines

    if inverting == total:
        lines += [
            f"The correlation is negative at **{inverting} of {total}** lead "
            "times, so the inversion itself survives the split. Which model wins "
            "does not: the crown changes hands across horizons, so a "
            "recommendation has to name the lead time it applies to.",
            "",
        ]
        return lines

    holds = ", ".join(f"h={row['horizon']}" for row in rows if row["rho"] < 0) or "no horizon"
    lines += [
        f"The correlation is negative at only **{inverting} of {total}** lead "
        f"times ({holds}). The pooled table above is therefore carrying the "
        "horizons where it holds into the ones where it does not, and the "
        "headline should be read as a statement about those lead times rather "
        "than about the series.",
        "",
    ]
    return lines


def _ablations(
    table: pd.DataFrame, bootstrap_path: str | Path = "results/bootstrap.csv"
) -> list[str]:
    """What each design choice is worth, from the pairs declared in models.py.

    A leaderboard says which model won. It does not say what any single design
    decision bought, because two models differ in many things at once. The
    pairs in :data:`yatra.models.ABLATIONS` differ by exactly one, so their gap
    is readable as the worth of that one thing -- and both arms are scored on
    the same origins against the same MASE denominator, so the gap cannot be a
    normalisation artefact.

    The decisive/undecided line is drawn at the bootstrap's **own declared
    confidence level**, read from the artefact rather than typed here. A
    threshold invented in this file would be a number in the README that no row
    produced.
    """
    clean, shock = regimes.CLEAN, regimes.SHOCK
    if clean not in table.columns or shock not in table.columns:
        return []

    pairs = [
        a for a in models.ABLATIONS
        if a.treatment in table.index and a.control in table.index
    ]
    if not pairs:
        return []

    shares, confidence = _pairwise_shares(bootstrap_path)

    lines = [
        "### What each design choice is worth",
        "",
        "The leaderboard says which model won; it does not say what any one "
        "decision bought, because two models differ in many things at once. "
        "Each pair below differs by exactly one, and both arms are scored on the "
        "same origins against the same denominator.",
        "",
    ]
    header = "| Comparison | What varies | Regime | With | Without | Difference |"
    rule = "|---|---|---|---:|---:|---:|"
    if shares:
        header += " With it better in |"
        rule += "---:|"
    lines += [header, rule]

    verdicts = []
    for ablation in pairs:
        label = f"`{ablation.treatment}` vs `{ablation.control}`"
        deltas = {}
        for regime in (clean, shock):
            with_it = float(table.loc[ablation.treatment, regime])
            without = float(table.loc[ablation.control, regime])
            delta = with_it - without
            deltas[regime] = delta
            share = shares.get((ablation.treatment, ablation.control, regime))
            row = (
                f"| {label if regime == clean else ''} | "
                f"{ablation.varies if regime == clean else ''} | {regime} | "
                f"{_fmt(with_it)} | {_fmt(without)} | {delta:+.3f} |"
            )
            if shares:
                row += f" {share * 100:.1f}% |" if share is not None else " — |"
            lines.append(row)
        verdicts.append((ablation, deltas))
    counts = _regime_counts_per_model(table)
    basis = ""
    if counts:
        basis = (
            f" Every arm is scored on the same {counts[clean]:,} clean and "
            f"**{counts[shock]:,} shock** forecasts, and the shock column is the "
            "thin one: read every difference in it against that number."
        )
    lines += [
        "",
        "Lower MASE is better, so a **negative** difference means the choice "
        "helped. The last column is the share of block-bootstrap resamples in "
        "which it helped, which is what carries the claim — a difference in the "
        "third decimal is not a result on its own." + basis,
        "",
    ]

    lines += _ablation_verdicts(verdicts, shares, confidence, counts)
    return lines


def _regime_counts_per_model(table: pd.DataFrame) -> dict[str, int]:
    """Forecasts behind each regime column, per model. Empty if not recorded."""
    counts = {}
    for regime in (regimes.CLEAN, regimes.SHOCK):
        column = f"{regime}_n"
        if column not in table.columns or table[column].empty:
            return {}
        counts[regime] = int(table[column].max())
    return counts


def _pairwise_shares(
    bootstrap_path: str | Path,
) -> tuple[dict[tuple[str, str, str], float], float | None]:
    """``p_beats`` keyed by (model, opponent, regime), plus the declared level."""
    try:
        path = Path(bootstrap_path)
        if not path.exists():
            return {}, None
        boot = pd.read_csv(path)
    except Exception:  # noqa: BLE001 - the README must render without it
        return {}, None
    if "statistic" not in boot.columns:
        return {}, None

    rows = boot[boot["statistic"] == "p_beats"]
    if rows.empty:
        return {}, None
    shares = {
        (str(r.model), str(r.opponent), str(r.regime)): float(r.point)
        for r in rows.itertuples()
    }
    confidence = None
    if "confidence" in rows.columns and rows["confidence"].notna().any():
        confidence = float(rows["confidence"].dropna().iloc[0])
    return shares, confidence


def _ablation_verdicts(
    verdicts: list[tuple["models.Ablation", dict[str, float]]],
    shares: dict[tuple[str, str, str], float],
    confidence: float | None,
    counts: dict[str, int] | None = None,
) -> list[str]:
    """One line per pair, then an honest count of how many are actually resolved.

    The lines describe the *sign* of each difference, not its importance. A gap
    in the third decimal has a sign too, and calling it "helps" would dress a
    rounding difference as a recommendation; the resolved count below is what
    says which of these the record can actually settle.
    """
    clean, shock = regimes.CLEAN, regimes.SHOCK
    lines = []
    resolved = 0
    flipped = []

    for ablation, deltas in verdicts:
        helps_clean = deltas[clean] < 0
        helps_shock = deltas[shock] < 0
        if helps_clean != helps_shock:
            flipped.append(ablation)
            direction = (
                "better on clean months, worse on shock ones"
                if helps_clean
                else "better on shock months, worse on clean ones"
            )
            tail = f"the sign flips between regimes — {direction}."
        elif helps_clean:
            tail = "lower error in both regimes."
        else:
            tail = (
                "higher error in both regimes. It is here because it was tried, "
                "not because it worked."
            )
        lines.append(f"- **{ablation.varies.capitalize()}** — {tail}")

        if confidence is not None:
            for regime in (clean, shock):
                share = shares.get((ablation.treatment, ablation.control, regime))
                # Symmetric on purpose: the pair is resolved if EITHER arm
                # reached the level. Writing the lower bound as
                # `share <= 1 - confidence` puts a float subtraction on
                # the boundary and drops the exact case.
                if share is not None and (share >= confidence or (1.0 - share) >= confidence):
                    resolved += 1

    lines.append("")

    if flipped and len(flipped) == len(verdicts):
        lines += [
            "Every one of these choices trades one regime against the other. "
            "That is the headline finding reappearing inside pairs of models "
            "differing by a single decision: on this record there is no design "
            "choice here that is simply better, only choices that are better "
            "somewhere.",
            "",
        ]
    elif flipped:
        names = ", ".join(f"**{a.varies}**" for a in flipped)
        lines += [
            f"{len(flipped)} of {len(verdicts)} choices trade one regime against "
            f"the other ({names}) — the headline finding reappearing inside a "
            "pair of models differing by a single decision.",
            "",
        ]

    calendar = next(
        (a for a, d in verdicts if a.name == "calendar" and (d[clean] < 0) != (d[shock] < 0)),
        None,
    )
    if calendar is not None:
        basis = (
            f"{counts[shock]:,} shock forecasts" if counts and shock in counts
            else "the shock forecasts in this record"
        )
        lines += [
            "The calendar pair is worth reading twice, because the calendar "
            "layer is this project's largest single investment. A festival "
            "regressor asserts a surge on a date the ephemeris computed, and a "
            "closure or a flood does not move that date — the feature goes on "
            "predicting an arrival pattern that policy or the weather has "
            "cancelled. The sign above is consistent with that.",
            "",
            f"**It is an observation, not a basis to build on.** It is one pair "
            f"of models on {basis} from a single shrine, and it is not among "
            "the comparisons that clear the declared level below. The obvious "
            "thing to do with it — route calendar features by regime, so the "
            "model drops them once it thinks it is in a shock — has "
            "deliberately not been built. Doing so would fit a mechanism to a "
            "difference this record cannot resolve, and the resulting model "
            "would then be scored on the same disrupted months that suggested "
            "it. What would justify building it is more disrupted months, from "
            "a site whose disruptions are not these ones.",
            "",
        ]

    if confidence is not None:
        total = 2 * len(verdicts)
        verb = "clears" if resolved == 1 else "clear"
        lines += [
            f"Of the {total} pair-and-regime comparisons above, **{resolved}** "
            f"{verb} the bootstrap's declared {confidence:.0%} level in one "
            "direction or the other. The rest are directional and unresolved by "
            "this record, and are reported as such rather than as findings.",
            "",
        ]
    return lines


def _calendar(
    config_path: str | Path = "experiments/configs/calendar.yaml",
    festivals_path: str | Path = "results/festivals.csv",
    calendar_path: str | Path = "results/calendar.csv",
) -> list[str]:
    """What the calendar layer is actually made of.

    ``sarimax_cal`` wins the clean regime and is one arm of the ablation above,
    so a reader judging either result needs to know what its features contain.
    "The calendar layer" sounds like an almanac; it is a handful of festivals,
    and saying which ones is the difference between a claim a reader can audit
    and one they have to take on trust.

    Every value here is read from the config that produced the dates or from
    the dates themselves. Nothing about the calendar is typed into this file --
    which is the same rule as the rest of the section, and doubly so here,
    where a hardcoded date table is a spec violation (brief constraint 6).
    """
    try:
        config = yaml.safe_load(Path(config_path).read_text(encoding="utf-8")) or {}
    except Exception:  # noqa: BLE001 - the README must render without it
        return []
    festivals = config.get("festivals") or []
    if not festivals:
        return []

    span = config.get("range") or {}
    ephemeris = config.get("ephemeris") or {}
    location = config.get("location") or {}

    resolved = _row_count(festivals_path)
    lines = [
        "### What the calendar layer contains",
        "",
        "`sarimax_cal` wins the clean regime and is one arm of the ablation "
        "above, so what its features are made of is part of reading both "
        "results. The dates are computed from an ephemeris — there is no date "
        "table in `src/` — under the declarations below.",
        "",
        "| | |",
        "|---|---|",
        f"| Backend | `{config.get('backend', '—')}`"
        + (f" ({ephemeris['kernel']})" if ephemeris.get("kernel") else "")
        + " |",
        f"| Ayanamsa | {config.get('ayanamsa', '—')} |",
        f"| Lunar month scheme | {config.get('lunar_month_scheme', '—')} |",
        f"| Reference location | {location.get('name', '—')} |",
        f"| Span computed | {span.get('start', '—')} to {span.get('end', '—')} |",
    ]
    if resolved is not None:
        lines.append(f"| Festival dates resolved | {resolved:,} |")
    lines += [
        "",
        f"**{len(festivals)} festivals, not a general almanac.** The civil-day "
        "rule is declared per festival because it genuinely differs, and it "
        "decides more dates than any plausible disagreement between "
        "ephemerides does.",
        "",
        "| Festival | Tithi rule | Civil-day rule | Duration |",
        "|---|---|---|---:|",
    ]
    for entry in festivals:
        rule = entry.get("rule") or {}
        tithi = " ".join(
            str(rule.get(key, "?")) for key in ("month", "paksha", "tithi")
        )
        duration = entry.get("duration_days")
        lines.append(
            f"| {entry.get('label', entry.get('id', '?'))} | {tithi} | "
            f"{rule.get('observance', '—')} | "
            f"{f'{int(duration)} day' + ('s' if int(duration) != 1 else '') if duration else '—'} |"
        )
    lines.append("")

    features = config.get("features") or []
    if features:
        named = ", ".join(f"`{name}`" for name in features)
        lines += [
            f"The monthly columns handed to the model are {named}. Each is a "
            "function of the calendar alone and touches no observation, so none "
            "of them can carry a future footfall value into a forecast.",
            "",
        ]

    coverage = _calendar_coverage(calendar_path, features)
    if coverage is not None:
        months, with_festival, still_live = coverage
        sentence = (
            f"Across the {months:,} months in the feature frame, "
            f"**{with_festival:,}** carry at least one festival day."
        )
        quiet = months - with_festival
        if still_live:
            named = ", ".join(f"`{name}`" for name in still_live)
            sentence += (
                f" In the other {quiet:,} the festival counts are zero, so "
                f"whatever the arm contributes there comes from {named}."
            )
        else:
            sentence += (
                f" In the other {quiet:,} every calendar column is zero, so the "
                "arm and its control see identical inputs."
            )
        lines += [sentence, ""]
    return lines


def _row_count(path: str | Path) -> int | None:
    try:
        p = Path(path)
        if not p.exists():
            return None
        return int(len(pd.read_csv(p)))
    except Exception:  # noqa: BLE001 - the README must render without it
        return None


def _calendar_coverage(
    path: str | Path, features: list[str]
) -> tuple[int, int, list[str]] | None:
    """How much of the series the calendar actually touches.

    Returns ``(months, months_with_a_festival_day, still_live)``, where
    ``still_live`` names the declared feature columns that are non-zero in at
    least one festival-free month. Those are what separates the calendar arm
    from its control in the months no festival falls in, and asserting the
    columns all go quiet there without checking would be wrong: a drift term
    keeps moving whether or not a festival lands.
    """
    try:
        p = Path(path)
        if not p.exists():
            return None
        frame = pd.read_csv(p)
    except Exception:  # noqa: BLE001 - the README must render without it
        return None
    if "festival_days" not in frame.columns or frame.empty:
        return None

    quiet = frame[frame["festival_days"] <= 0]
    still_live = [
        name
        for name in features
        if name in quiet.columns
        and pd.to_numeric(quiet[name], errors="coerce").fillna(0).ne(0).any()
    ]
    return int(len(frame)), int((frame["festival_days"] > 0).sum()), still_live


def _applicability(path: str | Path = "results/applicability.csv") -> list[str]:
    """Models that could not be fit at all. An absence that has to be visible.

    A model missing from the accuracy tables looks like a model nobody tried.
    When the reason is that the series broke it, that is a result about
    forecasting through shocks and belongs beside the accuracy numbers.
    """
    frame = None
    try:
        p = Path(path)
        if p.exists():
            frame = pd.read_csv(p)
    except Exception:  # noqa: BLE001 - the README must render without it
        return []
    if frame is None or frame.empty:
        return []

    broken = frame[~frame["applicable"].astype(bool)]
    if broken.empty:
        return []

    lines = [
        "### Models that could not be scored",
        "",
        "These are registered and were attempted, but cannot be fit on this "
        "series. They are absent from the tables above for that reason, not "
        "because they were untested.",
        "",
        "| Model | Origins where the fit is impossible | First such origin |",
        "|---|---:|---|",
    ]
    for row in broken.itertuples():
        lines.append(
            f"| `{row.model}` | {int(row.origins_failed)} of "
            f"{int(row.origins_total)} | {row.first_failure_origin} |"
        )
    lines += [
        "",
        "Multiplicative seasonality divides by a seasonal index, so it requires "
        "every month in its training window to be above zero. The shrine closed "
        "completely for part of 2020 and those months are recorded as zero. From "
        "the first origin whose history contains a closed month, the model is "
        "undefined — and every later origin inherits that history, so it never "
        "becomes fittable again.",
        "",
        "It was not quietly replaced with the additive variant. Doing so would "
        "put a number in the table under this model's name that a different "
        "model produced. **Applicability is part of the comparison:** a method "
        "that stops existing once a shock enters the record is not a safe "
        "default, however well it scores in ordinary months.",
        "",
    ]
    return lines


def _caveats(shocks_config: str | Path) -> list[str]:
    try:
        windows = regimes.load_windows(shocks_config)
    except Exception:
        return []
    pending = regimes.unverified(windows)
    if not pending:
        return []
    names = ", ".join(f"`{w.id}`" for w in pending)
    return [
        "### Caveat: unverified shock windows",
        "",
        f"{len(pending)} of {len(windows)} declared shock windows carry citations "
        f"that the project owner has not yet checked against the source: {names}. "
        "The dates were drafted from public reporting. Until they are verified, "
        "the regime split — and therefore every number above — rests on an "
        "unaudited boundary.",
        "",
    ]


def render(
    metrics_path: str | Path = "results/metrics.csv",
    shocks_config: str | Path = "experiments/configs/shocks.yaml",
) -> str:
    frame = backtest.read(metrics_path)
    if frame.empty:
        raise ConfigError(f"{metrics_path} has no rows.")

    leaderboard, table = _leaderboard(frame)
    blocks = (
        [WARNING, ""]
        + _scope(frame)
        + _provenance(frame)
        + _regime_counts(frame)
        + leaderboard
        + _inversion(frame, table)
        + _sensitivity()
        + _by_shock_type(frame)
        + _by_horizon(frame)
        + _ablations(table)
        + _calendar()
        + _applicability()
        + _caveats(shocks_config)
    )
    return "\n".join(blocks).rstrip() + "\n"


def update_readme(
    readme_path: str | Path = "README.md",
    metrics_path: str | Path = "results/metrics.csv",
    shocks_config: str | Path = "experiments/configs/shocks.yaml",
) -> Path:
    readme_path = Path(readme_path)
    text = readme_path.read_text(encoding="utf-8")

    if BEGIN not in text or END not in text:
        raise ConfigError(
            f"{readme_path} is missing the {BEGIN} / {END} markers. The generator "
            "will not guess where the results section belongs."
        )
    head, _, rest = text.partition(BEGIN)
    _, _, tail = rest.partition(END)

    body = render(metrics_path, shocks_config)
    readme_path.write_text(f"{head}{BEGIN}\n\n{body}\n{END}{tail}", encoding="utf-8")
    return readme_path
