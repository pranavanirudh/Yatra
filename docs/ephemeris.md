# The ephemeris backend

`src/yatra/ephemeris.py` selects a backend by name from
[experiments/configs/calendar.yaml](../experiments/configs/calendar.yaml). It
does not try one, catch `ImportError`, and quietly use another. If the named
backend cannot load, the calendar stage raises `EphemerisUnavailable` and the
run stops.

That rule is CLAUDE.md §3.6, and it is not fussiness. Silent backend fallback is
the §5 failure mode wearing a different hat: two backends disagree about a tithi
boundary by minutes, minutes decide a contested festival date, a contested
festival date moves a column of `results/calendar.csv`, and the ablation arm
reports a different number with nothing in the log to say why.

---

## Decision

**`skyfield` is the declared backend.** Recorded 2026-08-18.

`swisseph` remains implemented and selectable. It is not the default.

### Why not `swisseph`

Swiss Ephemeris is the reference implementation for Hindu calendrics and would
otherwise be the obvious choice. `pyswisseph` ships source-only on Windows and
needs an MSVC toolchain to build. The owner's machine does not have one, so on
the machine that actually produces `results/`, the reference implementation is
not installable. A backend that cannot run where the artefacts are generated is
not a backend.

It stays in the code because it is the natural cross-check: when a machine with
a toolchain is available, flipping one line in the config and re-running
`make calendar` regenerates the whole festival table under an independent
implementation, and `tests/test_calendar.py` scores both against the same
published dates.

### Why `skyfield`

- Pure Python over JPL DE kernels via `jplephem`. Installs anywhere `numpy` does.
- Reads the JPL kernels directly, so the underlying solar-system model is the
  same family Swiss Ephemeris compresses. The two are not independent in their
  physics; they are independent in their code, which is the failure mode that
  bites.
- `skyfield.almanac` gives rising and setting times with the standard
  refraction and semidiameter conventions, which the sunrise-based tithi rules
  need.

### What Skyfield does not give, and what we do about it

Skyfield has no sidereal zodiac and no ayanāṁśa. `ephemeris.py` computes Lahiri
itself, by the same construction Swiss Ephemeris uses: take the reference epoch
(TT JD 2435553.5, 1956 Jan 1) at which Lahiri is defined to be 23.25018278° −
0.00466022°, treat the point at that tropical longitude on that date's ecliptic
as a fixed inertial direction, and report its tropical longitude at the date
asked for. Precession does the rest.

Two consequences worth stating:

- The ayanāṁśa is computed in the **true ecliptic and equinox of date**, the
  same frame as the Sun's apparent longitude. Sidereal longitude is the
  difference of the two, so nutation cancels exactly rather than being
  approximately right. This matters because a ±17″ nutation term is ~7 minutes
  of Sun motion, and a sankrānti landing 7 minutes on the wrong side of a new
  moon renames a lunar month and can invent or erase an adhika māsa.
- Ayanāṁśa affects **only** sankrāntis, and sankrāntis affect **only** month
  naming. Tithi is a difference of two longitudes, so every ayanāṁśa term
  cancels out of it. A festival's date is a tithi question; its month label is
  an ayanāṁśa question.

## The kernel

`de421.bsp`, 16 MB, covering 1900–2050 — the observation window (1986 onward)
plus room past any forecast horizon. It is downloaded on demand into
`ephemeris.kernel_dir` from the config, and it is **git-ignored**: it is a
16 MB binary reproducible from a stable public URL, and committing it would put
a redistributed copy of someone else's data in this repository.

The download uses `certifi`'s CA bundle explicitly rather than the system trust
store. On the owner's network a TLS-intercepting middlebox presents a
self-signed chain that the system store rejects, and `certifi` accepts.

If the kernel is absent and cannot be fetched, the calendar stage raises
`EphemerisUnavailable` naming the path and the URL. It does not fall back to a
lower-precision series.

## Accuracy actually needed

The rules in `panchanga.py` ask two kinds of question:

| Question | Sensitivity |
|---|---|
| Which tithi is running at sunrise on day D? | Tithi advances ~12°/day, so 1′ of longitude error ≈ 2 minutes of time. A wrong answer needs the boundary to fall within minutes of sunrise. |
| Which lunar month contains this sankrānti? | The Sun moves ~1°/day. Needs the sankrānti within minutes of a new moon. |

DE421 is good to milliarcseconds for the Sun and Moon over this window, which
is five orders of magnitude more than either question needs. **The error budget
here is dominated by rule interpretation, not by astronomy** — whether a
festival follows sunrise, midnight, or evening observance decides more dates
than any plausible ephemeris difference. Those choices are declared per festival
in `calendar.yaml` under `observance`, and validated in `tests/test_calendar.py`
against published almanacs.
