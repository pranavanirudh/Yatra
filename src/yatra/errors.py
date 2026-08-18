"""Failure modes that must stop the pipeline.

Every exception here exists because the alternative -- a warning, a default, a
silently dropped row -- would let the pipeline emit a plausible number instead
of crashing. That is the failure class this project is built against
(docs/claude_code_brief.md, section 5).

None of these has a ``strict=False`` escape hatch, and none should acquire one.
"""

from __future__ import annotations


class YatraError(Exception):
    """Base for every error this package raises deliberately."""


class MissingObservations(YatraError):
    """A required observation file is absent.

    Raised instead of returning an empty frame, generating a placeholder, or
    falling back to a bundled sample. There is no bundled sample.
    """


class ContractViolation(YatraError):
    """The observation files exist but do not satisfy the data contract.

    Gaps in the monthly series, non-integer counts, dangling source ids, or an
    annual total that does not reconcile against the sum of its months.
    """


class MissingCitation(YatraError):
    """A shock window has no source, or a source is missing required fields.

    An undocumented shock window is an unfalsifiable claim about which months
    were disrupted, and the entire finding is a comparison across that line.
    """


class CalendarRoutingError(YatraError):
    """A model declaring ``needs_calendar`` was about to be fit without it.

    This is the named failure mode. A rename once broke suffix-based routing and
    the ablation arm trained featureless, which read as a null result. Now it
    raises here instead.
    """


class RaggedPanel(YatraError):
    """Models were not scored on an identical origin set.

    Raised after the backtest completes, before anything is written. A ragged
    panel means the per-regime leaderboards compare different subsets of
    history, which is not a comparison.
    """


class EphemerisUnavailable(YatraError):
    """The configured ephemeris backend could not be loaded.

    Deliberately fatal. Trying the configured backend, catching ImportError and
    quietly computing with a different one would reproduce the exact failure
    class this project is designed against -- the numbers would still look fine.
    """


class ConfigError(YatraError):
    """A config file is malformed, or asks for something unsupported."""


class LeakageError(YatraError):
    """A model was handed information unavailable at its forecast origin.

    Guards the Step 3 switching model: its break detector may read the
    observation window up to the origin and nothing else. In particular it may
    never read the declared shock windows, which are evaluation labels.
    """
