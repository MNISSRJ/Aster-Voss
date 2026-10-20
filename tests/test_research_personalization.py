from datetime import datetime, timedelta, timezone

from research_personalization import personalize_ranked


NOW = datetime(2026, 10, 7, tzinfo=timezone.utc)


def paper(identifier, topics, score=0.7, concepts=()):
    return {"id": identifier, "topics": topics, "core_concepts": list(concepts), "_score": score}


def event(kind, *, item="", topics=(), age_days=0):
    date = NOW - timedelta(days=age_days)
    return {"item_id": item, "event_type": kind, "occurred_at": date.isoformat(), "metadata": {"topics": list(topics)}}


def test_empty_event_history_preserves_base_order_and_only_trusted_concepts_link():
    ranked = [paper("a", ["agent"], .8, ["MCP", "invented"]), paper("b", ["rag"], .7)]
    result = personalize_ranked(ranked, trusted_concepts=["MCP"], now=NOW)
    assert [item["id"] for item in result] == ["a", "b"]
    assert result[0]["trusted_concept_links"] == ["MCP"]
    assert result[1]["trusted_concept_links"] == []


def test_signal_strength_favorite_exceeds_view_and_is_bounded():
    ranked = [paper("fav", ["agent"], .6), paper("view", ["agent"], .6)]
    events = [event("item_favorite", item="fav"), event("item_view", item="view")]
    result = personalize_ranked(ranked, events, now=NOW)
    assert result[0]["id"] == "fav"
    assert result[0]["_score"] - result[0]["_base_score"] <= .12


def test_dislike_is_item_scoped_temporary_and_decays():
    ranked = [paper("bad", ["agent"], .7), paper("other", ["agent"], .7)]
    recent = personalize_ranked(ranked, [event("item_dislike", item="bad")], now=NOW)
    old = personalize_ranked(ranked, [event("item_dislike", item="bad", age_days=56)], now=NOW)
    assert recent[0]["id"] == "other"
    recent_penalty = next(x["_feedback_penalty"] for x in recent if x["id"] == "bad")
    old_penalty = next(x["_feedback_penalty"] for x in old if x["id"] == "bad")
    assert recent_penalty > old_penalty > 0


def test_exploration_interleaves_a_reasonably_scored_unseen_topic():
    ranked = [paper("seen", ["agent"], .9), paper("low", ["rag"], .2), paper("fresh", ["multimodal"], .78), paper("also-seen", ["agent"], .75)]
    events = [event("item_click", item="seen", topics=["agent"])]
    result = personalize_ranked(ranked, events, now=NOW, exploration_fraction=.25)
    assert result[0]["id"] == "seen"
    assert any(item["id"] == "fresh" and item["_exploration"] for item in result[:3])
    assert all(item["id"] != "low" for item in result[:3])

