"""Cloud long-term memory for Aster Voss.

Uses Supabase PostgREST when configured. Local memory remains as a development
fallback, while the web deployment can keep durable memory in the cloud.
"""
from __future__ import annotations
import json, os
from datetime import datetime, timezone
from urllib.request import Request, urlopen
from urllib.parse import quote
from urllib.error import HTTPError, URLError
import log

TABLE = "aster_memory"
DEFAULT_USER_ID = (os.getenv("ASTER_DEFAULT_USER_ID") or "mint").strip() or "mint"
CONVERSATION_TABLE = "aster_conversations"
AI_BRIEF_TABLE = "ai_radar_briefs"
USAGE_TABLE = "aster_usage_events"


def _quote_filter_value(value: str) -> str:
    """Encode a value before interpolating it into a PostgREST filter URL."""
    return quote(str(value), safe="")

def _cfg():
    url = os.getenv("SUPABASE_URL", "").rstrip("/")
    # Supabase now exposes a server-side Secret Key. Keep the old service-role
    # variable as a backward-compatible fallback for existing deployments.
    key = os.getenv("SUPABASE_SECRET_KEY") or os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
    return url, key

def enabled() -> bool:
    url, key = _cfg()
    return bool(url and key)

def _request(method: str, path: str, body=None):
    url, key = _cfg()
    if not enabled():
        raise RuntimeError("cloud memory is not configured")
    data = None if body is None else json.dumps(body, ensure_ascii=False).encode("utf-8")
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    if method in {"POST","PATCH"}:
        headers["Prefer"] = "resolution=merge-duplicates,return=representation"
    req = Request(f"{url}/rest/v1/{path}", data=data, headers=headers, method=method)
    with urlopen(req, timeout=8) as r:
        raw = r.read().decode("utf-8")
        return json.loads(raw) if raw else None

def ensure_user(user_id: str = DEFAULT_USER_ID):
    if not enabled(): return False
    try:
        _request("POST", TABLE, {
            "user_id": user_id,
            "memory": [],
        })
        return True
    except HTTPError as e:
        if e.code in (409, 422):
            return True
        return False
    except (URLError, OSError, ValueError):
        return False

def load(user_id: str = DEFAULT_USER_ID) -> list[dict] | None:
    if not enabled():
        return None
    try:
        rows = _request("GET", f"{TABLE}?user_id=eq.{_quote_filter_value(user_id)}&select=memory&limit=1")
        if rows and isinstance(rows, list):
            memory = rows[0].get("memory")
            return memory if isinstance(memory, list) else []
        return []
    except Exception as exc:
        log.error("cloud memory read failed user_id=%s error=%s", user_id, type(exc).__name__)
        return None

def save(memory: list[dict], user_id: str = DEFAULT_USER_ID) -> bool:
    if not enabled():
        return False
    try:
        existing = _request("GET", f"{TABLE}?user_id=eq.{_quote_filter_value(user_id)}&select=user_id&limit=1")
        if existing:
            _request("PATCH", f"{TABLE}?user_id=eq.{_quote_filter_value(user_id)}", {"memory": memory})
        else:
            _request("POST", TABLE, {"user_id": user_id, "memory": memory})
        return True
    except Exception as exc:
        log.error("cloud memory write failed user_id=%s error=%s", user_id, type(exc).__name__)
        return False


def consume_rate_limit(
    key: str,
    window_seconds: int,
    limit: int,
):
    """Atomically consume one serverless rate-limit slot through Supabase RPC."""
    if not enabled() or not key or window_seconds < 1 or limit < 1:
        return None
    try:
        rows = _request(
            "POST",
            "rpc/consume_aster_rate_limit",
            {
                "p_key": key,
                "p_window_seconds": int(window_seconds),
                "p_limit": int(limit),
            },
        )
        if isinstance(rows, list) and rows and isinstance(rows[0], dict):
            return rows[0]
        if isinstance(rows, dict):
            return rows
    except Exception as exc:
        log.error(
            "cloud rate-limit consume failed key=%s error=%s",
            key,
            type(exc).__name__,
        )
    return None


def _utc_now():
    return datetime.now(timezone.utc).isoformat()

def list_conversations(user_id: str = DEFAULT_USER_ID) -> list[dict]:
    if not enabled():
        return []
    try:
        rows = _request(
            "GET",
            f"{CONVERSATION_TABLE}?user_id=eq.{_quote_filter_value(user_id)}&select=id,title,created_at,updated_at&order=updated_at.desc",
        )
        return rows if isinstance(rows, list) else []
    except Exception:
        return []

def load_conversation(conversation_id: str, user_id: str = DEFAULT_USER_ID):
    if not enabled() or not conversation_id:
        return None
    try:
        rows = _request(
            "GET",
            f"{CONVERSATION_TABLE}?id=eq.{_quote_filter_value(conversation_id)}&user_id=eq.{_quote_filter_value(user_id)}&select=id,title,messages,created_at,updated_at&limit=1",
        )
        if rows and isinstance(rows, list):
            row = rows[0]
            if isinstance(row.get("messages"), list):
                return row
    except Exception:
        pass
    return None

def save_conversation(
    conversation_id: str,
    title: str,
    messages: list[dict],
    user_id: str = DEFAULT_USER_ID,
    created_at: str | None = None,
) -> bool:
    if not enabled() or not conversation_id:
        return False
    try:
        now = _utc_now()
        payload = {
            "user_id": user_id,
            "title": title.strip() or "新对话",
            "messages": messages,
            "updated_at": now,
        }
        if created_at:
            payload["created_at"] = created_at

        existing = _request(
            "GET",
            f"{CONVERSATION_TABLE}?id=eq.{_quote_filter_value(conversation_id)}&user_id=eq.{_quote_filter_value(user_id)}&select=id&limit=1",
        )
        if existing:
            _request(
                "PATCH",
                f"{CONVERSATION_TABLE}?id=eq.{_quote_filter_value(conversation_id)}&user_id=eq.{_quote_filter_value(user_id)}",
                payload,
            )
        else:
            payload["id"] = conversation_id
            try:
                _request("POST", CONVERSATION_TABLE, payload)
            except HTTPError as exc:
                if exc.code != 409:
                    raise
                _request(
                    "PATCH",
                    f"{CONVERSATION_TABLE}?id=eq.{_quote_filter_value(conversation_id)}&user_id=eq.{_quote_filter_value(user_id)}",
                    payload,
                )
        return True
    except Exception as exc:
        log.error(
            "cloud conversation write failed conversation_id=%s user_id=%s error=%s",
            conversation_id,
            user_id,
            type(exc).__name__,
        )
        return False

def delete_conversation(conversation_id: str, user_id: str = DEFAULT_USER_ID) -> bool:
    if not enabled() or not conversation_id:
        return False
    try:
        _request(
            "DELETE",
            f"{CONVERSATION_TABLE}?id=eq.{_quote_filter_value(conversation_id)}&user_id=eq.{_quote_filter_value(user_id)}",
        )
        return True
    except Exception as exc:
        log.error("cloud conversation delete failed conversation_id=%s user_id=%s error=%s", conversation_id, user_id, type(exc).__name__)
        return False


def save_ai_brief(brief_date: str, payload: dict, user_id: str = DEFAULT_USER_ID) -> bool:
    if not enabled() or not brief_date:
        return False
    try:
        body = {"user_id": user_id, "payload": payload, "updated_at": _utc_now()}
        existing = _request(
            "GET",
            f"{AI_BRIEF_TABLE}?brief_date=eq.{_quote_filter_value(brief_date)}&user_id=eq.{_quote_filter_value(user_id)}&select=brief_date&limit=1",
        )
        if existing:
            _request(
                "PATCH",
                f"{AI_BRIEF_TABLE}?brief_date=eq.{_quote_filter_value(brief_date)}&user_id=eq.{_quote_filter_value(user_id)}",
                body,
            )
        else:
            body["brief_date"] = brief_date
            _request("POST", AI_BRIEF_TABLE, body)
        return True
    except Exception as exc:
        log.error("cloud radar write failed brief_date=%s user_id=%s error=%s", brief_date, user_id, type(exc).__name__)
        return False

def load_ai_brief(brief_date: str, user_id: str = DEFAULT_USER_ID):
    if not enabled() or not brief_date:
        return None
    try:
        rows = _request(
            "GET",
            f"{AI_BRIEF_TABLE}?brief_date=eq.{_quote_filter_value(brief_date)}&user_id=eq.{_quote_filter_value(user_id)}&select=brief_date,payload,updated_at&limit=1",
        )
        if rows and isinstance(rows, list):
            return rows[0]
    except Exception:
        pass
    return None

def list_ai_briefs(limit: int = 14, user_id: str = DEFAULT_USER_ID) -> list[dict]:
    if not enabled():
        return []
    try:
        rows = _request(
            "GET",
            f"{AI_BRIEF_TABLE}?user_id=eq.{_quote_filter_value(user_id)}&select=brief_date,payload,updated_at&order=brief_date.desc&limit={max(1, min(int(limit), 30))}",
        )
        return rows if isinstance(rows, list) else []
    except Exception:
        return []


def save_usage_event(
    conversation_id: str | None,
    provider: str,
    model: str,
    usage: dict | None,
    user_id: str = DEFAULT_USER_ID,
) -> bool:
    if not enabled() or not usage:
        return False
    try:
        _request(
            "POST",
            USAGE_TABLE,
            {
                "user_id": user_id,
                "conversation_id": conversation_id,
                "provider": provider,
                "model": model,
                "prompt_tokens": int(usage.get("prompt_tokens") or 0),
                "completion_tokens": int(usage.get("completion_tokens") or 0),
                "total_tokens": int(usage.get("total_tokens") or 0),
            },
        )
        return True
    except Exception as exc:
        log.error("cloud usage write failed user_id=%s error=%s", user_id, type(exc).__name__)
        return False


def usage_summary(days: int = 30, user_id: str = DEFAULT_USER_ID):
    if not enabled():
        return {"events": 0, "total_tokens": 0, "prompt_tokens": 0, "completion_tokens": 0}
    try:
        rows = _request(
            "GET",
            f"{USAGE_TABLE}?user_id=eq.{_quote_filter_value(user_id)}&select=prompt_tokens,completion_tokens,total_tokens&limit=1000",
        )
        rows = rows if isinstance(rows, list) else []
        return {
            "events": len(rows),
            "prompt_tokens": sum(int(x.get("prompt_tokens") or 0) for x in rows),
            "completion_tokens": sum(int(x.get("completion_tokens") or 0) for x in rows),
            "total_tokens": sum(int(x.get("total_tokens") or 0) for x in rows),
        }
    except Exception:
        return {"events": 0, "total_tokens": 0, "prompt_tokens": 0, "completion_tokens": 0}


def match_memory_vectors(
    embedding: list[float],
    user_id: str = DEFAULT_USER_ID,
    limit: int = 6,
    threshold: float = 0.72,
):
    if not enabled():
        return []
    try:
        rows = _request(
            "POST",
            "rpc/match_aster_memory",
            {
                "query_embedding": embedding,
                "match_threshold": threshold,
                "match_count": max(1, min(limit, 20)),
                "target_user_id": user_id,
            },
        )
        return rows if isinstance(rows, list) else []
    except Exception:
        return []
