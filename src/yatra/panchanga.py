"""Tithi, sankranti, lunar months, and the festival rules. Backend-independent.

Nothing here knows whether Skyfield or Swiss Ephemeris answered. Everything is
derived from the five quantities in :mod:`yatra.ephemeris`, which is what makes
swapping the backend a real cross-check rather than a coincidence.

**There is no date table in this module and there must not be one** (brief 3.6).
Every date returned here is solved for. The reference dates in
``tests/test_calendar.py`` are validation against published almanacs, not a
lookup the pipeline reads -- they live in the test suite precisely so that drift
in the computation fails the build.

The three questions
-------------------

*Which tithi is running?* A tithi is one thirtieth of the synodic month, defined
by the Moon-minus-Sun elongation alone. Every ayanamsa term cancels out of a
difference of longitudes, so a tithi is the robust part of this module.

*Which lunar month is this?* Amanta reckoning: the month runs new moon to new
moon, and is named for the solar month -- the sankranti -- that begins inside
it. A month containing no sankranti is *adhika* (intercalary) and borrows the
following month's name. This is the part that depends on the ayanamsa, and the
part that :func:`lunar_months` guards with a near-tie check.

*Which civil day is the festival?* A tithi is an interval; a festival is a day.
The map between them is the *observance rule*, declared per festival in the
config, because it differs by festival and decides more dates than any plausible
ephemeris difference does. See :data:`OBSERVANCES`.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from zoneinfo import ZoneInfo

import numpy as np
from scipy.optimize import brentq

from .ephemeris import Backend, jd_to_datetime, local_midnight_jd
from .errors import ConfigError

# Amanta month names, in order, indexed by the rashi whose sankranti names them:
# the month containing Mesha sankranti (sidereal Sun crossing 0 deg) is Chaitra,
# the one containing Vrishabha sankranti is Vaishakha, and so on round.
MONTHS: tuple[str, ...] = (
    "chaitra", "vaishakha", "jyeshtha", "ashadha",
    "shravana", "bhadrapada", "ashvina", "kartika",
    "margashirsha", "pausha", "magha", "phalguna",
)
MONTH_INDEX = {name: index for index, name in enumerate(MONTHS)}

PAKSHAS = ("shukla", "krishna")

# Amanta months run new moon to new moon; purnimanta months run full moon to
# full moon. The two schemes agree on every bright-fortnight day and disagree by
# one month name on every dark-fortnight day, because purnimanta assigns the
# dark fortnight to the *following* month. Same day, different label -- which is
# exactly the kind of difference that produces a plausible wrong answer rather
# than a crash, so the scheme is declared in config and applied here.
SCHEMES = ("amanta", "purnimanta")

DEGREES_PER_TITHI = 12.0
DEGREES_PER_RASHI = 30.0
TITHIS_PER_MONTH = 30

# How close a sankranti may fall to a new moon before the month name it decides
# stops being computable. Expressed in days. See _assert_no_near_tie.
DEFAULT_NEAR_TIE_TOLERANCE_DAYS = 15.0 / (24.0 * 60.0)   # 15 minutes

OBSERVANCES = ("sunrise", "nishita", "pradosha")


# --------------------------------------------------------------------------
# Root finding. Angles are degrees; every target is a level crossing of a
# monotone-in-the-bracket function, so bisection is enough and is exact to the
# tolerance asked for.
# --------------------------------------------------------------------------


def _wrapped(value: np.ndarray | float, target: float) -> np.ndarray:
    """Signed angular distance from ``target``, in ``[-180, 180)``."""
    return np.mod(np.asarray(value, dtype="float64") - target + 180.0, 360.0) - 180.0


def _solve(func, target: float, lo: float, hi: float, xtol: float = 1e-9) -> float:
    """Time in ``(lo, hi)`` at which ``func`` crosses ``target`` upwards.

    The bracket must be narrow enough that ``func`` moves less than 180 degrees
    across it, which every caller here guarantees by scanning on a grid first.
    """
    def residual(jd: float) -> float:
        return float(_wrapped(func(jd), target))

    return float(brentq(residual, lo, hi, xtol=xtol))


def _upward_crossings(values: np.ndarray, grid: np.ndarray) -> np.ndarray:
    """Indices ``i`` where ``values`` crosses zero from below between i and i+1."""
    return np.nonzero((values[:-1] < 0.0) & (values[1:] >= 0.0))[0]


# --------------------------------------------------------------------------
# New moons and sankrantis.
# --------------------------------------------------------------------------


def new_moons(backend: Backend, jd_start: float, jd_end: float) -> np.ndarray:
    """Instants of new moon (elongation crossing 0) in ``[jd_start, jd_end]``.

    Elongation advances between 10.9 and 15.4 degrees a day and never reverses,
    so a one-day grid cannot alias past a crossing.
    """
    grid = np.arange(jd_start, jd_end + 1.0, 1.0)
    residual = _wrapped(backend.elongation(grid), 0.0)
    return np.array([
        _solve(backend.elongation, 0.0, grid[i], grid[i + 1])
        for i in _upward_crossings(residual, grid)
    ])


@dataclass(frozen=True)
class Sankranti:
    """The Sun entering a sidereal sign. Names a lunar month; nothing else."""

    jd: float
    rashi: int          # 0 = Mesha, ... 11 = Meena

    @property
    def month_name(self) -> str:
        return MONTHS[self.rashi]


def sankrantis(backend: Backend, jd_start: float, jd_end: float) -> list[Sankranti]:
    """Sidereal sign ingresses in ``[jd_start, jd_end]``, ascending.

    The Sun advances about 0.9856 deg/day, so a sign boundary is crossed roughly
    every 30 days and a one-day grid resolves each one unambiguously.
    """
    grid = np.arange(jd_start, jd_end + 1.0, 1.0)
    longitudes = backend.sidereal_sun_longitude(grid)
    rashi = np.floor(longitudes / DEGREES_PER_RASHI).astype(int)

    found: list[Sankranti] = []
    for i in np.nonzero(rashi[:-1] != rashi[1:])[0]:
        entered = int(rashi[i + 1])
        boundary = entered * DEGREES_PER_RASHI
        jd = _solve(backend.sidereal_sun_longitude, boundary, grid[i], grid[i + 1])
        found.append(Sankranti(jd=jd, rashi=entered))
    return found


# --------------------------------------------------------------------------
# Lunar months.
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class LunarMonth:
    """One amanta month: new moon to new moon, with the name a sankranti gave it."""

    start_jd: float
    end_jd: float
    name: str
    is_adhika: bool
    sankranti_jd: float
    """The ingress this month is named for.

    For a nija month it falls inside ``[start_jd, end_jd)``. An adhika month
    contains no ingress at all, so this carries the one that named the following
    month -- which is what makes ``sankranti_jd - start_jd`` overflow a lunation
    for exactly the adhika months, and nothing else.
    """

    @property
    def label(self) -> str:
        return f"adhika {self.name}" if self.is_adhika else self.name

    @property
    def drift_days(self) -> float:
        """Days from this month's new moon to the sankranti that names it.

        This is the lunisolar drift itself: how far the lunar reckoning has slid
        against the solar one. It runs 0 to about 29.5 for a nija month and
        past that for an adhika month, and it is a purely local quantity -- it
        does not depend on where the computed range starts or ends, so extending
        the range cannot change a value already written.
        """
        return self.sankranti_jd - self.start_jd


def lunar_months(
    backend: Backend,
    jd_start: float,
    jd_end: float,
    near_tie_tolerance_days: float = DEFAULT_NEAR_TIE_TOLERANCE_DAYS,
    tz: ZoneInfo | None = None,
) -> list[LunarMonth]:
    """Amanta lunar months fully contained in ``[jd_start, jd_end]``.

    Naming follows the standard rule: the month is named for the sankranti that
    falls inside it. No sankranti means an adhika (intercalary) month, which
    takes the name of the month that follows it. Two sankrantis means a kshaya
    month, which does not occur anywhere near this project's window and is
    raised on rather than guessed at.
    """
    moons = new_moons(backend, jd_start, jd_end)
    if len(moons) < 2:
        raise ConfigError(
            f"Span {jd_start}..{jd_end} contains {len(moons)} new moon(s); at "
            "least two are needed to bound a single lunar month."
        )

    ingresses = sankrantis(backend, moons[0] - 1.0, moons[-1] + 1.0)
    _assert_no_near_tie(moons, ingresses, near_tie_tolerance_days, tz)

    spans = list(zip(moons[:-1], moons[1:]))
    contained: list[list[Sankranti]] = [
        [s for s in ingresses if start <= s.jd < end] for start, end in spans
    ]

    for index, (start, end) in enumerate(spans):
        if len(contained[index]) > 1:
            raise ConfigError(
                "Two sankrantis fall in the lunar month beginning "
                f"{_show(start, tz)} -- a kshaya (lost) month. The naming rule "
                "in this module does not cover it, and it should not occur in "
                "this project's window: the next ones are in the 22nd century. "
                "Check the configured date range before relaxing anything."
            )

    months: list[LunarMonth] = []
    for index, (start, end) in enumerate(spans):
        here = contained[index]
        if here:
            months.append(
                LunarMonth(start, end, here[0].month_name, False, here[0].jd)
            )
            continue

        # Adhika: borrow the name of the next month that does have a sankranti.
        following = next(
            (contained[j][0] for j in range(index + 1, len(spans)) if contained[j]),
            None,
        )
        if following is None:
            raise ConfigError(
                "The lunar month beginning "
                f"{_show(start, tz)} contains no sankranti, and neither does any "
                "month after it inside the requested span, so its adhika name "
                "cannot be resolved. Extend the range end by two months."
            )
        months.append(LunarMonth(start, end, following.month_name, True, following.jd))

    return months


def _assert_no_near_tie(
    moons: np.ndarray,
    ingresses: list[Sankranti],
    tolerance_days: float,
    tz: ZoneInfo | None,
) -> None:
    """Refuse to name a month when a sankranti sits on top of a new moon.

    Which side of a new moon a sankranti falls on decides a month's name, and
    can create or erase an adhika month -- which shifts every festival label for
    that year and therefore every column of ``results/calendar.csv``. Within a
    few minutes of the boundary, that decision is below the resolution of the
    ayanamsa *definition*, not of the ephemeris: panchang makers using different
    Lahiri variants disagree there too.

    So this raises. The alternative is a plausible month name that nothing in
    the pipeline would flag, which is the failure class in brief 5.
    """
    if not len(moons) or not ingresses:
        return
    for ingress in ingresses:
        gap = float(np.min(np.abs(moons - ingress.jd)))
        if gap < tolerance_days:
            raise ConfigError(
                f"The {ingress.month_name.title()} sankranti at "
                f"{_show(ingress.jd, tz)} falls {gap * 24 * 60:.1f} minutes from "
                "a new moon. Which side it lands on decides a lunar month's "
                "name and can create or erase an adhika month, and that margin "
                "is finer than the Lahiri ayanamsa is defined to. Adjudicate it "
                "against a published panchang and record the decision before "
                "this range can be computed."
            )


def _show(jd: float, tz: ZoneInfo | None) -> str:
    return jd_to_datetime(jd, tz).strftime("%Y-%m-%d %H:%M %Z").strip()


# --------------------------------------------------------------------------
# Tithis.
# --------------------------------------------------------------------------


def absolute_tithi(paksha: str, tithi: int) -> int:
    """``(paksha, tithi)`` from a config rule -> absolute tithi in ``1..30``.

    Shukla 1..15 are 1..15, with 15 the full moon. Krishna 1..15 are 16..30,
    with 30 the new moon. The absolute form 16..30 is also accepted for the dark
    fortnight, because almanacs write the new moon both ways -- "krishna 15" and
    "tithi 30" name the same thing, and the config uses the latter for Diwali.
    """
    if paksha not in PAKSHAS:
        raise ConfigError(f"Unknown paksha {paksha!r}. Expected one of {list(PAKSHAS)}.")
    if not isinstance(tithi, int) or isinstance(tithi, bool):
        raise ConfigError(f"Tithi must be an integer, got {tithi!r}.")

    if paksha == "shukla":
        if not 1 <= tithi <= 15:
            raise ConfigError(
                f"shukla tithi {tithi} is out of range. The bright fortnight is "
                "1..15, where 15 is the full moon."
            )
        return tithi

    if 1 <= tithi <= 15:
        return 15 + tithi
    if 16 <= tithi <= TITHIS_PER_MONTH:
        return tithi
    raise ConfigError(
        f"krishna tithi {tithi} is out of range. The dark fortnight is 1..15 "
        "counting within the paksha, or 16..30 counting from the new moon; 30 "
        "and krishna 15 both mean the new moon."
    )


def tithi_span(backend: Backend, month: LunarMonth, index: int) -> tuple[float, float]:
    """Start and end instants of absolute tithi ``index`` within ``month``.

    Tithi ``n`` runs from elongation ``12(n-1)`` to ``12n`` degrees measured from
    the new moon that opened the month. Elongation is strictly increasing across
    a lunation, so each boundary is a single crossing.
    """
    if not 1 <= index <= TITHIS_PER_MONTH:
        raise ConfigError(f"Absolute tithi must be 1..30, got {index}.")

    start_angle = (index - 1) * DEGREES_PER_TITHI
    end_angle = index * DEGREES_PER_TITHI
    start = month.start_jd if index == 1 else _elongation_time(backend, month, start_angle)
    end = month.end_jd if index == TITHIS_PER_MONTH else _elongation_time(backend, month, end_angle)
    return start, end


def _elongation_time(backend: Backend, month: LunarMonth, angle: float) -> float:
    """Instant inside ``month`` at which elongation reaches ``angle`` degrees."""
    grid = np.linspace(month.start_jd, month.end_jd, 80)
    unwrapped = np.degrees(np.unwrap(np.radians(backend.elongation(grid))))
    unwrapped -= unwrapped[0]

    hit = np.nonzero((unwrapped[:-1] <= angle) & (unwrapped[1:] > angle))[0]
    if not len(hit):
        raise ConfigError(
            f"Elongation {angle} deg is not reached inside the lunar month "
            f"beginning at JD {month.start_jd}. The month bounds are wrong."
        )
    i = int(hit[0])
    return _solve(backend.elongation, angle % 360.0, grid[i], grid[i + 1])


def tithi_at(backend: Backend, month: LunarMonth, jd: float) -> int:
    """Absolute tithi running at ``jd``, which must lie inside ``month``."""
    grid = np.linspace(month.start_jd, max(jd, month.start_jd), 80)
    unwrapped = np.degrees(np.unwrap(np.radians(backend.elongation(grid))))
    elapsed = unwrapped[-1] - unwrapped[0]
    return int(min(TITHIS_PER_MONTH, np.floor(elapsed / DEGREES_PER_TITHI) + 1))


# --------------------------------------------------------------------------
# Civil days, and the observance windows that map a tithi onto one.
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class CivilDay:
    """A local calendar day with the horizon events the observance rules need."""

    date: dt.date
    sunrise_jd: float
    sunset_jd: float
    next_sunrise_jd: float

    @property
    def night_length(self) -> float:
        return self.next_sunrise_jd - self.sunset_jd

    def window(self, observance: str) -> tuple[float, float]:
        """The interval a tithi must occupy to make this the festival's day.

        ``sunrise``  the instant of sunrise. The default rule, and the one most
                     festivals follow: a tithi belongs to the day at whose
                     sunrise it is running.
        ``nishita``  the eighth of the night's fifteen muhurtas -- true midnight
                     in the ritual sense. Maha Shivaratri is observed on the day
                     whose nishita the Chaturdashi covers, which is regularly a
                     different civil day from the sunrise answer.
        ``pradosha`` the three muhurtas following sunset. Diwali's Lakshmi Puja
                     is a pradosha observance, which is why it can fall on the
                     day *before* the one that holds Amavasya at sunrise.
        """
        if observance == "sunrise":
            return self.sunrise_jd, self.sunrise_jd
        night = self.night_length
        if observance == "nishita":
            return self.sunset_jd + 7.0 * night / 15.0, self.sunset_jd + 8.0 * night / 15.0
        if observance == "pradosha":
            return self.sunset_jd, self.sunset_jd + 3.0 * night / 15.0
        raise ConfigError(
            f"Unknown observance {observance!r}. Known: {list(OBSERVANCES)}."
        )


def civil_days(backend: Backend, jd_start: float, jd_end: float, tz: ZoneInfo) -> list[CivilDay]:
    """Every local day in the span, with its sunrise, sunset and next sunrise.

    Sunrise decides which day a tithi belongs to, so it is computed at the
    configured location rather than assumed to be a fixed offset from midnight.
    """
    risings = backend.risings(jd_start - 1.0, jd_end + 2.0)
    settings = backend.settings(jd_start - 1.0, jd_end + 2.0)
    if len(risings) < 2 or len(settings) < 1:
        raise ConfigError(f"No sunrise/sunset events found in {jd_start}..{jd_end}.")

    days: list[CivilDay] = []
    for index in range(len(risings) - 1):
        rise = risings[index]
        date = jd_to_datetime(rise, tz).date()
        after = settings[settings > rise]
        if not len(after):
            break
        days.append(
            CivilDay(
                date=date,
                sunrise_jd=rise,
                sunset_jd=float(after[0]),
                next_sunrise_jd=float(risings[index + 1]),
            )
        )
    return days


def _overlap(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Length of the intersection. A zero-length window scores 1 if contained."""
    lo, hi = max(a[0], b[0]), min(a[1], b[1])
    if a[0] == a[1] or b[0] == b[1]:
        return 1.0 if lo <= hi else 0.0
    return max(0.0, hi - lo)


# --------------------------------------------------------------------------
# Festivals.
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class FestivalRule:
    """One entry from ``calendar.yaml``, parsed and checked."""

    id: str
    label: str
    month: str
    paksha: str
    tithi: int
    observance: str
    duration_days: int

    @property
    def absolute_tithi(self) -> int:
        return absolute_tithi(self.paksha, self.tithi)


def to_amanta(month: str, paksha: str, scheme: str) -> str:
    """Translate a festival's declared lunar month into amanta reckoning.

    Under purnimanta the dark fortnight belongs to the following month's name,
    so a krishna-paksha rule labelled Phalguna is the same set of days an amanta
    almanac calls Magha. Bright-fortnight rules are identical in both schemes.

    Everything downstream -- :func:`lunar_months`, :func:`tithi_span` -- works in
    amanta only, because amanta months are bounded by new moons and a tithi
    index counts from the new moon. Translating once, here, keeps a single
    reckoning in the solver.
    """
    if scheme not in SCHEMES:
        raise ConfigError(
            f"Unknown lunar_month_scheme {scheme!r}. Known: {list(SCHEMES)}."
        )
    if scheme == "amanta" or paksha == "shukla":
        return month
    return MONTHS[(MONTH_INDEX[month] - 1) % len(MONTHS)]


def parse_rules(config: dict) -> list[FestivalRule]:
    """Read the ``festivals`` block. Every field is checked; none is defaulted
    except ``observance``, which defaults to the majority rule, and
    ``duration_days``, which defaults to a single day.

    Month names are translated into amanta here, according to the config's
    declared ``lunar_month_scheme``, so that the rest of the module works in one
    reckoning.
    """
    entries = config.get("festivals")
    if not entries:
        raise ConfigError("calendar.yaml declares no 'festivals'.")

    scheme = config.get("lunar_month_scheme")
    if scheme is None:
        raise ConfigError(
            "calendar.yaml declares no 'lunar_month_scheme'. It has no default: "
            "amanta and purnimanta give the same festival a different month "
            "name in the dark fortnight, and guessing wrong moves Maha "
            f"Shivaratri and Diwali by a whole month. Choose one of {list(SCHEMES)}."
        )
    if scheme not in SCHEMES:
        raise ConfigError(f"Unknown lunar_month_scheme {scheme!r}. Known: {list(SCHEMES)}.")

    rules: list[FestivalRule] = []
    seen: set[str] = set()
    for entry in entries:
        try:
            identifier = entry["id"]
            rule = entry["rule"]
            month, paksha, tithi = rule["month"], rule["paksha"], rule["tithi"]
        except (KeyError, TypeError) as exc:
            raise ConfigError(f"Malformed festival entry {entry!r}: missing {exc}.") from exc

        if identifier in seen:
            raise ConfigError(f"Duplicate festival id {identifier!r}.")
        seen.add(identifier)

        if month not in MONTH_INDEX:
            raise ConfigError(
                f"Festival {identifier!r} names lunar month {month!r}, which is "
                f"not an amanta month. Known: {list(MONTHS)}."
            )
        observance = rule.get("observance", "sunrise")
        if observance not in OBSERVANCES:
            raise ConfigError(
                f"Festival {identifier!r} declares observance {observance!r}. "
                f"Known: {list(OBSERVANCES)}."
            )
        duration = int(entry.get("duration_days", 1))
        if duration < 1:
            raise ConfigError(f"Festival {identifier!r} has duration_days {duration}.")

        if paksha not in PAKSHAS:
            raise ConfigError(
                f"Festival {identifier!r} declares paksha {paksha!r}. "
                f"Expected one of {list(PAKSHAS)}."
            )

        parsed = FestivalRule(
            id=str(identifier),
            label=str(entry.get("label", identifier)),
            month=to_amanta(str(month), str(paksha), scheme),
            paksha=str(paksha),
            tithi=int(tithi),
            observance=str(observance),
            duration_days=duration,
        )
        parsed.absolute_tithi        # validates the paksha/tithi pair now, not later
        rules.append(parsed)
    return rules


@dataclass(frozen=True)
class Occurrence:
    """One dated occurrence of one festival."""

    festival_id: str
    label: str
    start_date: dt.date
    duration_days: int
    lunar_month: str
    observance: str

    @property
    def dates(self) -> list[dt.date]:
        return [self.start_date + dt.timedelta(days=n) for n in range(self.duration_days)]


def resolve(
    backend: Backend,
    rules: list[FestivalRule],
    months: list[LunarMonth],
    days: list[CivilDay],
) -> list[Occurrence]:
    """Date every rule against every matching lunar month.

    Adhika months are skipped. An intercalary Ashvina does not carry Sharad
    Navratri -- the observance stays in the nija month -- and treating it as a
    second occurrence would double-count festival days in that year's features.
    """
    by_date = {day.date: day for day in days}
    ordered = sorted(by_date)
    occurrences: list[Occurrence] = []

    for rule in rules:
        index = rule.absolute_tithi
        for month in months:
            if month.name != rule.month or month.is_adhika:
                continue
            start_jd, end_jd = tithi_span(backend, month, index)
            day = _observance_day(rule, (start_jd, end_jd), ordered, by_date)
            if day is None:
                continue
            occurrences.append(
                Occurrence(
                    festival_id=rule.id,
                    label=rule.label,
                    start_date=day,
                    duration_days=rule.duration_days,
                    lunar_month=month.label,
                    observance=rule.observance,
                )
            )

    occurrences.sort(key=lambda o: (o.start_date, o.festival_id))
    return occurrences


def _observance_day(
    rule: FestivalRule,
    span: tuple[float, float],
    ordered: list[dt.date],
    by_date: dict[dt.date, CivilDay],
) -> dt.date | None:
    """Pick the civil day whose observance window the tithi best occupies.

    Ties break toward the earlier day, which is the usual almanac convention
    when a tithi covers the relevant window on two consecutive days. A tithi
    that covers no day's window at all -- a kshaya tithi, swallowed between two
    sunrises -- falls back to the day on which it ends, which is where the
    observance is transferred.
    """
    candidates = [
        d for d in ordered
        if abs((d - jd_to_datetime(span[0]).date()).days) <= 3
    ]
    best_day: dt.date | None = None
    best_score = 0.0
    for date in candidates:
        score = _overlap(span, by_date[date].window(rule.observance))
        if score > best_score:
            best_day, best_score = date, score

    if best_day is not None:
        return best_day

    ending = jd_to_datetime(span[1]).date()
    return ending if ending in by_date else None


# --------------------------------------------------------------------------
# The stage entry point.
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Panchanga:
    """Everything the feature layer needs, computed in one pass.

    The astronomy is the slow part of this pipeline, so the lunar months are
    handed back alongside the festivals rather than recomputed: the drift
    feature is a property of the months themselves.
    """

    occurrences: list[Occurrence]
    months: list[LunarMonth]
    timezone: str

    @property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.timezone)


def compute(backend: Backend, config: dict, start: dt.date, end: dt.date) -> Panchanga:
    """Every festival occurrence between ``start`` and ``end``, inclusive.

    The span is padded by a couple of lunar months at each end so that a
    festival near a boundary is resolved from a complete month rather than a
    truncated one, and so that the month covering the first civil day is known.
    """
    tz = ZoneInfo(config["location"]["timezone"])
    rules = parse_rules(config)

    pad = 70.0
    jd_start = local_midnight_jd(start, tz) - pad
    jd_end = local_midnight_jd(end, tz) + pad

    tolerance = float(
        config.get("near_tie_tolerance_minutes", DEFAULT_NEAR_TIE_TOLERANCE_DAYS * 24 * 60)
    ) / (24.0 * 60.0)

    months = lunar_months(backend, jd_start, jd_end, tolerance, tz)
    days = civil_days(backend, jd_start, jd_end, tz)
    found = resolve(backend, rules, months, days)
    return Panchanga(
        occurrences=[o for o in found if start <= o.start_date <= end],
        months=months,
        timezone=config["location"]["timezone"],
    )
