"""Pipeline stages. One function per `make` target.

Stages that are not built yet raise :class:`NotImplementedError` naming the
phase that will build them. They do not return quietly, and `all` does not skip
them -- a pipeline that reports success while a stage is missing is the failure
class this project is designed against.
"""

from __future__ import annotations

import sys
from datetime import date, datetime
from pathlib import Path

from . import (
    applicability,
    backtest,
    bootstrap,
    calendarfeat,
    contract,
    ephemeris,
    metrics,
    models,
    panchanga,
    regimes,
    report,
    sensitivity,
    ui,
)
from . import __version__
from . import figures as figures_mod
from . import ingest as ingest_mod
from . import operations as operations_mod
from .errors import ConfigError

DATA_DIR = Path("data/raw")
RESULTS_DIR = Path("results")
CONFIG_DIR = Path("experiments/configs")


def _say(message: str) -> None:
    print(message, flush=True)


def validate() -> None:
    """Data contract and shock-window citations. The first gate."""
    _say("== validate ==")

    windows = regimes.load_windows(CONFIG_DIR / "shocks.yaml")
    _say(f"shock windows: {len(windows)} declared, all citations present")
    for window in windows:
        flag = "" if window.verified else "  [UNVERIFIED]"
        _say(f"  {window.id:<16} {window.start}..{window.end}  "
             f"{window.n_months:>2}mo{flag}")
    pending = regimes.unverified(windows)
    if pending:
        _say(f"  -> {len(pending)} window(s) awaiting owner verification of the source")

    observations = contract.load(DATA_DIR)
    _say(f"observations: {observations.describe()}")


def calendar() -> None:
    """Festival dates from the ephemeris, then the monthly feature frame.

    Nothing here is tabulated. Every date in ``results/calendar.csv`` is solved
    for from the configured backend, which is why the stage takes half a minute
    rather than being a file read.
    """
    import yaml

    _say("== calendar ==")

    config = yaml.safe_load((CONFIG_DIR / "calendar.yaml").read_text(encoding="utf-8"))
    span = config.get("range")
    if not span or "start" not in span or "end" not in span:
        raise ConfigError(
            "calendar.yaml declares no 'range: {start, end}'. It has no default: "
            "the span has to cover the observation window plus every forecast "
            "horizon past it, and silently guessing would leave sarimax_cal "
            "without exogenous rows at the last origins."
        )
    start, end = _as_date(span["start"]), _as_date(span["end"])

    backend = ephemeris.build(config)
    _say(f"backend: {backend.name}, ayanamsa {config.get('ayanamsa', 'lahiri')}, "
         f"{config['lunar_month_scheme']} months")
    _say(f"computing {start}..{end} at {backend.location.name}")

    computed = panchanga.compute(backend, config, start, end)
    adhika = [m for m in computed.months if m.is_adhika]
    _say(f"festivals: {len(computed.occurrences)} occurrences, "
         f"{len(computed.months)} lunar months, {len(adhika)} adhika")

    frame = calendarfeat.build(computed, config, start, end)
    path = calendarfeat.write(frame, RESULTS_DIR / "calendar.csv")
    _say(f"wrote {path}: {len(frame)} months x {len(frame.columns)} features "
         f"({', '.join(frame.columns)})")

    # Dated festival days, for the operations briefing. The monthly frame is
    # what models are fit on; this is the only artefact that says *which days*
    # inside a month the crowds land on.
    occurrences = calendarfeat.occurrence_frame(computed)
    path = calendarfeat.write(occurrences.set_index("date"), RESULTS_DIR / "festivals.csv")
    _say(f"wrote {path}: {len(occurrences)} dated festival days")


def _as_date(value) -> "date":
    """Accept a YAML date or an ISO string; reject anything else loudly."""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        return date.fromisoformat(value)
    raise ConfigError(f"Cannot read {value!r} as a date in calendar.yaml 'range'.")


def run_backtest() -> None:
    """Rolling-origin backtest over the full model set."""
    _say("== backtest ==")

    observations = contract.load(DATA_DIR)
    config = backtest.load_config(CONFIG_DIR / "backtest.yaml")
    windows = regimes.load_windows(CONFIG_DIR / "shocks.yaml")

    calendar_features = None
    needs = [m for m in config.model_names if m in models.NEEDS_CALENDAR]
    if needs:
        path = RESULTS_DIR / "calendar.csv"
        if not path.exists():
            raise FileNotFoundError(
                f"{path} not found, but the config includes calendar-dependent "
                f"model(s) {needs}. Run the calendar stage first, or remove them "
                "from experiments/configs/backtest.yaml. They will not be fit "
                "without features."
            )
        import pandas as pd

        calendar_features = pd.read_csv(path, index_col=0, parse_dates=True)

    frame = backtest.run(observations.monthly, config, calendar_features, windows,
                         shocks_path=CONFIG_DIR / "shocks.yaml")
    path = backtest.write(frame, RESULTS_DIR / "metrics.csv")
    _say(f"wrote {path}: {len(frame):,} forecasts, "
         f"{frame['model'].nunique()} models, {frame['origin'].nunique()} origins")


def relabel() -> None:
    """Re-apply the current shock windows to results/metrics.csv.

    Cheap by design: regimes are evaluation labels, so no model has to be refit
    when a window boundary moves. Editing shocks.yaml and re-running this is
    seconds; re-running the backtest is half an hour and would change nothing
    except the labels.
    """
    _say("== relabel ==")

    path = RESULTS_DIR / "metrics.csv"
    frame = backtest.read(path)
    before = int((frame["regime"] == regimes.SHOCK).sum() / frame["model"].nunique())

    frame = backtest.relabel_from(frame, CONFIG_DIR / "shocks.yaml")
    after = int((frame["regime"] == regimes.SHOCK).sum() / frame["model"].nunique())

    backtest.write(frame, path)
    _say(f"shock forecasts per model: {before} -> {after}")
    _say(f"rewrote {path} (no models were refit)")


def run_bootstrap() -> None:
    """Block bootstrap over origins. Puts an interval around the inversion."""
    _say("== bootstrap ==")

    frame = backtest.read(RESULTS_DIR / "metrics.csv")
    backtest.assert_labels_current(frame, CONFIG_DIR / "shocks.yaml")
    config = bootstrap.load_config(CONFIG_DIR / "backtest.yaml")
    _say(f"{config.n_resamples:,} resamples, blocks of {config.block_origins} origins, "
         f"{int(config.confidence * 100)}% intervals")

    result = bootstrap.run(frame, config)
    path = bootstrap.write(result, RESULTS_DIR / "bootstrap.csv")

    rho = result[result["statistic"] == "rank_correlation"].iloc[0]
    inversion = result[result["statistic"] == "p_inversion"].iloc[0]
    _say(f"wrote {path}: {len(result)} statistics")
    _say(f"  clean-vs-shock rank correlation {rho['point']:+.3f} "
         f"[{rho['lo']:+.3f}, {rho['hi']:+.3f}]")
    _say(f"  ranking inverted in {inversion['point']:.1%} of resamples")

    pairs = result[result["statistic"] == "p_beats"]
    if len(pairs):
        _say(f"  {len(pairs)} pairwise comparisons written; these carry the "
             "specific claims and are tighter than the omnibus rho.")
    if rho["lo"] < 0 < rho["hi"]:
        _say("  -> rho's interval spans zero. It asks whether the WHOLE ordering "
             "reverses, which is a harder question than any single substitution; "
             "read the pairwise rows for those.")


def figures() -> None:
    """Regenerate every figure from the committed artefacts."""
    _say("== figures ==")

    observations = contract.load(DATA_DIR)
    frame = backtest.read(RESULTS_DIR / "metrics.csv")
    backtest.assert_labels_current(frame, CONFIG_DIR / "shocks.yaml")
    windows = regimes.load_windows(CONFIG_DIR / "shocks.yaml")
    table = backtest.per_regime_table(frame)

    bootstrap_frame = None
    path = RESULTS_DIR / "bootstrap.csv"
    if path.exists():
        bootstrap_frame = bootstrap.read(path)
    else:
        _say("  (no bootstrap.csv yet, skipping the interval figure)")

    written = figures_mod.build_all(
        observations.monthly, frame, table, windows,
        RESULTS_DIR / "figures", bootstrap_frame,
    )
    for item in written:
        _say(f"wrote {item}")


def run_applicability() -> None:
    """Which registered models cannot be fit on this series, and where."""
    _say("== applicability ==")

    observations = contract.load(DATA_DIR)
    config = backtest.load_config(CONFIG_DIR / "backtest.yaml")
    excluded = applicability.excluded_models(config)

    if not excluded:
        _say("every registered model is in the backtest; nothing to probe")
        return

    _say(f"probing {len(excluded)} model(s) left out of the backtest: {', '.join(excluded)}")
    outcomes = applicability.probe(observations.monthly, config, excluded)
    frame = applicability.to_frame(outcomes)
    path = applicability.write(frame, RESULTS_DIR / "applicability.csv")
    _say(f"wrote {path}")

    for o in outcomes:
        if o.applicable:
            _say(f"  {o.model}: fittable at all {o.origins_total} origins "
                 "(excluded for another reason)")
        else:
            _say(f"  {o.model}: NOT fittable at {o.origins_failed} of "
                 f"{o.origins_total} origins, from {o.first_failure} onward")
            _say(f"    {o.reason}")


def run_sensitivity() -> None:
    """Re-score the same forecasts under every declared window definition."""
    _say("== sensitivity ==")

    frame = backtest.read(RESULTS_DIR / "metrics.csv")
    arms = sensitivity.load_arms(CONFIG_DIR / "backtest.yaml")
    _say(f"{len(arms)} arms: {', '.join(a.name for a in arms)}")

    per_model, summary = sensitivity.run(frame, arms)
    for path in sensitivity.write(per_model, summary, RESULTS_DIR):
        _say(f"wrote {path}")

    for row in summary.itertuples():
        _say(f"  {row.arm:<10} {row.shock_forecasts_per_model:>4} shock forecasts/model  "
             f"rho {row.rank_correlation:+.3f}  "
             f"{'inverts' if row.inverts else 'does NOT invert'}")

    verdict = sensitivity.agreement(per_model)
    if verdict["rankings_identical"]:
        _say("  -> every model holds its rank in both regimes across all arms. "
             "The finding does not depend on where the boundary is drawn.")
    else:
        _say(f"  -> ranks move between arms: clean {verdict['clean_rank_changes']}, "
             f"shock {verdict['shock_rank_changes']}. The boundary choice matters "
             "and must be reported with the result.")


def operations() -> None:
    """Forward forecast, turned into a crowd-planning briefing."""
    import pandas as pd

    _say("== operations ==")

    observations = contract.load(DATA_DIR)
    frame = backtest.read(RESULTS_DIR / "metrics.csv")
    # Same guard the other regime-consuming stages carry. The briefing splits
    # its bands by regime, so labels that no longer match shocks.yaml would put
    # a stale contingency range in front of a duty officer.
    backtest.assert_labels_current(frame, CONFIG_DIR / "shocks.yaml")
    config = operations_mod.load_config(CONFIG_DIR / "operations.yaml")

    model = operations_mod.choose_model(frame, config.model)
    _say(f"forecasting with '{model}'"
         f"{' (best on clean months)' if config.model == 'best_clean' else ''}")

    calendar_features = None
    if model in models.NEEDS_CALENDAR:
        path = RESULTS_DIR / "calendar.csv"
        if not path.exists():
            raise FileNotFoundError(
                f"{path} not found, but '{model}' needs calendar features. "
                "Run the calendar stage first."
            )
        calendar_features = pd.read_csv(path, index_col=0, parse_dates=True)

    festivals = None
    path = RESULTS_DIR / "festivals.csv"
    if path.exists():
        festivals = pd.read_csv(path, parse_dates=["date"])
        festivals["date"] = festivals["date"].dt.date
    else:
        _say("  (no festivals.csv, briefing will not name specific dates)")

    forecast = operations_mod.forward(
        observations.monthly, model, config.horizons, calendar_features
    )
    spread = operations_mod.error_spread(frame, model, config.confidence)
    current_scale = metrics.seasonal_naive_scale(observations.monthly)
    table = operations_mod.planning_table(
        forecast, spread, config.horizons, config, current_scale, festivals
    )

    written = operations_mod.write_table(table, RESULTS_DIR / "operations.csv")
    _say(f"wrote {written}")
    text = operations_mod.briefing(
        table, config, model, observations.monthly, spread,
        shocks_hash=backtest.shocks_fingerprint(CONFIG_DIR / "shocks.yaml"),
    )
    written = operations_mod.write_briefing(text, RESULTS_DIR / "briefing.md")
    _say(f"wrote {written}")

    if not config.ratios:
        _say("  no planning ratios declared -- briefing reports volumes only. "
             "See experiments/configs/operations.yaml.")


def build_ui() -> None:
    """Write the self-contained answer console to results/yatra.html.

    Runs last among the artefact stages because it reads what all of them
    wrote. It calls ``assert_labels_current`` for the same reason ``operations``
    does: this is the other document a non-technical reader opens away from the
    run that produced it, and a stale regime split reaching it would look
    exactly like a current one.
    """
    _say("== ui ==")

    frame = backtest.read(RESULTS_DIR / "metrics.csv")
    backtest.assert_labels_current(frame, CONFIG_DIR / "shocks.yaml")

    artefacts = ui.load(RESULTS_DIR, DATA_DIR, CONFIG_DIR)
    answers = ui.build_answers(artefacts)
    page = ui.render(artefacts, answers)

    written = ui.write(page, RESULTS_DIR / "yatra.html")
    size = written.stat().st_size / 1e6
    _say(f"wrote {written}  ({len(answers)} answers, "
         f"{len(artefacts.figures)} figures embedded, {size:.1f} MB)")
    _say("  open it directly in a browser -- it is one file and needs no server.")


def ingest() -> None:
    """Convert the owner's published figures into contract-shaped files.

    ``python make.py ingest --inspect <file>`` describes a candidate file and
    prints a config template for it. With no flag it reads
    ``experiments/configs/ingest.yaml`` and writes ``data/raw/``.
    """
    _say("== ingest ==")

    argv = sys.argv[1:]
    if "--inspect" in argv:
        position = argv.index("--inspect")
        if position + 1 >= len(argv):
            raise ConfigError("--inspect needs a file path.")
        _say(ingest_mod.inspect(Path(argv[position + 1])))
        return

    config = ingest_mod.load_config(CONFIG_DIR / "ingest.yaml")
    monthly, annual, sources = ingest_mod.build(config)
    _say(ingest_mod.summarise(monthly, annual))

    written = ingest_mod.write(monthly, annual, sources, DATA_DIR)
    for item in written:
        _say(f"wrote {item}")
    _say("Now run `python make.py validate` -- nothing here has been checked "
         "against the data contract yet.")


def build_report() -> None:
    """Rewrite the generated block in README.md from results/metrics.csv."""
    _say("== report ==")
    backtest.assert_labels_current(
        backtest.read(RESULTS_DIR / "metrics.csv"), CONFIG_DIR / "shocks.yaml"
    )
    path = report.update_readme("README.md", RESULTS_DIR / "metrics.csv",
                                CONFIG_DIR / "shocks.yaml")
    _say(f"rewrote the generated section of {path}")


def test() -> None:
    """Run pytest, calendar tests first.

    Two passes, not one, and the calendar pass gates the other. A drift in the
    festival computation invalidates every ablation result downstream, so there
    is nothing to learn from the rest of the suite until it passes -- and a
    single combined run would bury that signal among a hundred green dots.
    """
    import subprocess

    _say("== test ==")
    for label, selection in (("calendar", ["-m", "calendar"]),
                             ("the rest", ["-m", "not calendar"])):
        _say(f"-- {label} --")
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", "--no-header", *selection],
            cwd=Path.cwd(),
        )
        if result.returncode != 0:
            if label == "calendar":
                _say(
                    "Calendar tests failed. Those dates are validated against "
                    "published almanacs: fix the computation, never the test "
                    "(brief 3.6). Not running the remaining suite."
                )
            raise SystemExit(result.returncode)


STAGES = {
    "ingest": ingest,
    "validate": validate,
    "calendar": calendar,
    "backtest": run_backtest,
    "relabel": relabel,
    "bootstrap": run_bootstrap,
    "applicability": run_applicability,
    "sensitivity": run_sensitivity,
    "figures": figures,
    "report": build_report,
    "operations": operations,
    "ui": build_ui,
    "test": test,
}

# `ingest` is deliberately NOT in this list. It writes into data/raw/, and the
# one thing that must never happen by accident is the observation set changing
# underneath a pipeline run. It is a one-time setup step, invoked by name.
ALL_ORDER = [
    "validate",
    "calendar",
    "backtest",
    "relabel",
    "bootstrap",
    "applicability",
    "sensitivity",
    "figures",
    "report",
    "operations",
    "ui",
    "test",
]


# --------------------------------------------------------------------------
# the dispatcher
# --------------------------------------------------------------------------
#
# One implementation, three ways in: `make <target>` delegates to `make.py`,
# `make.py` delegates to here, and the installed `yatra` console script enters
# here directly. The same rule the Makefile is written under (see its header):
# a second copy of this loop would be a second definition of what `all` means,
# and the entry point nobody runs is the one that rots.
#
# What `make.py` keeps for itself is the interpreter check -- re-executing
# inside the project venv, which an installed console script must not do
# because it is already running in the environment it was installed into.

USAGE = "usage: yatra [target ...] [stage options]"

HELP_FLAGS = ("-h", "--help")
VERSION_FLAGS = ("-V", "--version")


def _summary(name: str) -> str:
    """The stage's own first docstring line.

    Read rather than restated, so the help cannot describe a stage as something
    it stopped being. A second list of one-line descriptions is the same shape
    of mistake as a hand-typed README number.
    """
    doc = (STAGES[name].__doc__ or "").strip().splitlines()
    return doc[0].strip() if doc else ""


def usage() -> str:
    """The help text, generated from the stage table it describes."""
    lines = [
        "yatra -- regime-separated forecasting of pilgrimage footfall at",
        "        Shri Mata Vaishno Devi, Katra.",
        "",
        USAGE,
        "",
        "Targets, in the order `all` runs them:",
    ]
    lines += [f"  {name:<14} {_summary(name)}" for name in ALL_ORDER]

    aside = [name for name in STAGES if name not in ALL_ORDER]
    if aside:
        lines += ["", "Not part of `all`, invoked by name:"]
        lines += [f"  {name:<14} {_summary(name)}" for name in aside]

    lines += [
        "",
        "`yatra` with no target runs `all`, the way a bare `make` does. That is",
        "deliberate: `all` is the pipeline, and running it is what this command",
        "is for. It takes a while and it rewrites results/.",
        "",
        "`ingest` is outside `all` on purpose. It writes data/raw/, and the",
        "observation set must not change underneath a run scoring against it.",
        "",
        "Options after a target belong to that stage:",
        "  yatra ingest --inspect published_figures.csv",
        "",
        "  -h, --help     this text",
        "  -V, --version  print the version and exit",
        "",
        "From a checkout, without installing: `python make.py <target>` -- the",
        "same targets, in the same order, through the same code.",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    """Run one or more stages, in the order given. Returns a process exit code.

    Bare, or ``all``, runs :data:`ALL_ORDER`. ``ingest`` is reachable only by
    name: it writes ``data/raw/``, and the observation set must not change
    underneath a run that is scoring against it.
    """
    words = list(sys.argv[1:] if argv is None else argv)

    # A leading flag is not an empty target list. It used to become one, and an
    # empty target list means `all` -- so `yatra --help`, the first thing
    # anybody types after installing, ran the entire pipeline and rewrote
    # results/. Nothing that starts with a dash gets that far now.
    if words and words[0].startswith("-"):
        if words[0] in HELP_FLAGS:
            print(usage())
            return 0
        if words[0] in VERSION_FLAGS:
            print(f"yatra {__version__}")
            return 0
        print(f"unknown option: {words[0]}", file=sys.stderr)
        print(f"{USAGE}\ntry `yatra --help`", file=sys.stderr)
        return 2

    # Everything up to the first flag is a target; the rest belongs to the
    # stage, which reads sys.argv itself. Without this split, `yatra ingest
    # --inspect file.csv` reports "--inspect" as an unknown target.
    cut = next((i for i, word in enumerate(words) if word.startswith("-")), len(words))
    targets = words[:cut] or ["all"]
    if targets == ["all"]:
        targets = list(ALL_ORDER)

    unknown = [target for target in targets if target not in STAGES]
    if unknown:
        print(f"unknown target(s): {unknown}", file=sys.stderr)
        print(f"available: {', '.join(STAGES)}, all", file=sys.stderr)
        return 2

    for target in targets:
        try:
            STAGES[target]()
        except NotImplementedError as exc:
            # A stage that does not exist yet stops the run. `all` does not
            # continue past it and report success for the stages that did work.
            print(f"\n[yatra] STOP at '{target}': {exc}", file=sys.stderr)
            return 3
        except Exception as exc:
            print(f"\n[yatra] FAILED at '{target}': "
                  f"{type(exc).__name__}: {exc}", file=sys.stderr)
            return 1
    return 0
