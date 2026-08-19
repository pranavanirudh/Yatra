"""What the calendar layer contains has to be visible, not implied.

`sarimax_cal` wins the clean regime and is one arm of the ablation table, and
"the calendar layer" reads like an almanac. It is five festivals. A reader
judging either result needs to know which five, and under which civil-day
rule -- the choice that decides more dates than any disagreement between
ephemerides does.

Constraint 6 forbids a date table in `src/`, so this section is generated from
the config that produced the dates and from the dates themselves. These tests
also assert that nothing here reintroduces one.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
import yaml

from yatra import report

CONFIG = {
    "backend": "probe_backend",
    "ephemeris": {"kernel": "probe.bsp"},
    "ayanamsa": "lahiri",
    "lunar_month_scheme": "purnimanta",
    "location": {"name": "Probe Location"},
    "range": {"start": "1985-01-01", "end": "2030-12-31"},
    "festivals": [
        {
            "id": "probe_one",
            "label": "Probe One",
            "rule": {"month": "chaitra", "paksha": "shukla", "tithi": 1,
                     "observance": "sunrise"},
            "duration_days": 9,
        },
        {
            "id": "probe_two",
            "label": "Probe Two",
            "rule": {"month": "kartika", "paksha": "krishna", "tithi": 30,
                     "observance": "pradosha"},
            "duration_days": 1,
        },
    ],
    "features": ["festival_days", "drift_column"],
}


def _paths(tmp_path: Path, calendar: pd.DataFrame | None = None,
           config: dict | None = None) -> tuple[Path, Path, Path]:
    config_path = tmp_path / "calendar.yaml"
    config_path.write_text(yaml.safe_dump(config or CONFIG), encoding="utf-8")

    festivals_path = tmp_path / "festivals.csv"
    pd.DataFrame({"date": ["1985-02-17", "1985-03-22", "1985-04-01"]}).to_csv(
        festivals_path, index=False)

    calendar_path = tmp_path / "calendar.csv"
    if calendar is None:
        calendar = pd.DataFrame(
            {"month": ["2000-01", "2000-02", "2000-03"],
             "festival_days": [3, 0, 0],
             "drift_column": [11.2, 12.7, 14.1]}
        )
    calendar.to_csv(calendar_path, index=False)
    return config_path, festivals_path, calendar_path


def test_the_festivals_and_their_day_rules_are_named(tmp_path):
    text = "\n".join(report._calendar(*_paths(tmp_path)))

    assert "**2 festivals, not a general almanac.**" in text
    assert "| Probe One | chaitra shukla 1 | sunrise | 9 days |" in text
    assert "| Probe Two | kartika krishna 30 | pradosha | 1 day |" in text
    assert "`probe_backend` (probe.bsp)" in text
    assert "1985-01-01 to 2030-12-31" in text
    assert "| Festival dates resolved | 3 |" in text


def test_a_column_that_stays_live_in_quiet_months_is_named(tmp_path):
    """The claim has to be derived. A drift term keeps moving with no festival."""
    text = "\n".join(report._calendar(*_paths(tmp_path)))

    assert "**1** carry at least one festival day" in text
    assert "comes from `drift_column`" in text
    assert "identical inputs" not in text


def test_all_columns_going_quiet_is_reported_as_identical_inputs(tmp_path):
    calendar = pd.DataFrame(
        {"month": ["2000-01", "2000-02"],
         "festival_days": [3, 0],
         "drift_column": [11.2, 0.0]}
    )
    text = "\n".join(report._calendar(*_paths(tmp_path, calendar=calendar)))

    assert "every calendar column is zero" in text
    assert "identical inputs" in text


def test_a_config_without_festivals_renders_nothing(tmp_path):
    stripped = {k: v for k, v in CONFIG.items() if k != "festivals"}
    assert report._calendar(*_paths(tmp_path, config=stripped)) == []


def test_a_missing_config_renders_nothing_rather_than_raising(tmp_path):
    assert report._calendar(tmp_path / "absent.yaml",
                            tmp_path / "absent.csv",
                            tmp_path / "also-absent.csv") == []


def test_the_section_survives_missing_artefacts(tmp_path):
    """The config alone is enough for the festival table; counts are optional."""
    config_path, _, _ = _paths(tmp_path)
    text = "\n".join(report._calendar(config_path,
                                      tmp_path / "absent.csv",
                                      tmp_path / "also-absent.csv"))
    assert "| Probe One |" in text
    assert "Festival dates resolved" not in text
    assert "carry at least one festival day" not in text


def test_no_date_table_is_smuggled_into_the_report_module():
    """Constraint 6, applied to the module that describes the calendar."""
    import re

    text = Path(report.__file__).read_text(encoding="utf-8")
    dates = re.findall(r"\b(19|20)\d{2}-\d{2}-\d{2}\b", text)
    assert not dates, f"report.py contains literal dates: {dates}"


def test_the_section_reaches_the_rendered_readme():
    if not Path("results/metrics.csv").exists():
        pytest.skip("no committed metrics; run `make backtest`")
    body = report.render()
    assert "### What the calendar layer contains" in body

    config = yaml.safe_load(
        Path("experiments/configs/calendar.yaml").read_text(encoding="utf-8"))
    for entry in config["festivals"]:
        assert entry["label"] in body
        assert entry["rule"]["observance"] in body
