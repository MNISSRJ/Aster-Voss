from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel
from agent import AsterVoss
from llm.base import LLMMessage
from llm.factory import create_provider, available_providers
from aster import AGENT_IDENTITY, AGENT_TAGLINE, get_memory
from config import load_config
from auth import OwnerTokenProvider, UserContext
from memory.persistence import long_term_context, load_history, save_history
from memory import brain, cloud
from memory import extractor
from automations import list_automations
from memory.service import MemoryService
from services.conversation_service import ConversationService
from services.radar_service import RadarService
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

CONFIG = load_config()
log.configure(CONFIG.log_level)
RATE_LIMITER = RateLimiter()
_LOCAL_CHAT_LOCK = threading.Lock()

def _trusted_context(request: Request) -> UserContext:
    context = getattr(request.state, "user_context", None)
    if not isinstance(context, UserContext) or not context.user_id:
        raise HTTPException(status_code=401, detail="unauthorized")
    return context


def memory_service(context: UserContext):
    if not isinstance(context, UserContext):
        raise TypeError("trusted UserContext required")
    return MemoryService(user_id=context.user_id)


def conversation_service(context: UserContext):
    if not isinstance(context, UserContext):
        raise TypeError("trusted UserContext required")
    return ConversationService(user_id=context.user_id)


def radar_service(context: UserContext):
    if not isinstance(context, UserContext):
        raise TypeError("trusted UserContext required")
    return RadarService(user_id=context.user_id)


def build_prompt(context: UserContext):
    if not isinstance(context, UserContext):
        raise TypeError("trusted UserContext required")
    m = memory_service(context).context()
    growth = ""
    growth_path = Path(__file__).resolve().parent / "memory" / "GROWTH_LOG.md"
    try:
        if context.is_owner:
            growth = growth_path.read_text(encoding="utf-8")
    except OSError:
        growth = ""
    parts = [AGENT_IDENTITY.render_system_prompt()]
    if m:
        parts.append(m)
    if growth:
        parts.append(
            "<shared_growth_history>\n"
            "These are owner-private milestones in Aster's history. "
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
    public_paths = {"/", "/api/status"}
    if request.url.path not in public_paths and not request.url.path.startswith("/api/cron/"):
        if CONFIG.require_auth:
            context = OwnerTokenProvider(CONFIG.access_token, CONFIG.owner_id).authenticate(
                request.headers.get("authorization", "")
            )
        elif CONFIG.local_development:
            context = UserContext(CONFIG.owner_id, is_owner=True)
        else:
            context = None
        if context is None:
            response = JSONResponse({"error": "unauthorized", "request_id": request_id}, status_code=401)
            response.headers["X-Request-ID"] = request_id
            response.headers["X-Server-Time"] = str(int(time.time()))
            return response
        request.state.user_context = context

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


def _run_local_chat(message: str, context: UserContext):
    if not isinstance(context, UserContext):
        raise TypeError("trusted UserContext required")
    # Local file history requires one transaction lock across read -> model -> write.
    # Atomic replacement prevents partial files, but not lost updates from
    # concurrent read/modify/write requests.
    with _LOCAL_CHAT_LOCK:
        history = [
            {"role": m.role, "content": m.content}
            for m in load_history()
            if m.role in {"user", "assistant"} and isinstance(m.content, str)
        ]
        request_agent = _agent_from_messages(history, context)
        result = request_agent.run(message)
        save_history(request_agent.messages)
        return result


def _conversation_title(text: str) -> str:
    clean = " ".join((text or "").strip().split())
    if not clean:
        return "新对话"
    return clean[:30] + ("…" if len(clean) > 30 else "")


def _agent_from_messages(history, context: UserContext):
    if not isinstance(context, UserContext):
        raise TypeError("trusted UserContext required")
    a = AsterVoss(
        CONFIG,
        system_prompt=build_prompt(context),
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
    a._messages = [LLMMessage.system(build_prompt(context))] + restored
    return a


class ChatIn(BaseModel):
    message: str
    conversation_id: str | None = None


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
        return HTMLResponse(template.read_text(encoding="utf-8"))
    except OSError as exc:
        return HTMLResponse(
            "Aster Voss UI is unavailable: " + type(exc).__name__,
            status_code=500,
        )



@app.post("/api/chat")
def chat(body: ChatIn, request: Request):
    context = _trusted_context(request)
    user_id = context.user_id
    conversations = conversation_service(context)
    if cloud.enabled():
        conversation_id = (body.conversation_id or "").strip() or str(uuid4())
        existing = conversations.get(conversation_id)
        history = existing.get("messages", []) if existing else []
        title = existing.get("title", "新对话") if existing else _conversation_title(body.message)
        created_at = existing.get("created_at") if existing else None

        request_agent = _agent_from_messages(history, context)
        r = request_agent.run(body.message)

        persisted = conversations.save(
            conversation_id,
            title,
            _message_dicts(request_agent.messages),
            created_at=created_at,
        )
        usage_logged = bool(cloud.save_usage_event(conversation_id, r.provider, r.model, r.usage, user_id=user_id)) if r.usage else False
        if not persisted:
            log.error("conversation persistence failed conversation_id=%s", conversation_id)
            return JSONResponse(
                status_code=503,
                content={
                    "ok": False,
                    "error": "回复已生成，但对话暂时无法保存。",
                    "text": r.text,
                    "provider": r.provider,
                    "model": r.model,
                    "conversation_id": conversation_id,
                    "title": title,
                    "conversation_persisted": False,
                    "server_time": int(time.time()),
                    "usage": r.usage,
                    "source": r.source,
                    "complexity": r.complexity,
                    "usage_logged": usage_logged,
                },
            )
        saved_record = conversations.get(conversation_id)
        return {
            "ok": True,
            "text": r.text,
            "provider": r.provider,
            "model": r.model,
            "conversation_id": conversation_id,
            "title": title,
            "conversation_persisted": True,
            "server_time": int(time.time()),
            "created_at": saved_record.get("created_at") if saved_record else None,
            "updated_at": saved_record.get("updated_at") if saved_record else None,
            "usage": r.usage,
            "source": r.source,
            "complexity": r.complexity,
            "usage_logged": usage_logged,
        }

    # Development fallback when cloud storage is not configured:
    # create a fresh request-scoped agent instead of sharing global state.
    r = _run_local_chat(body.message, context)
    return {
        "text": r.text,
        "provider": r.provider,
        "model": r.model,
        "conversation_id": None,
        "title": "新对话",
        "conversation_persisted": False,
    }


@app.post("/api/reset")
def reset():
    # Conversation reset is client/session scoped. Durable memory remains intact.
    return {"ok": True}


@app.get("/api/conversations")
def get_conversations(request: Request):
    conversations = conversation_service(_trusted_context(request))
    return {
        "cloud": conversations.enabled,
        "conversations": conversations.list(),
        "server_time": int(time.time()),
    }


@app.get("/api/conversations/{conversation_id}")
def get_conversation(conversation_id: str, request: Request):
    conversations = conversation_service(_trusted_context(request))
    conversation = conversations.get(conversation_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="对话不存在")
    conversation["server_time"] = int(time.time())
    return conversation


@app.delete("/api/conversations/{conversation_id}")
def remove_conversation(conversation_id: str, request: Request):
    conversations = conversation_service(_trusted_context(request))
    if not conversations.delete(conversation_id):
        raise HTTPException(status_code=503, detail="对话暂时无法删除")
    return {"ok": True, "server_time": int(time.time())}


def _generate_ai_brief(user_id: str):
    try:
        provider = None
        provider_config = CONFIG.active_provider
        if provider_config and provider_config.is_configured:
            candidate = create_provider(CONFIG.main_provider, CONFIG)
            if candidate.is_available():
                provider = candidate
        return RadarService(user_id=user_id).generate(provider)
    except Exception as exc:
        raise HTTPException(status_code=502, detail="AI 热点抓取失败：" + type(exc).__name__) from exc


@app.get("/api/ai-radar/today")
def ai_radar_today(request: Request):
    context = _trusted_context(request)
    stored = radar_service(context).today()
    if stored:
        return stored
    return {
        "status": "empty",
        "brief_date": time.strftime("%Y-%m-%d", time.gmtime()),
        "generated": False,
        "items": [],
        "server_time": int(time.time()),
    }


@app.post("/api/ai-radar/refresh")
def ai_radar_refresh(request: Request):
    payload = _generate_ai_brief(_trusted_context(request).user_id)
    payload["server_time"] = int(time.time())
    return payload


@app.get("/api/ai-radar/history")
def ai_radar_history(request: Request):
    return {"briefs": radar_service(_trusted_context(request)).history(limit=14), "server_time": int(time.time())}


@app.get("/api/cron/ai-radar")
def ai_radar_cron(request: Request):
    authorization = request.headers.get("authorization", "")
    secret = os.getenv("CRON_SECRET", "")
    authorized = bool(secret) and hmac.compare_digest(authorization, "Bearer " + secret)
    if not authorized and CONFIG.local_development:
        authorized = True
    if not authorized:
        raise HTTPException(status_code=401, detail="unauthorized")
    return _generate_ai_brief(CONFIG.owner_id)


@app.post("/api/memory/suggestions")
def memory_suggestions(body: ConversationRefIn, request: Request):
    context = _trusted_context(request)
    user_id = context.user_id
    conversations = conversation_service(context)
    conversation = conversations.get(body.conversation_id or "") if conversations.enabled else None
    source = conversation.get("messages", []) if conversation else []
    messages = extractor.messages_for_agent(source)
    if len(messages) < 2:
        return {"status": "empty", "suggestions": []}
    try:
        reviewer = _agent_from_messages([], context)
        decision = reviewer.router.select("Extract durable memory suggestions")
        provider = reviewer.router.get_provider(decision.provider_name)
        if not provider.is_available():
            raise HTTPException(status_code=503, detail="模型当前不可用")
        result = provider.complete(
            [LLMMessage.system("You extract durable memories. Return JSON only."), LLMMessage.user(extractor.build_prompt(messages))],
            temperature=0.1,
            max_tokens=800,
            reasoning=None,
        )
        suggestions = extractor.parse(result.text or "")
        return {"status": "ready" if suggestions else "empty", "suggestions": suggestions}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail="记忆提取失败：" + type(exc).__name__) from exc


@app.get("/api/automations")
def get_automations():
    return {"automations": list_automations(), "server_time": int(time.time())}


@app.get("/api/memory")
def get_memories(request: Request):
    memory = memory_service(_trusted_context(request))
    return {"cloud": memory.cloud_enabled, "memories": memory.list()}


@app.post("/api/memory")
def add_memory(body: MemoryIn, request: Request):
    memory = memory_service(_trusted_context(request))
    text_value = brain.scrub_secrets(body.text).strip()
    if not text_value:
        raise HTTPException(status_code=400, detail="记忆内容不能为空")
    if not memory.add(text_value, source="manual"):
        raise HTTPException(status_code=503, detail="长期记忆暂时无法保存")
    return {"ok": True}


@app.put("/api/memory/{memory_id}")
def edit_memory(memory_id: str, body: MemoryEditIn, request: Request):
    memory = memory_service(_trusted_context(request))
    text_value = brain.scrub_secrets(body.text).strip()
    if not text_value:
        raise HTTPException(status_code=400, detail="记忆内容不能为空")
    memories = memory.list()
    for item in memories:
        if str(item.get("id")) == str(memory_id):
            item["text"] = text_value
            item["source"] = item.get("source") or "manual"
            if not memory.replace(memories):
                raise HTTPException(status_code=503, detail="长期记忆暂时无法保存")
            return {"ok": True}
    raise HTTPException(status_code=404, detail="记忆不存在")


@app.delete("/api/memory/{memory_id}")
def remove_memory(memory_id: str, request: Request):
    memory = memory_service(_trusted_context(request))
    if not memory.delete(memory_id):
        raise HTTPException(status_code=503, detail="长期记忆暂时无法保存")
    return {"ok": True}


@app.post("/api/memory/summarize")
def summarize_memories(body: ConversationRefIn, request: Request):
    context = _trusted_context(request)
    user_id = context.user_id
    conversations = conversation_service(context)
    conversation = conversations.get(body.conversation_id or "") if conversations.enabled else None
    source_messages = conversation.get("messages", []) if conversation else (_message_dicts(load_history()) if not conversations.enabled else [])
    messages = [
        LLMMessage(role=item["role"], content=item["content"])
        for item in source_messages[-16:]
        if isinstance(item, dict)
        and item.get("role") in {"user", "assistant"}
        and isinstance(item.get("content"), str)
        and item["content"].strip()
    ]
    if not messages:
        return {"ok": True, "added": 0, "memories": []}

    transcript = "\n".join(
        m.role.upper() + ": " + m.content.strip() for m in messages
    )
    curator_prompt = (
        "Extract only durable, useful memories about Mint from the conversation below. "
        "Keep them concise and factual. Prefer stable preferences, explicitly shared identity details, "
        "ongoing projects, recurring workflow preferences, and long-term goals. "
        "Do not save passwords, API keys, tokens, financial secrets, highly sensitive personal data, "
        "temporary emotions, or one-off details. "
        "Return JSON only: {\"memories\":[\"...\"]}. "
        "Return an empty list when nothing is worth remembering.\n\n"
        + transcript
    )
    try:
        summarizer = _agent_from_messages([], context)
        decision = summarizer.router.select("Summarize durable user memory")
        provider = summarizer.router.get_provider(decision.provider_name)
        if not provider.is_available():
            raise HTTPException(status_code=503, detail="模型当前不可用")
        response = provider.complete(
            [LLMMessage.system("You are a precise memory curator."), LLMMessage.user(curator_prompt)],
            temperature=0.2,
            max_tokens=800,
            reasoning=None,
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail="整理记忆失败：" + type(exc).__name__) from exc

    raw = (response.text or "").strip()
    if "```" in raw:
        raw = raw.replace("```json", "").replace("```", "").strip()
    try:
        data = json.loads(raw)
        candidates = data.get("memories") if isinstance(data, dict) else []
    except Exception:
        candidates = []

    saved = []
    for candidate in candidates[:8] if isinstance(candidates, list) else []:
        value = brain.scrub_secrets(str(candidate)).strip()
        if value and memory_service(context).add(value, source="conversation"):
            saved.append(value)
    return {"ok": True, "added": len(saved), "memories": saved}


@app.get("/api/status")
def status():
    return {
        "status": "ok",
        "name": AGENT_IDENTITY.name,
        "provider": CONFIG.main_provider,
        "providers": available_providers(CONFIG),
        "configured": bool(CONFIG.active_provider and CONFIG.active_provider.is_configured),
        "memory": "supabase" if cloud.enabled() else "local-or-disabled",
        "server_time": int(time.time()),
        "version": "0.2.0",
        "rate_limit": RATE_LIMITER.backend_status,
        "rate_limit_strict": RATE_LIMITER.strict,
    }


@app.get("/api/usage")
def usage(request: Request):
    return {"usage": cloud.usage_summary(user_id=_trusted_context(request).user_id), "server_time": int(time.time())}


@app.get("/api/capabilities")
def capabilities():
    return {
        "providers": available_providers(CONFIG),
        "memory": cloud.enabled(),
        "automations": list_automations(),
        "server_time": int(time.time()),
    }
