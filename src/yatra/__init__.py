"""Yatra: regime-separated forecasting of pilgrimage footfall.

The public surface is deliberately small. Import the modules you need:

    from yatra import contract, regimes, models, backtest, metrics

Nothing here loads data at import time, and nothing here has a code path that
can invent an observation. See docs/claude_code_brief.md.
"""

from __future__ import annotations

__version__ = "1.1.0"

from .errors import (
    CalendarRoutingError,
    ConfigError,
    ContractViolation,
    EphemerisUnavailable,
    LeakageError,
    MissingCitation,
    MissingObservations,
    RaggedPanel,
    YatraError,
)

__all__ = [
    "__version__",
    "YatraError",
    "MissingObservations",
    "ContractViolation",
    "MissingCitation",
    "CalendarRoutingError",
    "RaggedPanel",
    "EphemerisUnavailable",
    "ConfigError",
    "LeakageError",
]
