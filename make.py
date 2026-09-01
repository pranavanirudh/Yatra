#!/usr/bin/env python
"""Task runner. `python make.py <target>`.

Exists because there is no `make` on the owner's Windows machine. The Makefile
in this directory delegates here, so both entry points run identical code and
cannot drift apart.

Targets: ingest, validate, calendar, backtest, bootstrap, figures, report,
operations, ui, test, all.

`ingest` is not part of `all` -- it writes data/raw/ and is invoked by name.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))


def _venv_python() -> Path | None:
    for candidate in (ROOT / ".venv/Scripts/python.exe", ROOT / ".venv/bin/python"):
        if candidate.exists():
            return candidate
    return None


def _check_interpreter() -> None:
    """Re-exec inside the project venv if we were started outside it.

    Running the pipeline against whatever interpreter happened to be on PATH is
    how two machines end up with different statsmodels and a MASE that differs
    in the third decimal for no reason anybody can find later.
    """
    venv = _venv_python()
    if venv is None:
        return
    current = Path(sys.executable).resolve()
    if current == venv.resolve():
        return
    import subprocess

    print(f"[make.py] re-executing under {venv}", flush=True)
    raise SystemExit(subprocess.run([str(venv), __file__, *sys.argv[1:]]).returncode)


def main(argv: list[str]) -> int:
    """Interpreter check, then hand the targets to the one dispatcher.

    The target parsing and the stage loop live in `yatra.cli.main`, which the
    installed `yatra` console script also enters. This file owns exactly one
    thing the console script must not have: the re-exec into the project venv.
    """
    _check_interpreter()

    from yatra import cli

    return cli.main(argv[1:])


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
