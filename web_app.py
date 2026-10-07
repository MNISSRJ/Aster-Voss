from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel
from agent import AsterVoss
from llm.base import LLMMessage
from llm.factory import create_provider, available_providers
from aster import AGENT_IDENTITY, AGENT_TAGLINE, get_memory
from config import load_config
from memory.persistence import long_term_context, load_history, save_history
from memory import brain, cloud
from memory import extractor
from automations import list_automations
from memory.service import MemoryService
from services.conversation_service import ConversationService
from services.radar_service import RadarService
from services.bts_radar_service import BTSRadarService
from pathlib import Path
import hashlib
import hmac
import json
import os
import threading
import time
from uuid import uuid4

import log
from rate_limit import RateLimiter, rate_limit_rule
from feature_flags import radar_2_enabled

CONFIG = load_config()
log.configure(CONFIG.log_level)
MEMORY = MemoryService()
CONVERSATIONS = ConversationService()
RADAR = RadarService()
BTS_RADAR = BTSRadarService()
RATE_LIMITER = RateLimiter()
_LOCAL_CHAT_LOCK = threading.Lock()

def build_prompt(user_id: str = MEMORY.user_id):
    m = MEMORY.context()
    growth = ""
    growth_path = Path(__file__).resolve().parent / "memory" / "GROWTH_LOG.md"
    try:
        growth = growth_path.read_text(encoding="utf-8")
    except OSError:
        growth = ""
    parts = [AGENT_IDENTITY.render_system_prompt()]
    if m:
        parts.append(m)
    if growth:
        parts.append(
            "<shared_growth_history>\n"
            "These are a few curated milestones in Aster and Mint's shared history. "
            "Use them naturally when relevant; never recite the log unless asked.\n"
            + growth
            + "\n</shared_growth_history>"
        )
    return "\n\n".join(parts)

app = FastAPI(title="Aster Voss")


def _rate_limit_client_identity(request: Request) -> str:
    if CONFIG.require_auth:
        authorization = request.headers.get("authorization", "")
        return "token:" + hashlib.sha256(authorization.encode("utf-8")).hexdigest()
    forwarded = request.headers.get("x-real-ip") or request.headers.get("x-forwarded-for", "")
    if forwarded:
        raw = forwarded.split(",", 1)[0].strip()
    else:
        raw = request.client.host if request.client else "unknown"
    return "ip:" + raw


@app.middleware("http")
async def access_control_and_observability(request: Request, call_next):
    started = time.perf_counter()
    request_id = request.headers.get("x-request-id") or uuid4().hex
    if CONFIG.require_auth and request.url.path not in {"/", "/api/status"}:
        expected = os.getenv("ASTER_ACCESS_TOKEN", "")
        provided = request.headers.get("authorization", "")
        expected_header = "Bearer " + expected
        if not expected or not hmac.compare_digest(provided, expected_header):
            response = JSONResponse({"error": "unauthorized", "request_id": request_id}, status_code=401)
            response.headers["X-Request-ID"] = request_id
            response.headers["X-Server-Time"] = str(int(time.time()))
            return response

    rule = rate_limit_rule(request.method.upper(), request.url.path)
    if rule:
        scope, limit, window_seconds = rule
        decision = RATE_LIMITER.check(
            scope,
            RATE_LIMITER.client_key(_rate_limit_client_identity(request)),
            limit,
            window_seconds,
        )
        if not decision.allowed:
            status_code = 503 if decision.backend in {"supabase-unavailable", "disabled-serverless"} else 429
            response = JSONResponse(
                {
                    "ok": False,
                    "error": decision.error or "请求过于频繁，请稍后再试。",
                    "request_id": request_id,
                    "rate_limit_backend": decision.backend,
                },
                status_code=status_code,
            )
            response.headers["X-Request-ID"] = request_id
            response.headers["X-Server-Time"] = str(int(time.time()))
            if decision.retry_after:
                response.headers["Retry-After"] = str(decision.retry_after)
            response.headers["X-RateLimit-Limit"] = str(decision.limit)
            if decision.remaining is not None:
                response.headers["X-RateLimit-Remaining"] = str(decision.remaining)
            response.headers["X-Aster-RateLimit-Backend"] = decision.backend
            return response

    try:
        response = await call_next(request)
    except Exception:
        log.error("request_id=%s method=%s path=%s status=500 latency_ms=%.1f", request_id, request.method, request.url.path, (time.perf_counter() - started) * 1000)
        raise
    latency_ms = (time.perf_counter() - started) * 1000
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Server-Time"] = str(int(time.time()))
    if rule:
        response.headers["X-Aster-RateLimit-Backend"] = RATE_LIMITER.backend_status
    log.info("request_id=%s method=%s path=%s status=%s latency_ms=%.1f", request_id, request.method, request.url.path, response.status_code, latency_ms)
    return response


def _message_dicts(messages):
    return [
        {"role": m.role, "content": m.content}
        for m in messages
        if m.role in {"user", "assistant"}
        and isinstance(m.content, str)
        and m.content.strip()
    ][-80:]


def _run_local_chat(message: str):
    # Local file history requires one transaction lock across read -> model -> write.
    # Atomic replacement prevents partial files, but not lost updates from
    # concurrent read/modify/write requests.
    with _LOCAL_CHAT_LOCK:
        history = [
            {"role": m.role, "content": m.content}
            for m in load_history()
            if m.role in {"user", "assistant"} and isinstance(m.content, str)
        ]
        request_agent = _agent_from_messages(history)
        result = request_agent.run(message)
        save_history(request_agent.messages)
        return result


def _conversation_title(text: str) -> str:
    clean = " ".join((text or "").strip().split())
    if not clean:
        return "新对话"
    return clean[:30] + ("…" if len(clean) > 30 else "")


def _agent_from_messages(history):
    a = AsterVoss(
        CONFIG,
        system_prompt=build_prompt(),
        identity_name=AGENT_IDENTITY.name,
        identity_tagline=AGENT_TAGLINE,
        restore_history=False,
        persist_history=False,
    )
    restored = []
    for item in history or []:
        if (
            isinstance(item, dict)
            and item.get("role") in {"user", "assistant"}
            and isinstance(item.get("content"), str)
            and item["content"].strip()
        ):
            restored.append(LLMMessage(role=item["role"], content=item["content"]))
    a._messages = [LLMMessage.system(build_prompt())] + restored
    return a


class ChatIn(BaseModel):
    message: str
    conversation_id: str | None = None
    radar_context: dict | None = None


class RadarEventIn(BaseModel):
    item_id: str
    event_type: str
    metadata: dict = {}


class ConversationRefIn(BaseModel):
    conversation_id: str | None = None


class MemoryIn(BaseModel):
    text: str


class MemoryEditIn(BaseModel):
    text: str


@app.get("/", response_class=HTMLResponse)
def home():
    template = Path(__file__).resolve().parent / "templates" / "index.html"
    try:
        html = template.read_text(encoding="utf-8")
        if radar_2_enabled():
            html = html.replace("</head>", "<script>window.RADAR_2_ENABLED=true;</script></head>", 1)
        return HTMLResponse(html)
    ex