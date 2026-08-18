"""The calendar layer, validated against published almanacs.

**These reference dates are the specification, not the output.** Constraint 6 is
that festival dates are computed and never tabulated, and that if a test here
fails the computation is wrong, not the test. So the dates below must be read
back against a published panchang, never adjusted to match whatever
``panchanga.py`` currently returns. Editing a date in this file to make a test
pass converts the whole calendar layer into an elaborate way of agreeing with
itself.

**Provenance, stated honestly.** The dates were written down from the widely
published Drik Panchang / almanac figures for Katra's timezone and then checked
against the computation, which reproduced all of them. Agreement across forty
independent dates is strong evidence that both are right, but it is not the same
as an owner having verified each against a printed source. Until that happens,
treat this file as *the strongest available* check rather than as settled --
which is why the contested years are called out individually below rather than
being quietly dropped.

The tests are marked ``calendar`` and run first in ``make test``: their failure
invalidates every ablation result downstream, so there is no point running the
rest until they pass.
"""

from __future__ import annotations

import datetime as dt
import re
from pathlib import Path

import numpy as np
import pytest
import yaml

from yatra import calendarfeat, ephemeris, panchanga
from yatra.errors import ConfigError, EphemerisUnavailable

pytestmark = pytest.mark.calendar

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src" / "yatra"
CONFIG_PATH = ROOT / "experiments" / "configs" / "calendar.yaml"

# The window the reference dates cover. Kept narrow because every one of these
# dates is solved for from the ephemeris and the whole span costs real seconds.
FIRST_YEAR, LAST_YEAR = 2016, 2025


def _date(text: str) -> dt.date:
    return dt.date.fromisoformat(text)


# --------------------------------------------------------------------------
# The published dates. One block per festival, so that a disagreement points at
# a rule rather than at "the calendar".
# --------------------------------------------------------------------------

SHARAD_NAVRATRI = [  # Ghatasthapana, day 1
    "2016-10-01", "2017-09-21", "2018-10-10", "2019-09-29", "2020-10-17",
    "2021-10-07", "2022-09-26", "2023-10-15", "2024-10-03", "2025-09-22",
]

CHAITRA_NAVRATRI = [
    "2016-04-08", "2017-03-29", "2018-03-18", "2019-04-06", "2020-03-25",
    "2021-04-13", "2022-04-02", "2023-03-22", "2024-04-09", "2025-03-30",
]

MAHA_SHIVARATRI = [
    "2016-03-07", "2017-02-24", "2018-02-13", "2019-03-04", "2020-02-21",
    "2021-03-11", "2022-03-01", "2023-02-18", "2024-03-08", "2025-02-26",
]

DIWALI = [  # Lakshmi Puja
    "2016-10-30", "2017-10-19", "2018-11-07", "2019-10-27", "2020-11-14",
    "2021-11-04", "2022-10-24", "2023-11-12", "2024-10-31", "2025-10-20",
]

# Raksha Bandhan is listed with two years omitted, deliberately and visibly.
# In 2022 and 2023 the Purnima at sunrise fell on a day whose morning was under
# Bhadra, and observance was widely moved off it. Bhadra is a karana rule this
# module does not implement, so those two years are genuinely outside what the
# declared `observance: sunrise` rule claims to decide. Omitting them is honest;
# adding a hardcoded exception for them would be the date table constraint 6
# forbids. If Bhadra is implemented later, add them back.
RAKSHA_BANDHAN = [
    "2016-08-18", "2017-08-07", "2018-08-26", "2019-08-15", "2020-08-03",
    "2021-08-22", "2024-08-19", "2025-08-09",
]

REFERENCE = {
    "sharad_navratri": SHARAD_NAVRATRI,
    "chaitra_navratri": CHAITRA_NAVRATRI,
    "maha_shivaratri": MAHA_SHIVARATRI,
    "diwali": DIWALI,
    "raksha_bandhan": RAKSHA_BANDHAN,
}


# --------------------------------------------------------------------------
# Fixtures. The ephemeris is expensive, so it is built once per session.
# --------------------------------------------------------------------------


@pytest.fixture(scope="session")
def config() -> dict:
    return yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def backend(config):
    try:
        return ephemeris.build(config)
    except EphemerisUnavailable as exc:
        pytest.skip(f"configured ephemeris backend unavailable: {exc}")


@pytest.fixture(scope="session")
def computed(backend, config) -> panchanga.Panchanga:
    return panchanga.compute(
        backend, config, dt.date(FIRST_YEAR, 1, 1), dt.date(LAST_YEAR, 12, 31)
    )


@pytest.fixture(scope="session")
def by_festival(computed) -> dict[str, list[dt.date]]:
    found: dict[str, list[dt.date]] = {}
    for occurrence in computed.occurrences:
        found.setdefault(occurrence.festival_id, []).append(occurrence.start_date)
    return {key: sorted(value) for key, value in found.items()}


# --------------------------------------------------------------------------
# The validation that matters.
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("festival_id", "published"),
    [(key, value) for key, value in REFERENCE.items()],
    ids=list(REFERENCE),
)
def test_matches_published_almanac(by_festival, festival_id, published):
    """Computed dates must equal the published ones. Fix the computation, not this."""
    computed_dates = by_festival[festival_id]
    expected = [_date(text) for text in published]
    missing = [d for d in expected if d not in computed_dates]
    assert not missing, (
        f"{festival_id}: computed dates do not include published {missing}. "
        f"Computed in range: {computed_dates}. The computation is wrong -- do "
        "not edit the published dates to match it (brief 3.6)."
    )


def test_each_festival_occurs_once_a_year(by_festival):
    """A missing or doubled occurrence would distort every feature that counts days."""
    for festival_id, dates in by_festival.items():
        years = [d.year for d in dates]
        duplicated = {y for y in years if years.count(y) > 1}
        assert not duplicated, f"{festival_id} resolved twice in {sorted(duplicated)}"
        assert len(years) == LAST_YEAR - FIRST_YEAR + 1, (
            f"{festival_id} resolved {len(years)} times over "
            f"{LAST_YEAR - FIRST_YEAR + 1} years: {dates}"
        )


def test_diwali_2024_uses_the_evening_rule(by_festival):
    """The near-tie the observance mechanism exists for.

    In 2024 Amavasya began on the afternoon of 31 October and ran past the
    sunrise of 1 November. A sunrise rule dates Lakshmi Puja to 1 November;
    almanacs place it on 31 October, because the puja is a pradosha observance
    and Amavasya covered that evening. If this test fails while the rest pass,
    the observance mechanism has been bypassed rather than the astronomy broken.
    """
    assert dt.date(2024, 10, 31) in by_festival["diwali"]


def test_shivaratri_uses_the_midnight_rule(by_festival):
    """Shivaratri under a plain sunrise rule lands a day late in several years."""
    assert dt.date(2020, 2, 21) in by_festival["maha_shivaratri"]
    assert dt.date(2025, 2, 26) in by_festival["maha_shivaratri"]


# --------------------------------------------------------------------------
# Structural guards: the properties that keep the dates *computed*.
# --------------------------------------------------------------------------


def test_no_date_table_in_src():
    """Constraint 6, mechanically. No literal calendar dates anywhere in src/."""
    pattern = re.compile(r"\b(19|20)\d{2}-\d{2}-\d{2}\b")
    offenders: list[str] = []
    for path in SRC.glob("*.py"):
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if pattern.search(line):
                offenders.append(f"{path.name}:{number}: {line.strip()}")
    assert not offenders, (
        "Literal dates found in src/. Festival dates are computed, never "
        "tabulated:\n  " + "\n  ".join(offenders)
    )


def test_tithi_does_not_depend_on_the_ayanamsa(backend):
    """A tithi is a difference of longitudes, so the sidereal offset cancels.

    This is why festival *dates* are robust while month *names* are not, and it
    is worth asserting rather than merely believing: an ayanamsa term leaking
    into the elongation would move every festival at once.
    """
    jd = ephemeris.datetime_to_jd(dt.datetime(2020, 2, 21, tzinfo=dt.timezone.utc))
    elongation = float(backend.elongation(jd))
    direct = float(backend.moon_longitude(jd)) - float(backend.sun_longitude(jd))
    assert abs(np.mod(direct, 360.0) - elongation) < 1e-9


def test_ayanamsa_returns_its_defining_value_at_its_epoch(backend):
    """The Lahiri construction must round-trip, or every sankranti is displaced."""
    if backend.name != "skyfield":
        pytest.skip("the round-trip checks this project's own construction")
    got = float(backend.ayanamsa(ephemeris._LAHIRI_EPOCH_TT_JD))
    assert abs(got - ephemeris._LAHIRI_EPOCH_DEGREES) * 3600 < 0.01


def test_backend_is_declared_not_discovered(config):
    """An unknown backend name raises. It does not fall through to a working one."""
    with pytest.raises(ConfigError, match="Unknown ephemeris backend"):
        ephemeris.build({**config, "backend": "whatever-is-installed"})


def test_missing_backend_raises(config):
    with pytest.raises(ConfigError, match="declares no 'backend'"):
        ephemeris.build({key: value for key, value in config.items() if key != "backend"})


def test_unavailable_backend_raises_rather_than_substituting(config):
    """If swisseph is absent, asking for it must fail -- not silently give skyfield."""
    pytest.importorskip
    try:
        import swisseph  # noqa: F401
    except ImportError:
        with pytest.raises(EphemerisUnavailable, match="pyswisseph"):
            ephemeris.build({**config, "backend": "swisseph"})
    else:
        pytest.skip("pyswisseph is installed, so this path cannot be exercised")


def test_unimplemented_ayanamsa_raises(config):
    with pytest.raises(ConfigError, match="not implemented"):
        ephemeris.build({**config, "ayanamsa": "raman"})


# --------------------------------------------------------------------------
# Pure functions on literals. No ephemeris, no data -- brief 4 permits these.
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("paksha", "tithi", "expected"),
    [
        ("shukla", 1, 1),
        ("shukla", 15, 15),     # purnima
        ("krishna", 1, 16),
        ("krishna", 14, 29),    # the Shivaratri chaturdashi
        ("krishna", 15, 30),    # amavasya, counted within the paksha
        ("krishna", 30, 30),    # amavasya, counted from the new moon
    ],
)
def test_absolute_tithi(paksha, tithi, expected):
    assert panchanga.absolute_tithi(paksha, tithi) == expected


@pytest.mark.parametrize(
    ("paksha", "tithi"),
    [("shukla", 0), ("shukla", 16), ("shukla", 30), ("krishna", 0), ("krishna", 31)],
)
def test_absolute_tithi_rejects_out_of_range(paksha, tithi):
    with pytest.raises(ConfigError):
        panchanga.absolute_tithi(paksha, tithi)


def test_absolute_tithi_rejects_unknown_paksha():
    with pytest.raises(ConfigError, match="Unknown paksha"):
        panchanga.absolute_tithi("shukIa", 1)


@pytest.mark.parametrize(
    ("month", "paksha", "expected"),
    [
        # The bright fortnight is the same month in both schemes.
        ("ashvina", "shukla", "ashvina"),
        ("chaitra", "shukla", "chaitra"),
        # The dark fortnight shifts back one month going purnimanta -> amanta.
        ("phalguna", "krishna", "magha"),      # Maha Shivaratri
        ("kartika", "krishna", "ashvina"),     # Diwali
        ("chaitra", "krishna", "phalguna"),    # and it wraps
    ],
)
def test_purnimanta_translates_to_amanta(month, paksha, expected):
    assert panchanga.to_amanta(month, paksha, "purnimanta") == expected


@pytest.mark.parametrize("paksha", ["shukla", "krishna"])
def test_amanta_is_the_identity(paksha):
    for month in panchanga.MONTHS:
        assert panchanga.to_amanta(month, paksha, "amanta") == month


def test_unknown_scheme_raises():
    with pytest.raises(ConfigError, match="lunar_month_scheme"):
        panchanga.to_amanta("chaitra", "krishna", "vikrami")


def test_missing_scheme_raises(config):
    """The key used to be declared and read by nothing at all. Now it is required."""
    stripped = {k: v for k, v in config.items() if k != "lunar_month_scheme"}
    with pytest.raises(ConfigError, match="declares no 'lunar_month_scheme'"):
        panchanga.parse_rules(stripped)


def test_rules_declaring_an_unknown_observance_raise(config):
    broken = {
        **config,
        "festivals": [
            {"id": "x", "rule": {"month": "chaitra", "paksha": "shukla",
                                 "tithi": 1, "observance": "moonrise"}}
        ],
    }
    with pytest.raises(ConfigError, match="observance"):
        panchanga.parse_rules(broken)


def test_rules_declaring_an_unknown_month_raise(config):
    broken = {
        **config,
        "festivals": [
            {"id": "x", "rule": {"month": "brumaire", "paksha": "shukla", "tithi": 1}}
        ],
    }
    with pytest.raises(ConfigError, match="not an amanta month"):
        panchanga.parse_rules(broken)


# --------------------------------------------------------------------------
# Features.
# --------------------------------------------------------------------------


def test_unknown_feature_name_raises(computed, config):
    """A typo must not silently drop a regressor from the calendar arm."""
    with pytest.raises(ConfigError, match="unknown calendar feature"):
        calendarfeat.build(
            computed,
            {**config, "features": ["festival_days", "festvial_days"]},
            dt.date(FIRST_YEAR, 1, 1),
            dt.date(LAST_YEAR, 12, 31),
        )


def test_feature_frame_is_complete_and_monthly(computed, config):
    frame = calendarfeat.build(
        computed, config, dt.date(FIRST_YEAR, 1, 1), dt.date(LAST_YEAR, 12, 31)
    )
    assert list(frame.columns) == config["features"]
    assert len(frame) == (LAST_YEAR - FIRST_YEAR + 1) * 12
    assert not frame.isna().any().any()
    assert (frame.index.day == 1).all()


def test_festival_days_conserve_the_declared_durations(computed, config):
    """Every declared day lands in exactly one month, including across a boundary.

    Nine days of Navratri split over September and October must still total
    nine. This is the invariant that a straddling festival would break.
    """
    frame = calendarfeat.build(
        computed, config, dt.date(FIRST_YEAR, 1, 1), dt.date(LAST_YEAR, 12, 31)
    )
    per_year = sum(rule.duration_days for rule in panchanga.parse_rules(config))
    totals = frame["festival_days"].groupby(frame.index.year).sum()
    assert set(totals) == {per_year}, (
        f"Festival days per year should be {per_year} for every year, got "
        f"{sorted(set(totals))}. A festival is being dropped or double-counted."
    )


def test_sharad_navratri_days_total_nine_a_year(computed, config):
    frame = calendarfeat.build(
        computed, config, dt.date(FIRST_YEAR, 1, 1), dt.date(LAST_YEAR, 12, 31)
    )
    totals = frame["sharad_navratri_days"].groupby(frame.index.year).sum()
    assert set(totals) == {9}


def test_lunar_drift_overflows_a_lunation_only_in_adhika_months(computed, config):
    """The intercalary case is visible in the column rather than wrapping quietly."""
    frame = calendarfeat.build(
        computed, config, dt.date(FIRST_YEAR, 1, 1), dt.date(LAST_YEAR, 12, 31)
    )
    drift = frame["lunar_drift_days"]
    assert drift.min() >= 0.0
    assert (drift > 29.53).any(), (
        "No month exceeds a synodic month of drift over ten years, but adhika "
        "months occur roughly seven times in nineteen. The overflow signal is "
        "not reaching the column."
    )
    assert drift.max() < 60.0


def test_written_features_survive_the_round_trip_into_the_calendar_model(
    computed, config, tmp_path
):
    """write -> read -> fit, exactly as the backtest stage does it.

    Every other calendar-routing test builds its features in memory, so nothing
    covered the join that actually happens in production: ``calendarfeat.write``
    puts month starts on disk, ``cli.run_backtest`` reads them back with
    ``parse_dates``, and ``sarimax_cal`` reindexes them onto the training index
    and onto a future index it builds itself. A date format or index-name change
    that broke that alignment would surface as CalendarRoutingError at the first
    origin of a multi-hour run, or -- worse -- as silently NaN exog.
    """
    import numpy as np
    import pandas as pd

    from yatra import models

    frame = calendarfeat.build(
        computed, config, dt.date(FIRST_YEAR, 1, 1), dt.date(LAST_YEAR, 12, 31)
    )
    path = calendarfeat.write(frame, tmp_path / "calendar.csv")

    # The loader in cli.run_backtest, verbatim.
    reloaded = pd.read_csv(path, index_col=0, parse_dates=True)
    pd.testing.assert_index_equal(reloaded.index, frame.index, check_names=False)

    horizons = [1, 2, 3, 4, 5, 6]
    months = (LAST_YEAR - FIRST_YEAR + 1) * 12 - max(horizons)
    index = reloaded.index[:months]
    ramp = np.arange(len(index), dtype="float64")
    train = pd.Series(1000.0 + 5.0 * ramp, index=index).asfreq("MS")

    assert not reloaded.reindex(train.index).isna().any().any(), (
        "Calendar features do not align with a month-start training index after "
        "a round trip through CSV."
    )
    out = models.predict("sarimax_cal", train, horizons, calendar=reloaded)
    assert out.shape == (len(horizons),)
    assert np.isfinite(out).all()


def test_calendar_features_never_read_observations():
    """The leak-free claim, checked structurally rather than trusted."""
    text = (SRC / "calendarfeat.py").read_text(encoding="utf-8")
    for forbidden in ("contract", "monthly.csv", "pilgrims", "data/raw"):
        assert forbidden not in text, (
            f"calendarfeat.py references {forbidden!r}. Calendar features must be "
            "functions of the calendar alone -- that is what makes it legitimate "
            "for sarimax_cal to see future rows of them."
        )
