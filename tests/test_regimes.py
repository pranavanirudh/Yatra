"""Shock windows: citation enforcement, disjointness, and target-month labelling."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
import yaml

from yatra import regimes
from yatra.errors import ConfigError, MissingCitation

GOOD_SOURCE = {
    "publisher": "Fixture Publisher",
    "title": "Fixture report",
    "url": "https://example.invalid/a",
    "accessed": "2026-08-18",
}

REAL_CONFIG = Path("experiments/configs/shocks.yaml")


def write_config(tmp_path: Path, windows: list[dict]) -> Path:
    path = tmp_path / "shocks.yaml"
    path.write_text(yaml.safe_dump({"schema_version": 1, "windows": windows}),
                    encoding="utf-8")
    return path


def window(**overrides) -> dict:
    base = {
        "id": "w1",
        "label": "Fixture window",
        "start": "2020-03",
        "end": "2020-06",
        "rationale": "Fixture rationale, long enough to be non-empty.",
        "source": dict(GOOD_SOURCE),
    }
    base.update(overrides)
    return base


# --- citation enforcement ------------------------------------------------


def test_window_without_source_raises(tmp_path: Path):
    spec = window()
    del spec["source"]
    with pytest.raises(MissingCitation) as excinfo:
        regimes.load_windows(write_config(tmp_path, [spec]))
    assert "unfalsifiable" in str(excinfo.value)


@pytest.mark.parametrize("field", ["publisher", "title", "url", "accessed"])
def test_source_missing_any_required_field_raises(tmp_path: Path, field: str):
    source = dict(GOOD_SOURCE)
    del source[field]
    with pytest.raises(MissingCitation, match=field):
        regimes.load_windows(write_config(tmp_path, [window(source=source)]))


def test_blank_field_counts_as_missing(tmp_path: Path):
    source = dict(GOOD_SOURCE, url="   ")
    with pytest.raises(MissingCitation, match="url"):
        regimes.load_windows(write_config(tmp_path, [window(source=source)]))


def test_window_without_rationale_raises(tmp_path: Path):
    with pytest.raises(ConfigError, match="rationale"):
        regimes.load_windows(write_config(tmp_path, [window(rationale="")]))


# --- structural checks ---------------------------------------------------


def test_empty_window_list_raises(tmp_path: Path):
    path = tmp_path / "shocks.yaml"
    path.write_text(yaml.safe_dump({"schema_version": 1, "windows": []}), encoding="utf-8")
    with pytest.raises(ConfigError, match="vacuous"):
        regimes.load_windows(path)


def test_reversed_window_raises(tmp_path: Path):
    spec = window(start="2020-06", end="2020-03")
    with pytest.raises(ConfigError, match="precedes start"):
        regimes.load_windows(write_config(tmp_path, [spec]))


def test_overlapping_windows_raise(tmp_path: Path):
    a = window(id="a", start="2020-01", end="2020-06")
    b = window(id="b", start="2020-05", end="2020-09")
    with pytest.raises(ConfigError, match="overlap"):
        regimes.load_windows(write_config(tmp_path, [a, b]))


def test_adjacent_windows_are_allowed(tmp_path: Path):
    a = window(id="a", start="2020-01", end="2020-06")
    b = window(id="b", start="2020-07", end="2020-09")
    assert len(regimes.load_windows(write_config(tmp_path, [a, b]))) == 2


def test_n_months_is_inclusive(tmp_path: Path):
    spec = window(start="2020-03", end="2020-06")
    assert regimes.load_windows(write_config(tmp_path, [spec]))[0].n_months == 4


# --- labelling -----------------------------------------------------------


def test_labels_by_target_month(tmp_path: Path):
    windows = regimes.load_windows(write_config(tmp_path, [window()]))
    months = pd.period_range("2020-01", "2020-08", freq="M")
    labels = regimes.label_months(months, windows)

    assert labels.loc[pd.Period("2020-02", "M"), "regime"] == regimes.CLEAN
    assert labels.loc[pd.Period("2020-03", "M"), "regime"] == regimes.SHOCK
    assert labels.loc[pd.Period("2020-06", "M"), "regime"] == regimes.SHOCK
    assert labels.loc[pd.Period("2020-07", "M"), "regime"] == regimes.CLEAN
    assert labels.loc[pd.Period("2020-04", "M"), "shock_window"] == "w1"
    assert pd.isna(labels.loc[pd.Period("2020-07", "M"), "shock_window"])


def test_label_months_rejects_non_monthly_index(tmp_path: Path):
    windows = regimes.load_windows(write_config(tmp_path, [window()]))
    with pytest.raises(ConfigError, match="monthly PeriodIndex"):
        regimes.label_months(pd.period_range("2020-01", "2020-08", freq="D"), windows)


# --- the committed config ------------------------------------------------


def test_committed_config_loads_with_every_citation_present():
    windows = regimes.load_windows(REAL_CONFIG)
    assert len(windows) >= 3
    for w in windows:
        assert w.source.publisher and w.source.url and w.source.accessed
        assert w.rationale
        assert "http" in w.source.url


def test_committed_config_windows_are_disjoint_and_ordered():
    windows = sorted(regimes.load_windows(REAL_CONFIG), key=lambda w: w.start)
    for earlier, later in zip(windows, windows[1:]):
        assert later.start > earlier.end


def test_unverified_flags_are_surfaced():
    """Not a failure -- but the count must be reachable so report.py can warn."""
    windows = regimes.load_windows(REAL_CONFIG)
    pending = regimes.unverified(windows)
    assert all(not w.verified for w in pending)
    assert len(pending) <= len(windows)
