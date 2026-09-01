"""One dispatcher, three ways in.

`make <target>` delegates to `make.py`, `make.py` delegates to
`yatra.cli.main`, and the installed `yatra` console script enters it directly.
The Makefile's own header states the rule these tests enforce: do not put logic
in one entry point that the others do not have, because the two will diverge
and the one nobody runs is the one that rots.

A second copy of the stage loop would be a second definition of what `all`
means. It would also be invisible: both copies would run, both would print the
same lines, and the difference would surface as a stage that silently stopped
being part of a pipeline somebody else's machine still ran.
"""

from __future__ import annotations

import importlib.util
import sys
import tomllib
from pathlib import Path

import pytest

from yatra import cli

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def pyproject() -> dict:
    return tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))


@pytest.fixture
def make_py(monkeypatch):
    """`make.py`, imported as a module, with the venv re-exec disabled.

    Left in place, `_check_interpreter` would re-run make.py as a subprocess
    whenever the suite is driven by an interpreter that is not the project
    venv -- which, for a test that passes a target, means running the pipeline
    for real from inside pytest.
    """
    spec = importlib.util.spec_from_file_location("_make_under_test", ROOT / "make.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "_check_interpreter", lambda: None)
    return module


@pytest.fixture
def recorded(monkeypatch) -> list[str]:
    """Every stage replaced by a recorder, so dispatch can be driven for real."""
    calls: list[str] = []
    monkeypatch.setattr(
        cli, "STAGES",
        {name: (lambda n=name: calls.append(n)) for name in cli.STAGES},
    )
    return calls


# --------------------------------------------------------------------------
# the console script
# --------------------------------------------------------------------------

def test_the_console_script_is_declared_and_points_at_the_dispatcher(pyproject):
    scripts = pyproject["project"].get("scripts", {})
    assert scripts.get("yatra") == "yatra.cli:main", (
        "pyproject must ship a `yatra` console script entering yatra.cli:main. "
        f"It declares {scripts!r}."
    )
    assert callable(cli.main)


def test_the_console_script_runs_with_no_arguments_at_all(recorded, monkeypatch):
    """Installed, it is called as `main()` and reads sys.argv itself."""
    monkeypatch.setattr(sys, "argv", ["yatra", "validate"])
    assert cli.main() == 0
    assert recorded == ["validate"]


# --------------------------------------------------------------------------
# every stage stays reachable
# --------------------------------------------------------------------------

@pytest.mark.parametrize("stage", sorted(cli.STAGES))
def test_every_stage_is_reachable_from_the_cli(stage, recorded):
    assert cli.main([stage]) == 0
    assert recorded == [stage], (
        f"`yatra {stage}` did not run the {stage} stage. It is in cli.STAGES, so "
        "it is a documented target, and a target that cannot be invoked is a "
        "pipeline step nobody can run without importing the module by hand."
    )


@pytest.mark.parametrize("stage", sorted(cli.STAGES))
def test_every_stage_is_reachable_from_make_py(stage, recorded, make_py):
    assert make_py.main(["make.py", stage]) == 0
    assert recorded == [stage], (
        f"`python make.py {stage}` did not run the {stage} stage, though "
        "`yatra` does. The two entry points have diverged."
    )


def test_the_two_entry_points_agree_on_what_all_means(recorded, make_py):
    assert cli.main(["all"]) == 0
    through_cli = list(recorded)

    recorded.clear()
    assert make_py.main(["make.py"]) == 0
    through_make = list(recorded)

    assert through_cli == cli.ALL_ORDER, (
        "`yatra all` did not run ALL_ORDER, in order. The stage order is the "
        "dependency order: a stage running before the artefact it reads was "
        "written renders the previous run's numbers."
    )
    assert through_make == through_cli, (
        f"`make.py` runs {through_make} and `yatra` runs {through_cli}."
    )


def test_ingest_is_reachable_by_name_and_never_by_all(recorded):
    """CLAUDE.md 5: `ingest` writes data/raw/ and is not part of `all`."""
    assert "ingest" in cli.STAGES
    assert "ingest" not in cli.ALL_ORDER

    cli.main(["all"])
    assert "ingest" not in recorded, (
        "`all` ran ingest. The observation set must not change underneath a run "
        "that is scoring against it."
    )

    recorded.clear()
    assert cli.main(["ingest"]) == 0
    assert recorded == ["ingest"]


# --------------------------------------------------------------------------
# what the dispatcher does with the rest of the command line
# --------------------------------------------------------------------------

def test_flags_belong_to_the_stage_and_are_not_read_as_targets(recorded):
    """`yatra ingest --inspect file.csv` describes a file; it names one target."""
    assert cli.main(["ingest", "--inspect", "somefile.csv"]) == 0
    assert recorded == ["ingest"]


def test_an_unknown_target_is_refused_and_names_what_exists(recorded, capsys):
    assert cli.main(["backtset"]) == 2
    assert not recorded, "a run began before the target was checked"
    assert "backtset" in capsys.readouterr().err


def test_a_stage_that_is_not_built_stops_the_run(monkeypatch, capsys):
    """`all` must not continue past a missing stage and report success."""
    def unbuilt() -> None:
        raise NotImplementedError("phase 4 builds this")

    monkeypatch.setattr(
        cli, "STAGES",
        {**{name: (lambda: None) for name in cli.STAGES}, "figures": unbuilt},
    )
    assert cli.main(["all"]) == 3
    assert "STOP at 'figures'" in capsys.readouterr().err


def test_a_failing_stage_stops_the_run_and_names_itself(monkeypatch, capsys):
    def broken() -> None:
        raise ValueError("the months are not contiguous")

    monkeypatch.setattr(
        cli, "STAGES",
        {**{name: (lambda: None) for name in cli.STAGES}, "validate": broken},
    )
    assert cli.main(["all"]) == 1
    error = capsys.readouterr().err
    assert "FAILED at 'validate'" in error
    assert "the months are not contiguous" in error


def test_make_py_owns_the_interpreter_check_and_nothing_else(make_py):
    """The one thing that must not be shared.

    An installed console script is already running in the environment it was
    installed into; re-executing it inside `.venv` would be wrong there, and is
    right in `make.py`, which is run from a checkout by whatever interpreter is
    on PATH. Everything else has to be common, so make.py must hold no second
    copy of the stage loop.
    """
    source = (ROOT / "make.py").read_text(encoding="utf-8")
    assert "_check_interpreter" in source
    assert "cli.main(" in source, "make.py no longer delegates to the dispatcher"
    assert "STAGES[" not in source, (
        "make.py dispatches stages itself again. That is a second definition of "
        "what a target is, and it will drift from the one the console script uses."
    )
