"""Regression tests for the calendar-routing failure mode.

The history: routing keyed off a ``_cal`` name suffix. A rename broke it
silently, the ablation arm trained without the features it existed to test, and
the run reported a clean null result. Nothing crashed, so nothing was noticed.

These tests exist so that the same class of change fails loudly. They are cheap
and they guard a failure that costs an entire experiment.
"""

from __future__ import annotations

import pytest
import yaml

from yatra import backtest, models
from yatra.errors import ConfigError


def test_every_needs_calendar_name_resolves():
    """A rename that orphans the set is caught here."""
    unknown = sorted(models.NEEDS_CALENDAR - set(models.REGISTRY))
    assert not unknown, f"NEEDS_CALENDAR names unregistered models: {unknown}"


def test_set_and_flags_agree_in_both_directions():
    flagged = {name for name, spec in models.REGISTRY.items() if spec.needs_calendar}
    assert flagged == set(models.NEEDS_CALENDAR)


def test_the_set_is_not_empty():
    """An empty set would silently disable the entire calendar ablation."""
    assert models.NEEDS_CALENDAR, (
        "NEEDS_CALENDAR is empty, so no model receives calendar features and the "
        "calendar layer is untested by construction."
    )


def test_routing_is_not_derived_from_the_name():
    """The specific mechanism that failed before must not be back.

    If routing were suffix-based, renaming a model away from ``_cal`` would move
    it out of the set. Here the set is a literal, so a name without the suffix
    can still be routed -- and that is what this asserts.
    """
    for name in models.NEEDS_CALENDAR:
        spec = models.REGISTRY[name]
        assert spec.needs_calendar, (
            f"'{name}' is in NEEDS_CALENDAR but its registry flag is False -- "
            "routing has drifted back to being derived rather than declared."
        )

    source = (models.__file__)
    text = open(source, encoding="utf-8").read()
    assert 'endswith("_cal")' not in text and ".endswith('_cal')" not in text, (
        "Suffix-based calendar routing has reappeared in models.py."
    )


def test_a_rename_trips_the_import_time_check(monkeypatch):
    """Simulate the exact historical break: model renamed, set left stale."""
    surviving = {n: s for n, s in models.REGISTRY.items() if n not in models.NEEDS_CALENDAR}
    monkeypatch.setattr(models, "REGISTRY", surviving)
    with pytest.raises(ConfigError, match="not registered"):
        models._validate_registry()


def test_a_new_flagged_model_left_out_of_the_set_is_caught(monkeypatch):
    """The opposite drift: flagged in the registry, forgotten in the set."""
    extended = dict(models.REGISTRY)
    extended["hypothetical_arm"] = models.ModelSpec(
        name="hypothetical_arm",
        fn=lambda train, horizons, calendar: None,
        needs_calendar=True,
        description="fixture",
    )
    monkeypatch.setattr(models, "REGISTRY", extended)
    with pytest.raises(ConfigError, match="flagged but not in set"):
        models._validate_registry()


def test_backtest_config_only_names_registered_models():
    """A typo in the config must not silently shrink the model set."""
    config = backtest.load_config("experiments/configs/backtest.yaml")
    unknown = sorted(set(config.model_names) - set(models.REGISTRY))
    assert not unknown, f"backtest.yaml names unregistered models: {unknown}"


def test_every_declared_ablation_has_both_arms_configured():
    """An arm is only interpretable against its twin.

    If a control were dropped from the config, the treatment arm would still
    produce a number -- just an uninterpretable one. The pairs come from
    models.ABLATIONS rather than being listed here, so declaring a new pair
    brings it under this check automatically.
    """
    config = backtest.load_config("experiments/configs/backtest.yaml")
    configured = set(config.model_names)
    for ablation in models.ABLATIONS:
        if ablation.treatment in configured:
            assert ablation.control in configured, (
                f"'{ablation.treatment}' is configured without its control "
                f"'{ablation.control}'. The pair is the ablation; alone, the arm "
                "measures nothing."
            )


def test_every_ablation_resolves_in_the_registry():
    for ablation in models.ABLATIONS:
        assert ablation.treatment in models.REGISTRY, ablation.name
        assert ablation.control in models.REGISTRY, ablation.name
        assert ablation.treatment != ablation.control, ablation.name


def test_the_calendar_ablation_straddles_the_routing_set():
    """Both arms fed, or neither, is the historical bug wearing a new hat."""
    calendar = next(a for a in models.ABLATIONS if a.name == "calendar")
    assert calendar.treatment in models.NEEDS_CALENDAR
    assert calendar.control not in models.NEEDS_CALENDAR


def test_an_ablation_pointing_at_a_renamed_model_is_caught(monkeypatch):
    surviving = {n: s for n, s in models.REGISTRY.items()
                 if n != models.ABLATIONS[0].control}
    monkeypatch.setattr(models, "REGISTRY", surviving)
    with pytest.raises(ConfigError, match="unregistered model"):
        models._validate_ablations()


def test_an_ablation_against_itself_is_refused(monkeypatch):
    """The degenerate pair reports zero, and zero looks exactly like a null result."""
    twin = models.Ablation(
        name="degenerate", treatment="naive", control="naive",
        varies="nothing at all", question="does a model beat itself?",
    )
    monkeypatch.setattr(models, "ABLATIONS", (twin,))
    with pytest.raises(ConfigError, match="with itself"):
        models._validate_ablations()


def test_a_calendar_ablation_with_both_arms_fed_is_refused(monkeypatch):
    """The exact historical failure: the arm trains like its control."""
    monkeypatch.setattr(models, "NEEDS_CALENDAR", frozenset({"sarimax_cal", "sarima"}))
    with pytest.raises(ConfigError, match="straddle"):
        models._validate_ablations()


def test_calendar_config_features_are_declared():
    with open("experiments/configs/calendar.yaml", encoding="utf-8") as handle:
        config = yaml.safe_load(handle)
    assert config.get("features"), "calendar.yaml declares no features."
    assert config.get("festivals"), "calendar.yaml declares no festivals."
