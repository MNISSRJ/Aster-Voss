"""Small, explainable behavior adjustments for research recommendations.

This module is pure: callers supply event and trusted concept records. It does
not read or write cloud storage, and missing event history preserves cold-start
ranking unchanged.
"""
from __future__ import annotations

import math
import os
from datetime import datetime, timezone
from typing import Any, Iterable


DEFAULT_SIGNAL_WEIGHTS = {
    "item_favorite": 4.0,
    "open_original": 3.0,
    "ask_aster": 2.5,
    "item_click": 2.0,
    "item_view": 0.5,
    "item_dislike": -3.0,
}


def _configured_weight(event_type: str) -> float:
    default = DEFAULT_SIGNAL_WEIGHTS[event_type]
    try:
        return float(os.getenv(f"RADAR_SIGNAL_WEIGHT_{event_type.upper()}", default))
    except (TypeError, ValueError):
        return default


def _date(value: Any) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


def _terms(value: Any) -> set[str]:
    if isinstance(value, str):
        return {value.strip().casefold()} if value.strip() else set()
    if isinstance(value, (list, tuple, set)):
        return {str(item).strip().casefold() for item in value if str(item).strip()}
    return set()


def _event_similarity(paper: dict[str, Any], event: dict[str, Any]) -> float:
    """Exact item match or limited topic/concept overlap; never infer broad taste."""
    if str(event.get("item_id", "")) and str(event.get("item_id")) == str(paper.get("id", "")):
        return 1.0
    metadata = event.get("metadata") if isinstance(event.get("metadata"), dict) else {}
    event_terms = _terms(metadata.get("topics")) | _terms(metadata.get("core_concepts"))
    paper_terms = _terms(paper.get("topics")) | _terms(paper.get("core_concepts"))
    return min(1.0, len(event_terms & paper_terms) / max(1, len(event_terms))) if event_terms else 0.0


def personalize_ranked(
    papers: Iterable[dict[str, Any]], events: Iterable[dict[str, Any]] = (), *,
    trusted_concepts: Iterable[str] = (), now: datetime | None = None,
    half_life_days: float | None = None, exploration_fraction: float = 0.2,
) -> list[dict[str, Any]]:
    """Apply decaying feedback and reserve a small, quality-bounded exploration mix.

    Negative feedback is a temporary score penalty capped at 0.12. Exploration
    draws from the existing ranked candidate set and never promotes a candidate
    below the normal quality floor. Concept links require exact trusted data.
    """
    ranked = [dict(item) for item in papers]
    event_rows = [dict(row) for row in events if isinstance(row, dict)]
    if not ranked:
        return []
    now = now or datetime.now(timezone.utc)
    try:
        half_life = max(1.0, float(half_life_days if half_life_days is not None else os.getenv("RADAR_FEEDBACK_HALF_LIFE_DAYS", "28")))
    except (TypeError, ValueError):
        half_life = 28.0
    scored = []
    for original_index, paper in enumerate(ranked):
        base = float(paper.get("_score", paper.get("score", 0.5)))
        adjustment = 0.0
        negative = 0.0
        for event in event_rows:
            event_type = str(event.get("event_type", ""))
            if event_type not in DEFAULT_SIGNAL_WEIGHTS:
                continue
            occurred = _date(event.get("occurred_at") or event.get("created_at"))
            age_days = max(0.0, (now - occurred).total_seconds() / 86400) if occurred else half_life * 4
            decay = math.exp(-math.log(2) * age_days / half_life)
            similarity = _event_similarity(paper, event)
            contribution = _configured_weight(event_type) * decay * similarity
            adjustment += contribution
            if event_type == "item_dislike":
                negative += abs(contribution)
        # Keep personalized behavior a secondary signal, and dislike temporary.
        adjustment = max(-0.12, min(0.12, adjustment * 0.015))
        result = dict(paper)
        result["_base_score"] = base
        result["_score"] = base + adjustment
        result["_feedback_penalty"] = min(0.12, negative * 0.015)
        paper_topics = _terms(paper.get("topics"))
        interacted_topics = set()
        for event in event_rows:
            meta = event.get("metadata") if isinstance(event.get("metadata"), dict) else {}
            interacted_topics |= _terms(meta.get("topics")) | _terms(meta.get("core_concepts"))
        result["_exploration"] = bool(interacted_topics and not (paper_topics & interacted_topics))
        trusted = {str(x).strip() for x in trusted_concepts if str(x).strip()}
        concepts = [str(x).strip() for x in paper.get("core_concepts", []) if str(x).strip()] if isinstance(paper.get("core_concepts"), list) else []
        result["trusted_concept_links"] = [name for name in concepts if name in trusted][:3]
        scored.append((result, original_index))
    scored.sort(key=lambda pair: (pair[0]["_score"], -pair[1]), reverse=True)
    if event_rows and len(scored) >= 3:
        fraction = max(0.0, min(0.5, float(exploration_fraction)))
        count = min(len(scored) - 1, int(len(scored) * fraction))
        if count:
            floor = max(0.0, float(scored[0][0]["_base_score"]) - 0.35)
            explored = [pair for pair in scored[1:] if pair[0]["_exploration"] and pair[0]["_base_score"] >= floor]
            if explored:
                chosen = explored[:count]
                chosen_ids = {id(pair[0]) for pair in chosen}
                remaining = [pair for pair in scored if id(pair[0]) not in chosen_ids]
                # Interleave exploration so its placement is visible without
                # replacing the strongest recommendation.
                result = [remaining[0]]
                remainder = remaining[1:]
                stride = max(2, round(1 / max(fraction, 0.01)))
                for index, pair in enumerate(chosen):
                    insert_at = min(len(result), 1 + index * stride)
                    result.insert(insert_at, pair)
                result.extend(remainder)
                scored = result
    return [item for item, _ in scored]

