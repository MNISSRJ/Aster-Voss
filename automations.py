"""Small automation registry used by scheduled Aster skills."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AutomationDefinition:
    name: str
    description: str
    schedule: str
    skill: str
    enabled: bool = True


AUTOMATIONS = (
    AutomationDefinition(
        name="ai_radar_daily",
        description="Generate and archive the daily AI Radar brief.",
        schedule="0 0 * * *",
        skill="ai_radar",
    ),
)


def list_automations():
    return [
        {
            "name": item.name,
            "description": item.description,
            "schedule": item.schedule,
            "skill": item.skill,
            "enabled": item.enabled,
        }
        for item in AUTOMATIONS
    ]
