# Delegates to make.py so that `make all` and `python make.py all` run the same
# code. The owner's machine has no make; do not add logic here that make.py does
# not also have, or the two entry points will diverge and the one nobody runs
# will rot.

PYTHON ?= python

.PHONY: all ingest validate calendar backtest relabel bootstrap applicability sensitivity figures report operations test clean

all:
	$(PYTHON) make.py all

# Not part of `all`: it writes data/raw/, which must never change underneath a
# pipeline run. `make ingest INSPECT=path/to/file.csv` describes a file first.
ingest:
	$(PYTHON) make.py ingest $(if $(INSPECT),--inspect $(INSPECT),)

validate:
	$(PYTHON) make.py validate

calendar:
	$(PYTHON) make.py calendar

backtest:
	$(PYTHON) make.py backtest

# `relabel` attaches regime labels to forecasts already scored. It is a join,
# not a refit: no model ever sees a label (CLAUDE.md 3.4).
relabel:
	$(PYTHON) make.py relabel

bootstrap:
	$(PYTHON) make.py bootstrap

applicability:
	$(PYTHON) make.py applicability

sensitivity:
	$(PYTHON) make.py sensitivity

figures:
	$(PYTHON) make.py figures

report:
	$(PYTHON) make.py report

operations:
	$(PYTHON) make.py operations

test:
	$(PYTHON) make.py test

# Deliberately does NOT remove results/metrics.csv. That file is the artefact
# every README number traces back to, it is committed, and regenerating it
# requires the full data set. Deleting it on `make clean` would make the README
# unverifiable until someone with the data re-ran the backtest.
clean:
	$(PYTHON) -c "import shutil,pathlib; [shutil.rmtree(p, ignore_errors=True) for p in pathlib.Path('.').rglob('__pycache__')]"
	$(PYTHON) -c "import shutil; shutil.rmtree('.pytest_cache', ignore_errors=True)"
