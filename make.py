#!/usr/bin/env python
"""Task runner. `python make.py <target>`.

Exists because there is no `make` on the owner's Windows machine. The Makefile
in this directory delegates here, so both entry points run identical code and
cannot drift apart.

Targets: ingest, validate, calendar, backtest, bootstrap, figures, report,
operations, test, all.

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
    _check_interpreter()

    from yatra import cli

    # Everything up to the first flag is a target; the rest belongs to the
    # stage, which reads sys.argv itself. Without this split, `make.py ingest
    # --inspect file.csv` reports "--inspect" as an unknown target.
    words = argv[1:]
    cut = next((i for i, w in enumerate(words) if w.startswith("-")), len(words))
    targets = words[:cut] or ["all"]
    if targets == ["all"]:
        targets = cli.ALL_ORDER

    unknown = [t for t in targets if t not in cli.STAGES]
    if unknown:
        print(f"unknown target(s): {unknown}", file=sys.stderr)
        print(f"available: {', '.join(cli.STAGES)}, all", file=sys.stderr)
        return 2

    for target in targets:
        try:
            cli.STAGES[target]()
        except NotImplementedError as exc:
            # A stage that does not exist yet stops the run. `all` does not
            # continue past it and report success for the stages that did work.
            print(f"\n[make.py] STOP at '{target}': {exc}", file=sys.stderr)
            return 3
        except Exception as exc:
            print(f"\n[make.py] FAILED at '{target}': "
                  f"{type(exc).__name__}: {exc}", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
