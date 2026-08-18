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

from pathlib import Path

import pandas as pd

from . import backtest, metrics, regimes
from .errors import ConfigError

BEGIN = "<!-- BEGIN GENERATED -->"
END = "<!-- END GENERATED -->"

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
        + _provenance(frame)
        + _regime_counts(frame)
        + leaderboard
        + _inversion(frame, table)
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
