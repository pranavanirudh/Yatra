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


# --------------------------------------------------------------------------
# flags, which used to mean "run everything"
# --------------------------------------------------------------------------
#
# `yatra --help` ran the entire pipeline. The flag split put the cut at index
# zero, an empty target list means `all`, and `all` rewrites results/ -- so the
# first thing anybody types after installing was the most destructive thing the
# command can do. These tests are about the class, not the one flag: nothing
# starting with a dash may reach a stage.

LEADING_FLAGS = ("-h", "--help", "-V", "--version", "--inspect", "-x",
                 "--dry-run", "--", "-")


@pytest.mark.parametrize("flag", LEADING_FLAGS)
def test_no_leading_flag_ever_starts_the_pipeline(flag, recorded):
    cli.main([flag])
    assert not recorded, (
        f"`yatra {flag}` ran {recorded}. A flag is not an empty target list, "
        "and an empty target list is the whole pipeline."
    )


@pytest.mark.parametrize("flag", ["-h", "--help"])
def test_help_prints_usage_and_exits_zero(flag, recorded, capsys):
    assert cli.main([flag]) == 0
    assert not recorded
    assert cli.USAGE in capsys.readouterr().out


def test_the_help_describes_every_stage_out_of_the_stage_table(capsys):
    """Generated from STAGES, so it cannot describe a stage that moved.

    A hand-typed target list is the same shape of mistake as a hand-typed
    README number: correct when written, silently wrong after a rename.
    """
    assert cli.main(["--help"]) == 0
    text = capsys.readouterr().out
    for name in cli.STAGES:
        assert name in text, f"the help does not mention the {name} stage"
        summary = cli._summary(name)
        assert summary and summary in text, (
            f"the help does not carry {name}'s own one-line description"
        )


def test_the_help_says_that_a_bare_invocation_runs_everything(capsys):
    """It is deliberate, so it must not be a surprise."""
    assert cli.main(["--help"]) == 0
    text = capsys.readouterr().out
    assert "no target runs `all`" in text
    assert "rewrites results/" in text
    assert "make.py" in text, (
        "the help does not mention the checkout entry point, so a reader "
        "without an install is told nothing"
    )


def test_the_help_marks_ingest_as_outside_all(capsys):
    assert cli.main(["--help"]) == 0
    text = capsys.readouterr().out
    assert "Not part of `all`" in text
    assert "data/raw/" in text


def test_version_prints_the_package_version_and_runs_nothing(recorded, capsys):
    from yatra import __version__

    assert cli.main(["--version"]) == 0
    assert not recorded
    assert __version__ in capsys.readouterr().out


def test_an_unknown_flag_is_refused_and_points_at_the_help(recorded, capsys):
    assert cli.main(["--inspect", "figures.csv"]) == 2
    assert not recorded, "a stage ran on an invocation that named no target"
    error = capsys.readouterr().err
    assert "--inspect" in error
    assert "--help" in error


def test_a_bare_invocation_still_runs_all(recorded):
    """The deliberate half of the behaviour, kept: `yatra` is `make`."""
    assert cli.main([]) == 0
    assert recorded == cli.ALL_ORDER


def test_make_py_gets_the_same_flag_handling(make_py, recorded, capsys):
    assert make_py.main(["make.py", "--help"]) == 0
    assert not recorded, "`python make.py --help` ran the pipeline"
    assert cli.USAGE in capsys.readouterr().out


def test_the_declared_version_and_the_reported_version_are_the_same(pyproject):
    """`pyproject` packages one number and `__init__` reports another.

    They drifted, and the drift surfaced as `yatra --version` printing a
    version the repository's own tags contradicted -- the reported version was
    behind the released one, so the first question anybody asks a CLI got an
    answer that disagreed with `git tag`. Nothing coupled the two, so nothing
    failed. Now something does.
    """
    from yatra import __version__

    declared = pyproject["project"]["version"]
    assert declared == __version__, (
        f"pyproject declares {declared} and yatra.__version__ reports "
        f"{__version__}. `yatra --version` prints the second, packaging metadata "
        "carries the first, and a reader has no way to tell which is the "
        "release they are holding."
    )
