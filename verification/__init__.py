"""External verification for the Maya stabilization protocol.

OpenCode's controlled-condition sweep: runs the full test battery, launches
the runtime in isolation, monitors for any unintended or unexpected behavior,
and produces the stabilization report that -- together with Maya's internal
self-check -- decides ready state.
"""
from __future__ import annotations

from .manifest import CONTROLLED_RUNTIME, SUITES
from .report import stabilization_report
from .runner import launch_runtime, run_suite, sweep

__version__ = "1.0.0"

__all__ = [
    "__version__",
    "SUITES",
    "CONTROLLED_RUNTIME",
    "run_suite",
    "sweep",
    "launch_runtime",
    "stabilization_report",
]