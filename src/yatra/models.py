"""The model registry, and the explicit calendar routing set.

Every model is a function ``(train, horizons, calendar) -> np.ndarray`` returning
one prediction per requested horizon. They are registered by name, and the names
in :data:`NEEDS_CALENDAR` are the only ones that receive calendar features.

**Why the set is a literal.** Routing here once keyed off a ``_cal`` name suffix.
A rename broke it silently and the ablation arm trained without the features it
existed to test, which reads as a null result rather than as a bug. The set
below is written out by hand, checked against the registry at import time, and
checked again in ``tests/test_registry.py``. A rename now raises on import.
"""

from __future__ import annotations

import warnings
from collections.abc import Callable, Sequence
from dataclasses import dataclass

import numpy as np
import pandas as pd

from .errors import CalendarRoutingError, ConfigError, LeakageError

Predictor = Callable[[pd.Series, Sequence[int], pd.DataFrame | None], np.ndarray]

SEASONAL_PERIOD = 12


@dataclass(frozen=True)
class ModelSpec:
    name: str
    fn: Predictor
    needs_calendar: bool
    description: str


REGISTRY: dict[str, ModelSpec] = {}


def register(name: str, *, needs_calendar: bool = False, description: str = "") -> Callable[[Predictor], Predictor]:
    def decorate(fn: Predictor) -> Predictor:
        if name in REGISTRY:
            raise ConfigError(f"Model '{name}' is already registered.")
        REGISTRY[name] = ModelSpec(name, fn, needs_calendar, description)
        return fn

    return decorate


def _horizon_array(horizons: Sequence[int]) -> np.ndarray:
    h = np.asarray(list(horizons), dtype="int64")
    if h.ndim != 1 or len(h) == 0 or (h < 1).any():
        raise ValueError(f"Horizons must be positive integers, got {horizons!r}.")
    return h


# --------------------------------------------------------------------------
# Benchmarks. These have no free parameters, which is what makes them useful:
# when one of them wins, it is not because it was tuned harder.
# --------------------------------------------------------------------------


@register("naive", description="Repeat the last observation.")
def naive(train: pd.Series, horizons: Sequence[int], calendar: pd.DataFrame | None = None) -> np.ndarray:
    last = float(train.iloc[-1])
    return np.full(len(_horizon_array(horizons)), last)


@register("seasonal_naive", description="Repeat the observation from 12 months earlier.")
def seasonal_naive(train: pd.Series, horizons: Sequence[int], calendar: pd.DataFrame | None = None) -> np.ndarray:
    values = np.asarray(train, dtype="float64")
    if len(values) < SEASONAL_PERIOD:
        raise ValueError("seasonal_naive needs at least 12 observations.")
    h = _horizon_array(horizons)
    # For h > 12 this recycles the same seasonal cycle, which is the standard
    # definition. Horizons here top out at 6, so the branch never bites.
    offsets = ((h - 1) % SEASONAL_PERIOD) - SEASONAL_PERIOD
    return values[offsets]


@register("drift", description="Last value plus the average per-period change.")
def drift(train: pd.Series, horizons: Sequence[int], calendar: pd.DataFrame | None = None) -> np.ndarray:
    values = np.asarray(train, dtype="float64")
    if len(values) < 2:
        raise ValueError("drift needs at least 2 observations.")
    slope = (values[-1] - values[0]) / (len(values) - 1)
    return values[-1] + slope * _horizon_array(horizons)


# --------------------------------------------------------------------------
# Seasonal methods.
# --------------------------------------------------------------------------


@register("theta", description="Theta method (Assimakopoulos & Nikolopoulos), deseasonalised.")
def theta(train: pd.Series, horizons: Sequence[int], calendar: pd.DataFrame | None = None) -> np.ndarray:
    from statsmodels.tsa.forecasting.theta import ThetaModel

    h = _horizon_array(horizons)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        # method="additive" rather than the default multiplicative
        # deseasonalisation: the multiplicative path divides by a seasonal index
        # and this series contains near-zero closure months.
        model = ThetaModel(train, period=SEASONAL_PERIOD, deseasonalize=True, method="additive")
        fitted = model.fit()
        path = np.asarray(fitted.forecast(int(h.max())), dtype="float64")
    return path[h - 1]


def _holt_winters(train: pd.Series, horizons: Sequence[int], seasonal: str) -> np.ndarray:
    from statsmodels.tsa.holtwinters import ExponentialSmoothing

    h = _horizon_array(horizons)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        model = ExponentialSmoothing(
            train,
            trend="add",
            seasonal=seasonal,
            seasonal_periods=SEASONAL_PERIOD,
            initialization_method="estimated",
        )
        fitted = model.fit()
        path = np.asarray(fitted.forecast(int(h.max())), dtype="float64")
    return path[h - 1]


@register("holt_winters_add", description="Holt-Winters, additive trend and additive seasonality.")
def holt_winters_add(train: pd.Series, horizons: Sequence[int], calendar: pd.DataFrame | None = None) -> np.ndarray:
    return _holt_winters(train, horizons, "add")


@register("holt_winters_mul", description="Holt-Winters, additive trend and multiplicative seasonality.")
def holt_winters_mul(train: pd.Series, horizons: Sequence[int], calendar: pd.DataFrame | None = None) -> np.ndarray:
    # Multiplicative seasonality is undefined on a window containing a zero, and
    # a closure month can be exactly that. This raises rather than nudging the
    # data upward: on_model_failure=fail in the backtest config turns it into a
    # reported limitation instead of a silently substituted forecast.
    if (np.asarray(train, dtype="float64") <= 0).any():
        raise ValueError(
            "holt_winters_mul requires strictly positive observations; the "
            "training window contains a zero or negative month. This is a real "
            "limitation of multiplicative seasonality on a series with closures, "
            "and belongs in the results table as such."
        )
    return _holt_winters(train, horizons, "mul")


def _sarimax(train: pd.Series, horizons: Sequence[int], exog: pd.DataFrame | None, exog_future: pd.DataFrame | None) -> np.ndarray:
    from statsmodels.tsa.statespace.sarimax import SARIMAX

    h = _horizon_array(horizons)
    steps = int(h.max())
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        model = SARIMAX(
            train,
            exog=exog,
            order=(1, 1, 1),
            seasonal_order=(1, 1, 1, SEASONAL_PERIOD),
            enforce_stationarity=False,
            enforce_invertibility=False,
        )
        fitted = model.fit(disp=False)
        path = np.asarray(fitted.forecast(steps=steps, exog=exog_future), dtype="float64")
    return path[h - 1]


@register("sarima", description="SARIMA(1,1,1)(1,1,1)[12], no exogenous terms.")
def sarima(train: pd.Series, horizons: Sequence[int], calendar: pd.DataFrame | None = None) -> np.ndarray:
    return _sarimax(train, horizons, None, None)


@register(
    "sarimax_cal",
    needs_calendar=True,
    description="SARIMA(1,1,1)(1,1,1)[12] plus computed festival-calendar regressors.",
)
def sarimax_cal(train: pd.Series, horizons: Sequence[int], calendar: pd.DataFrame | None = None) -> np.ndarray:
    """The calendar arm. Its pair is ``sarima``: same order, same data, no exog.

    Calendar features are deterministic functions of the astronomical calendar,
    so future values are legitimately knowable at the origin -- that is the whole
    argument for including them, and it is why passing ``exog_future`` here is
    not leakage the way a future observation would be.
    """
    if calendar is None or calendar.empty:
        raise CalendarRoutingError(
            "sarimax_cal was called without calendar features. This model exists "
            "to test whether the calendar layer helps; fitting it featureless "
            "would produce a number identical to plain sarima and read as a null "
            "result. Refusing."
        )

    h = _horizon_array(horizons)
    steps = int(h.max())

    exog = calendar.reindex(train.index)
    if exog.isna().any().any():
        missing = exog.index[exog.isna().any(axis=1)]
        raise CalendarRoutingError(
            f"Calendar features do not cover the training window: {len(missing)} "
            f"month(s) missing, first {missing[0]:%Y-%m}. The calendar stage must "
            "run before the backtest."
        )

    future_index = pd.date_range(train.index[-1], periods=steps + 1, freq="MS")[1:]
    exog_future = calendar.reindex(future_index)
    if exog_future.isna().any().any():
        raise CalendarRoutingError(
            "Calendar features do not extend past the last origin. Compute the "
            f"calendar through {future_index[-1]:%Y-%m} before backtesting."
        )

    return _sarimax(train, horizons, exog, exog_future)


# --------------------------------------------------------------------------
# --------------------------------------------------------------------------
# The switching models, and the one-step surprise detector.
#
# Everything these models know they read out of ``train``, which by construction
# ends at the forecast origin. They never see the declared shock windows: those
# are evaluation labels, and a model that read them would be scoring against the
# answer key (CLAUDE.md 3.4).
#
# WHY THE DETECTOR WAS REPLACED
#
# The first version waited for a run of two consecutive deviating months before
# calling a break. That is the wrong shape for this series. A closure takes the
# level to zero in a single month, so a two-month confirmation rule fires only
# once the collapse is already a month old -- typically as recovery begins --
# and is mistimed in both directions: late into the shock, late out of it.
#
# The rule below needs one observation. At the origin, the seasonal model has
# already produced a one-step-ahead prediction for the month that just closed.
# Compare what actually happened against it. A month far below what the model
# expected is the signal, and it is available immediately.
#
# The comparison uses the model's own in-sample one-step residuals for scale,
# not an analytic prediction interval. An analytic interval assumes the model is
# correctly specified, which is exactly the assumption that fails when something
# unusual happens -- the interval widens least precisely when it should widen
# most.
# --------------------------------------------------------------------------

# Entry: how far BELOW its own one-step prediction the last month must fall.
SURPRISE_ENTER = 2.5

# Entry on the upside, in the same units. Six times the downside threshold, not
# a mirror of it, and the asymmetry is set by measurement rather than taste.
#
# Sweeping this against the observations: at 6.0 the upside rule fires exactly
# once in forty years -- July 2021, when footfall went from 198,490 to 500,671
# as the COVID restrictions lifted. That is a RECOVERY month, and a recovery is
# the single worst moment to hand the forecast to a level-anchored rule, because
# the level is climbing fast and any anchor undershoots every month. The largest
# positive surprises in this series are all recoveries. So a threshold low
# enough to catch surges is a threshold that switches precisely when switching
# is most expensive.
#
# 15.0 sits well clear of the largest surprise ever observed at its own origin
# (+6.57) while staying finite, so an order-of-magnitude break would still fire.
# A symmetric two-sided interval would have switched into every recovery.
SURPRISE_ENTER_UP = 15.0

# Exit: how far the surprise must climb back before the switch releases.
# Scored separately from entry because it is a separate decision with a separate
# failure mode -- see `switching_sticky`.
SURPRISE_EXIT = 1.0

# Dwell: months the switch is held after firing, before the exit rule is even
# consulted. `switching` uses 1 -- it may release the month after it fires.
# `switching_sticky` uses a half-year, which is what "reverts slowly" means
# here.
#
# A dwell is the only way to make the exit rule separately measurable on this
# series. A surprise-based exit cannot be made sticky: once the level has
# collapsed the model adapts to it within a month or two, and the surprises
# during the RECOVERY come out strongly positive (+3 to +5 through late 2020),
# so any threshold on the surprise releases immediately. Holding for a fixed
# number of months is a blunt rule, and bluntness is the point -- it isolates
# the cost of staying switched while the level climbs back.
SWITCH_DWELL = 1
SWITCH_DWELL_STICKY = 6

# Minimum history before the detector is allowed an opinion at all.
SURPRISE_MIN_HISTORY = 36

# Months of recent history used to re-anchor the level once switched.
LEVEL_WINDOW = 6


def _one_step_residuals(train: pd.Series) -> tuple[np.ndarray, np.ndarray]:
    """In-sample one-step-ahead predictions and their residuals.

    For exponential smoothing, ``fittedvalues[t]`` is the prediction of ``y[t]``
    made from the state after ``y[t-1]`` -- exactly the "what did the seasonal
    model expect for the month that just closed" quantity the detector needs,
    and it comes free with the fit the forecast already requires.
    """
    from statsmodels.tsa.holtwinters import ExponentialSmoothing

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        fitted = ExponentialSmoothing(
            train,
            trend="add",
            seasonal="add",
            seasonal_periods=SEASONAL_PERIOD,
            initialization_method="estimated",
        ).fit()
    predicted = np.asarray(fitted.fittedvalues, dtype="float64")
    actual = np.asarray(train, dtype="float64")
    return predicted, actual - predicted


def surprise_scores(train: pd.Series) -> np.ndarray:
    """One-step surprises in robust scale units. Negative means below expectation.

    Median and MAD rather than mean and standard deviation: the disruptions
    being detected are inside the sample, and a closure large enough to matter
    inflates a standard deviation enough to hide itself.
    """
    _, residual = _one_step_residuals(train)
    centre = float(np.median(residual))
    scale = 1.4826 * float(np.median(np.abs(residual - centre)))
    level = float(np.median(np.abs(np.asarray(train, dtype="float64"))))
    # Floor relative to the level, for the same reason the old detector needed
    # one: on a very regular window the MAD collapses toward zero and ordinary
    # rounding noise starts measuring thousands of "scale units".
    floor = 1e-4 * max(level, 1.0)
    if not np.isfinite(scale) or scale <= floor:
        return np.zeros_like(residual)
    return (residual - centre) / scale


def detect_shock_state(
    train: pd.Series,
    enter: float = SURPRISE_ENTER,
    exit_: float = SURPRISE_EXIT,
    enter_up: float = SURPRISE_ENTER_UP,
    dwell: int = SWITCH_DWELL,
) -> bool:
    """Is the series in a disrupted state at the end of ``train``?

    A forward pass with hysteresis: switch on when a month comes in far below
    its own one-step prediction, switch off when the surprise climbs back. Two
    thresholds rather than one, because entering and leaving are different
    decisions -- see the module comment above and ``switching_sticky``.
    """
    values = np.asarray(train, dtype="float64")
    if len(values) < SURPRISE_MIN_HISTORY:
        return False

    scores = surprise_scores(train)
    state = False
    held = 0
    for score in scores:
        if not state:
            if score < -enter or score > enter_up:
                state, held = True, 0
        else:
            held += 1
            if held >= dwell and score > -exit_:
                state = False
    return state


def _level_shifted_seasonal_naive(
    train: pd.Series, horizons: Sequence[int]
) -> np.ndarray:
    """Last year's same month, moved by however far the level has since shifted.

    During a disruption the seasonal *shape* is usually still informative -- the
    Navratri peak is still the year's peak, just smaller -- while the *level*
    from twelve months ago is stale. So the shape is kept and the level is
    re-anchored on the last few months.

    The result is not clipped at zero. Other estimators in this registry can
    return negatives too, and making this one alone non-negative would flatter
    it in exactly the regime the comparison is about.
    """
    values = np.asarray(train, dtype="float64")
    h = _horizon_array(horizons)

    recent = values[-LEVEL_WINDOW:]
    year_before = values[-LEVEL_WINDOW - SEASONAL_PERIOD : -SEASONAL_PERIOD]
    shift = float(np.median(recent) - np.median(year_before))

    offsets = ((h - 1) % SEASONAL_PERIOD) - SEASONAL_PERIOD
    return values[offsets] + shift


def _switch(
    train: pd.Series, horizons: Sequence[int], enter: float, exit_: float, dwell: int
) -> np.ndarray:
    values = np.asarray(train, dtype="float64")
    if not detect_shock_state(train, enter=enter, exit_=exit_, dwell=dwell):
        return _holt_winters(train, horizons, "add")

    if len(values) < SEASONAL_PERIOD + LEVEL_WINDOW:
        return _holt_winters(train, horizons, "add")

    # The detector may only look at months that exist. Nothing below indexes
    # past the end of the training window, and this asserts it rather than
    # trusting it: a future change that peeked would produce a spectacular
    # shock-regime score that meant nothing at all.
    if len(values) > len(train):
        raise LeakageError(
            "The switching detector read more months than the training window "
            "contains. Those months do not exist at the forecast origin."
        )
    return _level_shifted_seasonal_naive(train, horizons)


@register(
    "switching",
    description=(
        "Holt-Winters additive, switching to a level-shifted seasonal naive when "
        "the last month falls far below its own one-step prediction. Releases as "
        "soon as the surprise returns to normal."
    ),
)
def switching(
    train: pd.Series, horizons: Sequence[int], calendar: pd.DataFrame | None = None
) -> np.ndarray:
    """Fast in, fast out.

    The control branch is deliberately *identical* to ``holt_winters_add`` rather
    than merely similar, so every difference between their scores comes from
    months the detector actually acted on.
    """
    return _switch(train, horizons, SURPRISE_ENTER, SURPRISE_EXIT, SWITCH_DWELL)


@register(
    "switching_sticky",
    description=(
        "Same entry rule as `switching`, but holds the switched state for six "
        "months before the exit rule applies. Isolates the cost of reverting slowly."
    ),
)
def switching_sticky(
    train: pd.Series, horizons: Sequence[int], calendar: pd.DataFrame | None = None
) -> np.ndarray:
    """Fast in, slow out. Registered to make the exit rule separately scorable.

    ``naive``-like behaviour wins during a collapse and is badly wrong during a
    recovery, when the level is climbing fast and a lagging anchor undershoots
    every month. A detector that enters quickly and leaves slowly inherits that
    second weakness while keeping the first strength, and the only way to know
    which dominates is to score the two exit rules against each other on the
    same origin set. Entry is held fixed so the comparison isolates the exit.
    """
    return _switch(train, horizons, SURPRISE_ENTER, SURPRISE_EXIT, SWITCH_DWELL_STICKY)


# --------------------------------------------------------------------------
# Calendar routing. Literal, not derived. See the module docstring.
# --------------------------------------------------------------------------

NEEDS_CALENDAR: frozenset[str] = frozenset({"sarimax_cal"})


def _validate_registry() -> None:
    """Fail at import if the literal set and the registry have drifted apart.

    Both directions matter. A name in the set that no longer resolves means a
    model was renamed and would now silently run without features. A model
    flagged ``needs_calendar`` that is absent from the set means routing would
    skip it. Either way the arm degrades into a duplicate of its control and
    reports a null result.
    """
    unknown = sorted(NEEDS_CALENDAR - set(REGISTRY))
    if unknown:
        raise ConfigError(
            f"NEEDS_CALENDAR names models that are not registered: {unknown}. "
            "A model was renamed or removed without updating the set -- which is "
            "exactly how the calendar arm once ended up training featureless."
        )

    flagged = {name for name, spec in REGISTRY.items() if spec.needs_calendar}
    if flagged != set(NEEDS_CALENDAR):
        raise ConfigError(
            "NEEDS_CALENDAR disagrees with the registry's needs_calendar flags.\n"
            f"  set but not flagged: {sorted(set(NEEDS_CALENDAR) - flagged)}\n"
            f"  flagged but not in set: {sorted(flagged - set(NEEDS_CALENDAR))}"
        )


_validate_registry()


# --------------------------------------------------------------------------
# Ablation pairs. Literal, for the same reason NEEDS_CALENDAR is.
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Ablation:
    """Two registered models differing by exactly one design choice.

    The pair is what makes a difference in MASE readable as the worth of that
    choice rather than as the difference between two estimators. Both arms are
    scored on the same origin set with the same MASE denominator, so the gap
    cannot come from normalisation.

    ``treatment`` has the thing; ``control`` does not.
    """

    name: str
    treatment: str
    control: str
    varies: str
    question: str


# Written out by hand and checked against the registry at import, because an
# ablation whose two arms have quietly become the same model reports a null
# result and looks exactly like a real one. That is the failure this project
# already had once, in the calendar routing.
ABLATIONS: tuple[Ablation, ...] = (
    Ablation(
        name="calendar",
        treatment="sarimax_cal",
        control="sarima",
        varies="festival calendar features",
        question="do the computed festival dates earn their place as regressors?",
    ),
    Ablation(
        name="switch",
        treatment="switching",
        control="holt_winters_add",
        varies="whether the model switches at a detected break",
        question="does reacting to a break beat never reacting to one?",
    ),
    Ablation(
        name="exit_rule",
        treatment="switching_sticky",
        control="switching",
        varies="how long the switched regime is held before release",
        question="once switched, is it better to hold or to release as soon as "
                 "the break clears?",
    ),
)


def _validate_ablations() -> None:
    """Fail at import if a declared pair no longer describes a real comparison."""
    seen: set[tuple[str, str]] = set()
    for ablation in ABLATIONS:
        missing = sorted({ablation.treatment, ablation.control} - set(REGISTRY))
        if missing:
            raise ConfigError(
                f"Ablation '{ablation.name}' names unregistered model(s): {missing}. "
                "A rename left an ablation pointing at nothing, and an ablation "
                "that cannot be resolved is one nobody notices has stopped running."
            )
        if ablation.treatment == ablation.control:
            raise ConfigError(
                f"Ablation '{ablation.name}' compares '{ablation.treatment}' with "
                "itself, which measures nothing and reports zero as a finding."
            )
        pair = (ablation.treatment, ablation.control)
        if pair in seen:
            raise ConfigError(f"Ablation pair {pair} is declared more than once.")
        seen.add(pair)

    calendar = next((a for a in ABLATIONS if a.name == "calendar"), None)
    if calendar is not None:
        fed = {calendar.treatment, calendar.control} & set(NEEDS_CALENDAR)
        if fed != {calendar.treatment}:
            raise ConfigError(
                "The calendar ablation's arms do not straddle NEEDS_CALENDAR: "
                f"fed = {sorted(fed)}. Both arms fed, or neither, is the exact "
                "shape of the bug this project already had -- the arm trains "
                "like its control and the null result looks real."
            )


_validate_ablations()


def get(name: str) -> ModelSpec:
    try:
        return REGISTRY[name]
    except KeyError:
        raise ConfigError(
            f"Unknown model '{name}'. Registered: {sorted(REGISTRY)}."
        ) from None


def predict(
    name: str,
    train: pd.Series,
    horizons: Sequence[int],
    calendar: pd.DataFrame | None = None,
) -> np.ndarray:
    """Dispatch to a registered model, enforcing calendar routing.

    The routing check lives here rather than inside each model so that adding a
    model cannot accidentally opt out of it.
    """
    spec = get(name)

    if spec.needs_calendar and (calendar is None or calendar.empty):
        raise CalendarRoutingError(
            f"Model '{name}' is in NEEDS_CALENDAR but was dispatched without "
            "calendar features. Refusing to fit it featureless -- the result "
            "would be indistinguishable from its no-calendar control."
        )
    if not spec.needs_calendar and calendar is not None:
        # Not an error, but worth being explicit: passing features to a model
        # that ignores them is how an ablation quietly stops being an ablation.
        calendar = None

    out = np.asarray(spec.fn(train, horizons, calendar), dtype="float64")
    if out.shape != (len(list(horizons)),):
        raise ConfigError(
            f"Model '{name}' returned shape {out.shape}, expected "
            f"({len(list(horizons))},) -- one prediction per horizon."
        )
    return out
