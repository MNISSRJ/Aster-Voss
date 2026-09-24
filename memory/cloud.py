"""Cloud long-term memory for Aster Voss.

Uses Supabase PostgREST when configured. Local memory remains as a development
fallback, while the web deployment can keep durable memory in the cloud.
"""
from __future__ import annotations
import json, os
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

TABLE = "aster_memory"

def _cfg():
    return os.getenv("SUPABASE_URL","").rstrip("/"), os.getenv("SUPABASE_SERVICE_ROLE_KEY","")

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

def ensure_user(user_id: str = "mint"):
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

def load(user_id: str = "mint") -> list[dict]:
    if not enabled(): return []
    try:
        rows = _request("GET", f"{TABLE}?user_id=eq.{user_id}&select=memory&limit=1")
        if rows and isinstance(rows, list):
            memory = rows[0].get("memory")
            return memory if isinstance(memory, list) else []
    except Exception:
        pass
    return []

def save(memory: list[dict], user_id: str = "mint") -> bool:
    if not enabled(): return False
    try:
        _request("POST", TABLE, {"user_id": user_id, "memory": memory})
        return True
    except Exception:
        return False
