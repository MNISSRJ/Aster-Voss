"""Cloud long-term memory for Aster Voss.

Uses Supabase PostgREST when configured. Local memory remains as a development
fallback, while the web deployment can keep durable memory in the cloud.
"""
from __future__ import annotations
import json, os
from datetime import datetime, timezone
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

TABLE = "aster_memory"
DEFAULT_USER_ID = (os.getenv("ASTER_DEFAULT_USER_ID") or "mint").strip() or "mint"
CONVERSATION_TABLE = "aster_conversations"
AI_BRIEF_TABLE = "ai_radar_briefs"

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

def load(user_id: str = DEFAULT_USER_ID) -> list[dict]:
    if not enabled(): return []
    try:
        rows = _request("GET", f"{TABLE}?user_id=eq.{user_id}&select=memory&limit=1")
        if rows and isinstance(rows, list):
            memory = rows[0].get("memory")
            return memory if isinstance(memory, list) else []
    except Exception:
        pass
    return []

def save(memory: list[dict], user_id: str = DEFAULT_USER_ID) -> bool:
    if not enabled():
        return False
    try:
        existing = _request("GET", f"{TABLE}?user_id=eq.{user_id}&select=user_id&limit=1")
        if existing:
            _request("PATCH", f"{TABLE}?user_id=eq.{user_id}", {"memory": memory})
        else:
            _request("POST", TABLE, {"user_id": user_id, "memory": memory})
        return True
    except Exception:
        return False


def _utc_now():
    return datetime.now(timezone.utc).isoformat()

def list_conversations(user_id: str = DEFAULT_USER_ID) -> list[dict]:
    if not enabled():
        return []
    try:
        rows = _request(
            "GET",
            f"{CONVERSATION_TABLE}?user_id=eq.{user_id}&select=id,title,created_at,updated_at&order=updated_at.desc",
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
            f"{CONVERSATION_TABLE}?id=eq.{conversation_id}&user_id=eq.{user_id}&select=id,title,messages,created_at,updated_at&limit=1",
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
            f"{CONVERSATION_TABLE}?id=eq.{conversation_id}&user_id=eq.{user_id}&select=id&limit=1",
        )
        if existing:
            _request(
                "PATCH",
                f"{CONVERSATION_TABLE}?id=eq.{conversation_id}&user_id=eq.{user_id}",
                payload,
            )
        else:
            payload["id"] = conversation_id
            _request("POST", CONVERSATION_TABLE, payload)
        return True
    except Exception:
        return False

def delete_conversation(conversation_id: str, user_id: str = DEFAULT_USER_ID) -> bool:
    if not enabled() or not conversation_id:
        return False
    try:
        _request(
            "DELETE",
            f"{CONVERSATION_TABLE}?id=eq.{conversation_id}&user_id=eq.{user_id}",
        )
        return True
    except Exception:
        return False


def save_ai_brief(brief_date: str, payload: dict, user_id: str = DEFAULT_USER_ID) -> bool:
    if not enabled() or not brief_date:
        return False
    try:
        body = {"user_id": user_id, "payload": payload, "updated_at": _utc_now()}
        existing = _request(
            "GET",
            f"{AI_BRIEF_TABLE}?brief_date=eq.{brief_date}&user_id=eq.{user_id}&select=brief_date&limit=1",
        )
        if existing:
            _request(
                "PATCH",
                f"{AI_BRIEF_TABLE}?brief_date=eq.{brief_date}&user_id=eq.{user_id}",
                body,
            )
        else:
            body["brief_date"] = brief_date
            _request("POST", AI_BRIEF_TABLE, body)
        return True
    except Exception:
        return False

def load_ai_brief(brief_date: str, user_id: str = DEFAULT_USER_ID):
    if not enabled() or not brief_date:
        return None
    try:
        rows = _request(
            "GET",
            f"{AI_BRIEF_TABLE}?brief_date=eq.{brief_date}&user_id=eq.{user_id}&select=brief_date,payload,updated_at&limit=1",
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
            f"{AI_BRIEF_TABLE}?user_id=eq.{user_id}&select=brief_date,payload,updated_at&order=brief_date.desc&limit={max(1, min(int(limit), 30))}",
        )
        return rows if isinstance(rows, list) else []
    except Exception:
        return []
