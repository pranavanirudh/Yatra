"""A thin port over the astronomy backend. One backend at a time.

The backend is **declared** in ``experiments/configs/calendar.yaml`` and looked
up by name. If the named backend cannot load, this module raises
:class:`~yatra.errors.EphemerisUnavailable` and the calendar stage stops. It
does not try Swiss Ephemeris, catch ``ImportError``, and quietly compute with
something else. See CLAUDE.md 3.6 and docs/ephemeris.md for why that rule is
load-bearing rather than fussy.

What a backend must provide is deliberately small -- five quantities, from which
``panchanga.py`` derives every tithi, sankranti and festival date without
knowing which library answered:

==============================  ============================================
:meth:`Backend.sun_longitude`   apparent geocentric ecliptic longitude, Sun
:meth:`Backend.moon_longitude`  apparent geocentric ecliptic longitude, Moon
:meth:`Backend.ayanamsa`        tropical longitude of the sidereal zero point
:meth:`Backend.risings`         Sun rising times over a span
:meth:`Backend.settings`        Sun setting times over a span
==============================  ============================================

Longitudes are degrees in ``[0, 360)``, referred to the **true ecliptic and
equinox of date**. That frame choice is not cosmetic. Sidereal longitude is
``sun_longitude - ayanamsa``, and because both terms are expressed in the same
frame, nutation cancels exactly instead of approximately. A stray 17-arcsecond
nutation term is about seven minutes of solar motion, and a sankranti landing
seven minutes on the wrong side of a new moon renames a lunar month.

Times crossing this interface are **Julian Days, UT**. That is the currency
Swiss Ephemeris already speaks, and Skyfield converts to it in one call. UTC is
substituted for UT1 without correction; the discrepancy is under 0.9 s, four
orders of magnitude below anything that can move a festival date.
"""

from __future__ import annotations

import datetime as dt
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np

from .errors import ConfigError, EphemerisUnavailable

# Lahiri (Chitrapaksha), as Swiss Ephemeris defines it: the ayanamsa at this
# epoch, from which every other date follows by precessing the implied
# direction. Do not "improve" these digits -- they are a definition, not a
# measurement, and changing them silently moves every sankranti.
_LAHIRI_EPOCH_TT_JD = 2435553.5           # 1956 Mar 21, the equinox
_LAHIRI_EPOCH_DEGREES = 23.250182778 - 0.004660222

_KERNEL_URLS = (
    "https://ssd.jpl.nasa.gov/ftp/eph/planets/bsp/{name}",
    "https://naif.jpl.nasa.gov/pub/naif/generic_kernels/spk/planets/{name}",
)


@dataclass(frozen=True)
class Location:
    """Where sunrise is computed. Pinned to the shrine, not the town.

    Sunrise at Bhawan and at Katra differ by well under a minute, which cannot
    move a tithi across a sunrise except in a near-tie -- and the near-tie is
    exactly the case that decides a contested festival date. So it is pinned
    rather than left implicit.
    """

    name: str
    latitude: float
    longitude: float
    elevation_m: float
    timezone: str

    @property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.timezone)


class Backend(ABC):
    """The whole surface ``panchanga.py`` is allowed to depend on."""

    name: str

    #: The site sunrise and sunset are computed for. Declared here because it
    #: is part of the surface in fact -- every backend takes one, `risings` and
    #: `settings` are meaningless without it, and `cli.py` prints it so an
    #: operator can see which site a calendar was computed at. It was reachable
    #: on both implementations and absent from the contract, which is a
    #: difference nothing would have caught until a third backend omitted it.
    location: Location

    @abstractmethod
    def sun_longitude(self, jd_ut: np.ndarray | float) -> np.ndarray:
        """Apparent geocentric ecliptic longitude of the Sun, degrees."""

    @abstractmethod
    def moon_longitude(self, jd_ut: np.ndarray | float) -> np.ndarray:
        """Apparent geocentric ecliptic longitude of the Moon, degrees."""

    @abstractmethod
    def ayanamsa(self, jd_ut: np.ndarray | float) -> np.ndarray:
        """Tropical longitude of the sidereal zero point, degrees (Lahiri)."""

    @abstractmethod
    def risings(self, jd_start: float, jd_end: float) -> np.ndarray:
        """Sun rising times in ``[jd_start, jd_end]``, ascending, as JD UT."""

    @abstractmethod
    def settings(self, jd_start: float, jd_end: float) -> np.ndarray:
        """Sun setting times in ``[jd_start, jd_end]``, ascending, as JD UT."""

    def elongation(self, jd_ut: np.ndarray | float) -> np.ndarray:
        """Moon minus Sun longitude, degrees in ``[0, 360)``.

        Every tithi question reduces to this one number, and every ayanamsa
        term cancels out of it -- which is why a tithi is a robust quantity
        while a lunar month *name* is not.
        """
        return np.mod(self.moon_longitude(jd_ut) - self.sun_longitude(jd_ut), 360.0)

    def sidereal_sun_longitude(self, jd_ut: np.ndarray | float) -> np.ndarray:
        """Sun's longitude in the sidereal zodiac. Sankrantis live here."""
        return np.mod(self.sun_longitude(jd_ut) - self.ayanamsa(jd_ut), 360.0)


# --------------------------------------------------------------------------
# Time helpers. JD UT in, aware datetimes out.
# --------------------------------------------------------------------------

_JD_UNIX_EPOCH = 2440587.5


def jd_to_datetime(jd_ut: float, tz: ZoneInfo | None = None) -> dt.datetime:
    """JD UT -> aware datetime, in ``tz`` if given, else UTC."""
    seconds = (float(jd_ut) - _JD_UNIX_EPOCH) * 86400.0
    moment = dt.datetime.fromtimestamp(seconds, tz=dt.timezone.utc)
    return moment.astimezone(tz) if tz is not None else moment


def datetime_to_jd(moment: dt.datetime) -> float:
    """Aware datetime -> JD UT. Naive input is rejected rather than assumed UTC."""
    if moment.tzinfo is None:
        raise ConfigError(
            f"{moment!r} is naive. Refusing to guess a timezone: a silent "
            "5h30m error here would shift every sunrise-based festival date."
        )
    return moment.timestamp() / 86400.0 + _JD_UNIX_EPOCH


def local_midnight_jd(day: dt.date, tz: ZoneInfo) -> float:
    """JD UT of 00:00 local on ``day``."""
    return datetime_to_jd(dt.datetime(day.year, day.month, day.day, tzinfo=tz))


# --------------------------------------------------------------------------
# Skyfield.
# --------------------------------------------------------------------------


class SkyfieldBackend(Backend):
    """JPL DE kernels through Skyfield. The declared default; see docs/ephemeris.md.

    Skyfield has no sidereal zodiac, so :meth:`ayanamsa` is computed here by the
    same construction Swiss Ephemeris uses: the point at the defining tropical
    longitude on the defining date is treated as a fixed inertial direction, and
    precession carries it to the date asked for.
    """

    name = "skyfield"

    def __init__(
        self,
        location: Location,
        kernel_dir: Path,
        kernel: str = "de421.bsp",
        allow_download: bool = True,
    ) -> None:
        try:
            from skyfield import almanac
            from skyfield.api import load, load_file, wgs84
            from skyfield.framelib import ecliptic_frame
        except ImportError as exc:  # pragma: no cover - environment dependent
            raise EphemerisUnavailable(
                "backend 'skyfield' is declared in experiments/configs/calendar.yaml "
                f"but skyfield could not be imported ({exc}). Install it with "
                "`pip install skyfield`, or declare a different backend. This is "
                "not falling back to one."
            ) from exc

        self._almanac = almanac
        self._ecliptic = ecliptic_frame
        self.location = location

        path = Path(kernel_dir) / kernel
        if not path.exists():
            if not allow_download:
                raise EphemerisUnavailable(
                    f"Ephemeris kernel {path} is absent and downloading is "
                    "disabled. Fetch it from "
                    f"{_KERNEL_URLS[0].format(name=kernel)} or point "
                    "ephemeris.kernel_dir at a copy."
                )
            _download_kernel(path)

        self._eph = load_file(str(path))
        try:
            self._earth = self._eph["earth"]
            self._sun = self._eph["sun"]
            self._moon = self._eph["moon"]
        except KeyError as exc:
            raise EphemerisUnavailable(
                f"Kernel {path} does not contain {exc}. de421.bsp and the de44x "
                "series do; a satellite or asteroid kernel does not."
            ) from exc

        self._ts = load.timescale()
        self._observer = self._earth + wgs84.latlon(
            location.latitude, location.longitude, elevation_m=location.elevation_m
        )
        self._ayanamsa_direction = self._sidereal_zero_direction()

    # -- longitudes -------------------------------------------------------

    def _time(self, jd_ut: np.ndarray | float):
        return self._ts.ut1_jd(np.asarray(jd_ut, dtype="float64"))

    def _longitude(self, target, jd_ut: np.ndarray | float) -> np.ndarray:
        apparent = self._earth.at(self._time(jd_ut)).observe(target).apparent()
        _, lon, _ = apparent.frame_latlon(self._ecliptic)
        return np.mod(np.asarray(lon.degrees, dtype="float64"), 360.0)

    def sun_longitude(self, jd_ut: np.ndarray | float) -> np.ndarray:
        return self._longitude(self._sun, jd_ut)

    def moon_longitude(self, jd_ut: np.ndarray | float) -> np.ndarray:
        return self._longitude(self._moon, jd_ut)

    # -- ayanamsa ---------------------------------------------------------

    def _sidereal_zero_direction(self) -> np.ndarray:
        """The Lahiri zero point as a fixed ICRF unit vector."""
        t0 = self._ts.tt_jd(_LAHIRI_EPOCH_TT_JD)
        theta = np.radians(_LAHIRI_EPOCH_DEGREES)
        in_ecliptic_of_t0 = np.array([np.cos(theta), np.sin(theta), 0.0])
        # rotation_at maps ICRF -> ecliptic of date, so its transpose carries
        # the point back to the inertial frame, where precession leaves it be.
        return self._ecliptic.rotation_at(t0).T @ in_ecliptic_of_t0

    def ayanamsa(self, jd_ut: np.ndarray | float) -> np.ndarray:
        rotation = self._ecliptic.rotation_at(self._time(jd_ut))
        vector = np.einsum("ij...,j->i...", rotation, self._ayanamsa_direction)
        return np.mod(np.degrees(np.arctan2(vector[1], vector[0])), 360.0)

    # -- horizon events ---------------------------------------------------

    def _events(self, finder, jd_start: float, jd_end: float) -> np.ndarray:
        times, above = finder(
            self._observer, self._sun, self._ts.ut1_jd(jd_start), self._ts.ut1_jd(jd_end)
        )
        above = np.asarray(above, dtype=bool)
        if not above.all():
            # Only possible above the polar circles. At 33 deg N it cannot
            # happen, so it means the location was misconfigured rather than
            # that the Sun genuinely failed to rise.
            raise ConfigError(
                f"The Sun does not rise or set on every day of {jd_start}..{jd_end} "
                f"at {self.location.name} ({self.location.latitude}, "
                f"{self.location.longitude}). Check the latitude."
            )
        return np.asarray(times.ut1, dtype="float64")

    def risings(self, jd_start: float, jd_end: float) -> np.ndarray:
        return self._events(self._almanac.find_risings, jd_start, jd_end)

    def settings(self, jd_start: float, jd_end: float) -> np.ndarray:
        return self._events(self._almanac.find_settings, jd_start, jd_end)


def _download_kernel(path: Path) -> None:
    """Fetch a JPL kernel, resuming across the connection resets this network throws.

    ``certifi``'s bundle is used explicitly rather than the system trust store:
    a TLS-intercepting middlebox on the owner's network presents a self-signed
    chain that the system store rejects and certifi accepts.
    """
    import shutil
    import ssl
    import urllib.request

    try:
        import certifi
    except ImportError as exc:  # pragma: no cover
        raise EphemerisUnavailable(
            f"Cannot fetch {path.name}: certifi is not installed and the system "
            "trust store is not usable on this network."
        ) from exc

    path.parent.mkdir(parents=True, exist_ok=True)
    context = ssl.create_default_context(cafile=certifi.where())
    partial = path.with_suffix(path.suffix + ".part")
    failures: list[str] = []

    for attempt in range(12):
        have = partial.stat().st_size if partial.exists() else 0
        url = _KERNEL_URLS[attempt % len(_KERNEL_URLS)].format(name=path.name)
        request = urllib.request.Request(url)
        if have:
            request.add_header("Range", f"bytes={have}-")
        try:
            with urllib.request.urlopen(request, timeout=60, context=context) as response:
                if have and response.status != 206:
                    partial.unlink(missing_ok=True)
                    have = 0
                with partial.open("ab" if have else "wb") as handle:
                    shutil.copyfileobj(response, handle, length=1 << 16)
            partial.replace(path)
            return
        except Exception as exc:  # noqa: BLE001 - retried, then reported in full
            failures.append(f"{url}: {type(exc).__name__}: {exc}")

    raise EphemerisUnavailable(
        f"Could not download the ephemeris kernel to {path} after "
        f"{len(failures)} attempts. Place a copy there by hand, or point "
        "ephemeris.kernel_dir at one. Attempts:\n  " + "\n  ".join(failures)
    )


# --------------------------------------------------------------------------
# Swiss Ephemeris.
# --------------------------------------------------------------------------


class SwissEphemerisBackend(Backend):
    """The reference implementation, kept selectable as a cross-check.

    Not the default only because ``pyswisseph`` is source-only on Windows and
    the machine that generates ``results/`` has no MSVC toolchain. On a machine
    that can build it, flipping ``backend`` in the config regenerates the whole
    festival table under an independent implementation, and
    ``tests/test_calendar.py`` scores both against the same published dates.
    """

    name = "swisseph"

    def __init__(self, location: Location, ephe_path: Path | None = None) -> None:
        try:
            import swisseph as swe
        except ImportError as exc:
            raise EphemerisUnavailable(
                "backend 'swisseph' is declared in experiments/configs/calendar.yaml "
                f"but pyswisseph could not be imported ({exc}). It is source-only "
                "on Windows and needs an MSVC toolchain; see docs/ephemeris.md. "
                "Install it, or declare backend: skyfield. This is not falling "
                "back to skyfield on its own -- that is the failure mode in "
                "CLAUDE.md 3.6."
            ) from exc

        self._swe = swe
        self.location = location
        if ephe_path is not None:
            swe.set_ephe_path(str(ephe_path))
        swe.set_sid_mode(swe.SIDM_LAHIRI, 0, 0)
        self._flags = swe.FLG_SWIEPH
        self._geopos = (location.longitude, location.latitude, location.elevation_m)

    def _body_longitude(self, body: int, jd_ut: np.ndarray | float) -> np.ndarray:
        scalar = np.ndim(jd_ut) == 0
        values = np.atleast_1d(np.asarray(jd_ut, dtype="float64"))
        out = np.empty(values.shape, dtype="float64")
        for index, jd in np.ndenumerate(values):
            position, _ = self._swe.calc_ut(float(jd), body, self._flags)
            out[index] = position[0]
        out = np.mod(out, 360.0)
        return out[()] if scalar else out

    def sun_longitude(self, jd_ut: np.ndarray | float) -> np.ndarray:
        return self._body_longitude(self._swe.SUN, jd_ut)

    def moon_longitude(self, jd_ut: np.ndarray | float) -> np.ndarray:
        return self._body_longitude(self._swe.MOON, jd_ut)

    def ayanamsa(self, jd_ut: np.ndarray | float) -> np.ndarray:
        scalar = np.ndim(jd_ut) == 0
        values = np.atleast_1d(np.asarray(jd_ut, dtype="float64"))
        out = np.array([self._swe.get_ayanamsa_ut(float(jd)) for jd in values])
        return out[0] if scalar else out

    def _horizon_events(self, flag: int, jd_start: float, jd_end: float) -> np.ndarray:
        events: list[float] = []
        cursor = jd_start
        while cursor < jd_end:
            code, times = self._swe.rise_trans(
                cursor, self._swe.SUN, self._geopos, rsmi=flag, flags=self._flags
            )
            if code < 0 or not times or times[0] > jd_end:
                break
            events.append(times[0])
            cursor = times[0] + 0.1
        return np.asarray(events, dtype="float64")

    def risings(self, jd_start: float, jd_end: float) -> np.ndarray:
        return self._horizon_events(self._swe.CALC_RISE, jd_start, jd_end)

    def settings(self, jd_start: float, jd_end: float) -> np.ndarray:
        return self._horizon_events(self._swe.CALC_SET, jd_start, jd_end)


# --------------------------------------------------------------------------
# Selection. By name, from config. Never by probing.
# --------------------------------------------------------------------------

BACKENDS = ("skyfield", "swisseph")


def build(config: dict) -> Backend:
    """Construct the backend the config names, or raise.

    There is no ``try skyfield except ImportError: try swisseph`` here, and
    there must not be one. Which library computed a festival date has to be a
    fact recorded in the config, not an accident of what happened to be
    installed on the machine that ran ``make calendar``.
    """
    name = config.get("backend")
    if name is None:
        raise ConfigError(
            "calendar.yaml declares no 'backend'. It is required and has no "
            f"default. Choose one of {list(BACKENDS)}."
        )
    if name not in BACKENDS:
        raise ConfigError(f"Unknown ephemeris backend {name!r}. Known: {list(BACKENDS)}.")

    ayanamsa = config.get("ayanamsa", "lahiri")
    if ayanamsa != "lahiri":
        raise ConfigError(
            f"ayanamsa: {ayanamsa!r} is not implemented. Only 'lahiri' is, and it "
            "is what the almanacs in tests/test_calendar.py use. Adding another "
            "means adding its defining epoch to ephemeris.py, not loosening "
            "this check."
        )

    location = _location(config)
    settings = config.get("ephemeris", {}) or {}

    if name == "skyfield":
        return SkyfieldBackend(
            location,
            kernel_dir=Path(settings.get("kernel_dir", "data/ephemeris")),
            kernel=settings.get("kernel", "de421.bsp"),
            allow_download=bool(settings.get("allow_download", True)),
        )

    ephe_path = settings.get("ephe_path")
    return SwissEphemerisBackend(location, Path(ephe_path) if ephe_path else None)


def _location(config: dict) -> Location:
    block = config.get("location")
    if not block:
        raise ConfigError("calendar.yaml declares no 'location'. Sunrise needs one.")
    missing = [
        key
        for key in ("name", "latitude", "longitude", "elevation_m", "timezone")
        if key not in block
    ]
    if missing:
        raise ConfigError(f"calendar.yaml location is missing {missing}.")
    return Location(
        name=str(block["name"]),
        latitude=float(block["latitude"]),
        longitude=float(block["longitude"]),
        elevation_m=float(block["elevation_m"]),
        timezone=str(block["timezone"]),
    )
