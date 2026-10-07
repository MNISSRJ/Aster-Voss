"""Environment-backed feature flags.

Radar 2.0 stays disabled unless an environment explicitly opts in. In
particular, Production remains on the legacy Radar behavior by default.
"""
from __future__ import annotations

import os


def radar_2_enabled() -> bool:
    """Return whether Radar 2.0 is enabled in this deployment."""
    return (os.getenv("RADAR_2_ENABLED", "false") or "false").strip().lower() in {
        "1", "true", "yes", "y", "on"
    }


def radar_2_events_enabled() -> bool:
    """Require a separate opt-in before Radar event data can be written."""
    return (os.getenv("RADAR_2_EVENTS_ENABLED", "false") or "false").strip().lower() in {
        "1", "true", "yes", "y", "on"
    }
