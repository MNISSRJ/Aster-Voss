from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from agent import AsterVoss
from llm.base import LLMMessage
from llm.factory import create_provider
from aster import AGENT_IDENTITY, AGENT_TAGLINE, get_memory
from config import load_config
from memory.persistence import long_term_context
from memory import brain, cloud
from memory import extractor
from automations import list_automations
from memory.service import MemoryService
from services.conversation_service import ConversationService
from services.radar_service import RadarService
from pathlib import Path
import json
import time
import os
from uuid import uuid4

CONFIG = load_config()
MEMORY = MemoryService()
CONVERSATIONS = ConversationService()
RADAR = RadarService()

def build_prompt(user_id: str = MEMORY.user_id):
    m = MEMORY.context() if brain.enabled() else get_memory().context_block(reload=True)
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
            "<shared_growth_history>\\n"
            "These are a few curated milestones in Aster and Mint's shared history. "
            "Use them naturally when relevant; never recite the log unless asked.\\n"
            + growth
            + "\\n</shared_growth_history>"
        )
    return "\\n\\n".join(parts)

app = FastAPI(title="Aster Voss")


@app.middleware("http")
async def request_observability(request: Request, call_next):
    started = time.perf_counter()
    request_id = request.headers.get("x-request-id") or uuid4().hex
    try:
        response = await call_next(request)
    except Exception:
        log.error("request_id=%s method=%s path=%s status=500 latency_ms=%.1f", request_id, request.method, request.url.path, (time.perf_counter() - started) * 1000)
        raise
    latency_ms = (time.perf_counter() - started) * 1000
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Server-Time"] = str(int(time.time()))
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


class ConversationRefIn(BaseModel):
    conversation_id: str | None = None


class MemoryIn(BaseModel):
    text: str


class MemoryEditIn(BaseModel):
    text: str


@app.get("/", response_class=HTMLResponse)
def home():
    return HTMLResponse("""<!doctype html>
<html lang="zh-CN">
<head>
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="theme-color" content="#eef3ff">
<title>Aster Voss</title>
<style>
:root{
  --bg:#eef3ff;
  --ink:#253149;
  --muted:#7a879d;
  --line:rgba(91,108,155,.16);
  --glass:rgba(255,255,255,.56);
  --glass-strong:rgba(255,255,255,.72);
  --blue:#5f73ff;
  --violet:#8f6cff;
}
*{box-sizing:border-box}
html,body{margin:0;min-height:100%;background:var(--bg);color:var(--ink)}
body{font-family:-apple-system,BlinkMacSystemFont,"SF Pro Text","SF Pro Display","Segoe UI",sans-serif;overflow:hidden}
button,input,textarea{font:inherit}
button{cursor:pointer}
body::before,body::after{
  content:"";position:fixed;width:52vw;height:52vw;min-width:340px;min-height:340px;
  border-radius:50%;pointer-events:none;z-index:0;filter:blur(8px);opacity:.72
}
body::before{
  left:-14vw;top:-8vh;
  background:radial-gradient(circle at 55% 55%,rgba(78,203,255,.52),rgba(101,112,255,.30) 45%,transparent 73%);
  animation:aurora1 16s ease-in-out infinite
}
body::after{
  right:-14vw;bottom:-14vh;
  background:radial-gradient(circle at 45% 45%,rgba(255,156,220,.54),rgba(169,117,255,.32) 44%,transparent 73%);
  animation:aurora2 18s ease-in-out infinite
}
@keyframes aurora1{0%,100%{transform:translate3d(0,0,0) scale(1)}50%{transform:translate3d(8vw,3vh,0) scale(1.08)}}
@keyframes aurora2{0%,100%{transform:translate3d(0,0,0) scale(1)}50%{transform:translate3d(-6vw,-4vh,0) scale(1.06)}}

.app{position:relative;z-index:1;height:100vh;display:flex}
.sidebar{
  width:248px;flex:0 0 248px;height:100vh;padding:14px 11px;display:flex;flex-direction:column;
  background:rgba(247,249,255,.58);border-right:1px solid rgba(255,255,255,.72);
  backdrop-filter:blur(24px);-webkit-backdrop-filter:blur(24px)
}
.side-brand{display:flex;align-items:center;gap:10px;padding:6px 8px 16px}
.side-logo,.top-logo{
  display:grid;place-items:center;border-radius:12px;
  background:linear-gradient(145deg,rgba(255,255,255,.88),rgba(226,233,255,.66));
  border:1px solid rgba(255,255,255,.9);box-shadow:0 8px 24px rgba(91,111,200,.12)
}
.side-logo{width:34px;height:34px;font-size:17px}.top-logo{width:39px;height:39px;font-size:19px}
.side-name{font-size:14px;font-weight:700}.side-sub{font-size:11px;color:var(--muted);margin-top:2px}
.side-new{
  width:100%;border:1px solid rgba(103,121,176,.20);background:rgba(255,255,255,.46);color:#34405a;
  border-radius:11px;padding:10px 11px;text-align:left;font-size:13px;font-weight:650;
  backdrop-filter:blur(12px);-webkit-backdrop-filter:blur(12px);transition:.15s ease
}
.side-new:hover{background:rgba(255,255,255,.66);transform:translateY(-1px)}
.side-nav{display:flex;flex-direction:column;gap:3px;margin-top:14px}
.conversation-list{margin-top:10px;display:flex;flex-direction:column;gap:2px;overflow:auto;max-height:calc(100vh - 275px);scrollbar-width:none}
.conversation-list::-webkit-scrollbar{display:none}
.conversation-empty{padding:10px;color:#95a0b3;font-size:11px;line-height:1.5}
.conversation-item{width:100%;border:0;background:transparent;color:#67748b;border-radius:9px;padding:8px 7px;display:flex;align-items:center;gap:7px;text-align:left;font-size:12px;transition:.14s ease}
.conversation-item:hover,.conversation-item.active{background:rgba(255,255,255,.55);color:#2c3850}
.conversation-title{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;flex:1}
.conversation-meta{display:flex;flex-direction:column;gap:2px;min-width:0;flex:1}.conversation-group{font-size:9px;letter-spacing:.08em;text-transform:uppercase;color:#9aa6b9;padding:10px 7px 4px}
.conversation-item time{font-size:9px;color:#8f9ab0}

.conversation-time{font-size:9px;color:#8f9ab0;line-height:1.2}
.radar-status{font-size:10px;color:#8290a8;margin-top:3px}

.conversation-delete{flex:0 0 22px;width:22px;height:22px;border:0;background:transparent;color:#9aa4b5;border-radius:7px;opacity:0;font-size:14px;line-height:1}
.conversation-item:hover .conversation-delete,.conversation-item.active .conversation-delete{opacity:1}
.conversation-delete:hover{background:rgba(130,145,180,.16);color:#4f5c73}
.radar-view{height:calc(100vh - 64px);overflow-y:auto;padding:34px min(7vw,92px) 86px;scrollbar-width:none}
.radar-view::-webkit-scrollbar{display:none}
.radar-head{display:flex;align-items:flex-end;justify-content:space-between;gap:22px;margin-bottom:18px}
.radar-kicker{font-size:10px;font-weight:800;letter-spacing:.16em;color:#8290aa;text-transform:uppercase}
.radar-title{font-size:31px;letter-spacing:-.8px;margin-top:5px;color:#293650}
.radar-date{font-size:12px;color:#7b879d;margin-top:5px}
.radar-refresh{border:1px solid rgba(103,121,176,.20);background:rgba(255,255,255,.60);color:#44516a;border-radius:12px;padding:9px 13px;font-size:12px;box-shadow:0 5px 18px rgba(88,103,157,.06)}
.radar-refresh:hover{background:rgba(255,255,255,.80);transform:translateY(-1px)}
.radar-intro{padding:14px 16px;border:1px solid rgba(255,255,255,.82);background:rgba(255,255,255,.48);border-radius:16px;color:#596780;line-height:1.65;box-shadow:0 8px 24px rgba(88,103,157,.06);backdrop-filter:blur(18px);-webkit-backdrop-filter:blur(18px);margin-bottom:12px}
.radar-list{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}
.radar-card{min-height:220px;padding:16px;border:1px solid rgba(255,255,255,.82);background:rgba(255,255,255,.50);border-radius:17px;box-shadow:0 9px 28px rgba(88,103,157,.07);backdrop-filter:blur(18px);-webkit-backdrop-filter:blur(18px);transition:transform .16s ease,box-shadow .16s ease;display:flex;flex-direction:column}
.radar-card:hover{transform:translateY(-2px);box-shadow:0 14px 34px rgba(88,103,157,.11)}
.radar-top{display:flex;align-items:center;justify-content:space-between;gap:8px}
.radar-company{font-size:10px;color:#7f8ba0;text-transform:uppercase;letter-spacing:.07em;font-weight:700}
.radar-score{font-size:10px;color:#637190;background:rgba(225,231,249,.68);padding:4px 7px;border-radius:999px}
.radar-headline{font-size:16px;line-height:1.45;font-weight:720;color:#293650;margin-top:8px}
.radar-summary{font-size:12.5px;line-height:1.65;color:#5f6d85;margin-top:7px}
.radar-why{font-size:11.5px;line-height:1.55;color:#7b879c;margin-top:9px;padding-top:9px;border-top:1px solid rgba(128,142,184,.14)}
.radar-tags{display:flex;flex-wrap:wrap;gap:5px;margin-top:10px}
.radar-tag{font-size:10px;color:#657390;background:rgba(238,242,252,.72);padding:4px 7px;border-radius:7px}
.radar-source{display:block;margin-top:auto;padding-top:12px;font-size:10px;color:#687895;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;text-decoration:none}
.radar-source:hover{text-decoration:underline}
.radar-empty{padding:32px 16px;text-align:center;border:1px dashed rgba(115,132,176,.22);border-radius:16px;color:#818da2;font-size:12px;grid-column:1/-1}
.side-item.radar-active{background:rgba(255,255,255,.58);color:#2d3850}
#radar[hidden]{display:none!important}
@media(max-width:899px){.radar-view{padding:22px 14px 72px}.radar-head{align-items:flex-start}.radar-title{font-size:25px}.radar-list{grid-template-columns:1fr}.radar-refresh{padding:8px 10px}}
.side-item{
  width:100%;border:0;background:transparent;color:#6f7d94;border-radius:10px;padding:9px 10px;
  text-align:left;font-size:13px;display:flex;align-items:center;gap:9px;transition:.15s ease
}
.side-item:hover,.side-item.active{background:rgba(255,255,255,.58);color:#2d3850}
.side-spacer{flex:1}.side-foot{border-top:1px solid rgba(128,142,184,.17);padding-top:8px}
.side-foot button{
  width:100%;border:0;background:transparent;color:#6f7d94;border-radius:10px;padding:9px 10px;text-align:left;font-size:13px
}
.side-foot button:hover{background:rgba(255,255,255,.54);color:#2d3850}

.main{flex:1;min-width:0;position:relative}
.topbar{
  height:64px;display:flex;align-items:center;justify-content:space-between;padding:0 22px;
  border-bottom:1px solid rgba(128,142,184,.14);backdrop-filter:blur(18px);-webkit-backdrop-filter:blur(18px)
}
.brand{display:flex;align-items:center;gap:10px}.brand-name{font-size:16px;font-weight:700}.brand-sub{font-size:11px;color:var(--muted);margin-top:2px}
.top-actions{display:flex;align-items:center;gap:7px}.new{
  border:1px solid rgba(103,121,176,.18);background:rgba(255,255,255,.48);color:#34405a;
  border-radius:11px;padding:9px 12px;font-size:13px;font-weight:650
}
.new:hover{background:rgba(255,255,255,.68)}.mobile-menu{display:none;border:0;background:transparent;color:#56657f;font-size:22px}

.chat{
  height:calc(100vh - 64px);overflow-y:auto;scrollbar-width:none;
  padding:28px min(7vw,90px) 142px;display:flex;flex-direction:column;gap:14px
}
.chat::-webkit-scrollbar{display:none}
.msg{max-width:78%;font-size:15.5px;line-height:1.7;word-break:break-word;white-space:pre-wrap;animation:msgIn .18s ease}
@keyframes msgIn{from{opacity:0;transform:translateY(4px)}to{opacity:1;transform:translateY(0)}}
.u{
  align-self:flex-end;color:white;padding:10px 14px;border-radius:19px 19px 6px 19px;
  background:linear-gradient(135deg,#667aff,#8b6cff 58%,#54c6ff);box-shadow:0 8px 25px rgba(100,119,255,.18)
}
.a{
  align-self:flex-start;padding:12px 15px;border-radius:18px;color:#2f3b54;
  background:rgba(255,255,255,.48);border:1px solid rgba(255,255,255,.78);
  box-shadow:0 9px 28px rgba(88,103,157,.08);backdrop-filter:blur(18px);-webkit-backdrop-filter:blur(18px)
}
.welcome{
  max-width:min(650px,90%);color:#60708b;background:rgba(255,255,255,.52)
}
.thinking{
  display:flex!important;align-items:center;gap:12px;width:max-content;max-width:none;
  position:relative;overflow:hidden
}
.thinking::after{
  content:"";position:absolute;inset:-70% -30%;
  background:linear-gradient(110deg,transparent 38%,rgba(255,255,255,.72) 50%,transparent 62%);
  transform:translateX(-80%);animation:sweep 2.2s ease-in-out infinite
}
@keyframes sweep{0%,25%{transform:translateX(-80%)}75%,100%{transform:translateX(80%)}}
.thinking-name{font-size:13px;font-weight:700;color:#56637c;position:relative;z-index:1}
.liquid{display:flex;gap:4px;align-items:flex-end;height:22px;position:relative;z-index:1}
.drop{
  width:8px;height:11px;border-radius:65% 65% 48% 48%;
  background:linear-gradient(145deg,#63d9ff,#7880ff 54%,#b06cff);
  box-shadow:0 0 14px rgba(108,131,255,.32);
  animation:dropWave 1.12s ease-in-out infinite
}
.drop:nth-child(2){animation-delay:.12s}.drop:nth-child(3){animation-delay:.24s}.drop:nth-child(4){animation-delay:.36s}.drop:nth-child(5){animation-delay:.48s}
@keyframes dropWave{
  0%,100%{transform:translateY(1px) scale(.92,.92);opacity:.68}
  34%{transform:translateY(-8px) scale(1.02,1.18);opacity:1}
  64%{transform:translateY(-2px) scale(.96,.98);opacity:.86}
}

.composer-wrap{
  position:fixed;left:248px;right:0;bottom:0;z-index:8;padding:10px 20px 18px;
  background:linear-gradient(transparent,rgba(238,243,255,.70) 32%,rgba(238,243,255,.94))
}
.composer{
  width:min(860px,92%);margin:auto;display:flex;align-items:flex-end;gap:8px;
  padding:8px;border-radius:19px;background:rgba(255,255,255,.58);
  border:1px solid rgba(255,255,255,.84);box-shadow:0 14px 45px rgba(87,104,163,.14);
  backdrop-filter:blur(22px);-webkit-backdrop-filter:blur(22px)
}
.composer textarea{
  flex:1;min-height:44px;max-height:140px;resize:none;overflow-y:auto;scrollbar-width:none;
  border:0;outline:0;background:transparent;color:#263149;padding:10px 10px;line-height:1.5
}
.composer textarea::-webkit-scrollbar{display:none}.composer textarea::placeholder{color:#8b96a9}
.send{
  flex:0 0 44px;width:44px;height:44px;border:0;border-radius:14px;
  background:linear-gradient(135deg,#667aff,#8d69ff 56%,#50c6ff);color:white;font-size:22px;font-weight:600;
  box-shadow:0 8px 20px rgba(100,116,255,.20);transition:.15s ease
}
.send:hover{transform:translateY(-1px)}.send:disabled{opacity:.45;transform:none}

.overlay{position:fixed;inset:0;background:rgba(83,98,145,.18);opacity:0;pointer-events:none;transition:.2s ease;z-index:20}
.overlay.open{opacity:1;pointer-events:auto}
.settings{
  position:fixed;top:0;right:0;width:min(440px,94vw);height:100vh;z-index:21;
  background:rgba(250,252,255,.80);border-left:1px solid rgba(255,255,255,.80);
  box-shadow:-18px 0 70px rgba(70,86,140,.18);backdrop-filter:blur(26px);-webkit-backdrop-filter:blur(26px);
  transform:translateX(100%);transition:transform .22s ease;display:flex;flex-direction:column
}
.settings.open{transform:translateX(0)}
.settings-head{display:flex;align-items:center;justify-content:space-between;padding:18px;border-bottom:1px solid var(--line)}
.settings-title{font-size:18px;font-weight:750}.close{border:0;background:transparent;color:#7c889d;font-size:25px}
.settings-body{padding:20px;overflow-y:auto;scrollbar-width:none}.settings-body::-webkit-scrollbar{display:none}
.section{margin-bottom:28px}.section-title{font-size:13px;font-weight:750;margin-bottom:6px}.section-copy{font-size:12px;line-height:1.65;color:#748199;margin-bottom:12px}
.theme-row{display:flex;gap:4px;background:rgba(224,230,248,.60);border-radius:11px;padding:3px}
.theme-btn{flex:1;border:0;background:transparent;color:#7a879c;border-radius:9px;padding:8px;font-size:12px}.theme-btn.active{background:rgba(255,255,255,.78);color:#34405a;box-shadow:0 1px 5px rgba(70,83,130,.08)}
.memory-compose{display:flex;gap:7px}.memory-compose input{
  flex:1;min-width:0;border:1px solid rgba(115,132,176,.23);background:rgba(255,255,255,.52);color:#2b3851;
  border-radius:11px;padding:10px 11px;outline:0
}
.memory-compose input:focus{border-color:rgba(99,118,205,.48);box-shadow:0 0 0 4px rgba(107,126,230,.10)}
.memory-add{border:0;border-radius:11px;padding:10px 12px;background:linear-gradient(135deg,#667aff,#8c69ff);color:#fff;font-weight:700}
.memory-import{width:100%;margin-top:8px;border:1px solid rgba(115,132,176,.20);border-radius:11px;background:rgba(255,255,255,.34);color:#4a5770;padding:10px 12px;text-align:left;font-size:12px}
.memory-list{display:flex;flex-direction:column;gap:8px;margin-top:13px}
.memory-card{
  border:1px solid rgba(115,132,176,.18);border-radius:13px;background:rgba(255,255,255,.44);padding:11px;
  box-shadow:0 5px 18px rgba(84,102,157,.05)
}
.memory-top{display:flex;justify-content:space-between;gap:8px;align-items:center}.memory-source{font-size:10px;color:#8a95a8;text-transform:uppercase;letter-spacing:.06em}
.memory-actions{display:flex;gap:3px}.memory-action{border:0;background:transparent;color:#79869b;border-radius:7px;padding:4px 5px;font-size:11px}.memory-action:hover{background:rgba(224,230,245,.72);color:#39455e}
.memory-text{margin-top:7px;font-size:12.5px;line-height:1.58;white-space:pre-wrap;word-break:break-word}
.memory-edit{width:100%;min-height:82px;margin-top:7px;resize:vertical;border:1px solid rgba(115,132,176,.22);border-radius:9px;background:rgba(255,255,255,.60);color:#2b3851;padding:9px;outline:0;line-height:1.5}
.memory-save{border:0;background:#283349;color:white;border-radius:8px;padding:7px 10px;font-size:11px;margin-top:7px}.memory-cancel{border:1px solid rgba(115,132,176,.22);background:transparent;color:#657189;border-radius:8px;padding:6px 10px;font-size:11px;margin:7px 0 0 5px}
.memory-empty{border:1px dashed rgba(115,132,176,.22);border-radius:12px;padding:22px 12px;text-align:center;color:#8290a5;font-size:12px;line-height:1.65}

.clean-mode::before,.clean-mode::after{display:none}
.clean-mode{background:#f5f6f8}
.clean-mode .sidebar{background:rgba(255,255,255,.92);border-right-color:#e5e7eb}
.clean-mode .topbar{background:rgba(255,255,255,.72);border-bottom-color:#e6e8ed}
.clean-mode .a,.clean-mode .welcome{background:rgba(255,255,255,.94);border-color:#e6e8ed;box-shadow:0 4px 18px rgba(40,47,61,.05)}
.clean-mode .composer-wrap{background:linear-gradient(transparent,rgba(245,246,248,.72) 32%,rgba(245,246,248,.96))}
.clean-mode .composer{background:#fff;border-color:#e1e4ea;box-shadow:0 8px 28px rgba(40,47,61,.08)}
.clean-mode .send{background:#1f2937;box-shadow:none}
.clean-mode .settings{background:rgba(255,255,255,.97)}
.clean-mode .memory-card{background:#fff;border-color:#e3e6eb}

.toast{position:fixed;left:50%;bottom:88px;transform:translate(-50%,10px);padding:9px 13px;border-radius:11px;background:rgba(38,50,76,.84);color:white;border:1px solid rgba(255,255,255,.26);box-shadow:0 10px 30px rgba(48,62,104,.20);opacity:0;pointer-events:none;transition:.18s ease;z-index:40;font-size:12px}
.toast.show{opacity:1;transform:translate(-50%,0)}
@media(max-width:899px){
  body{overflow:auto}
  .sidebar{position:fixed;left:0;top:0;bottom:0;transform:translateX(-100%);transition:transform .2s ease;z-index:25;width:276px}
  .sidebar.open{transform:translateX(0)}
  .topbar{padding:0 14px}.mobile-menu{display:block}.brand{display:none}
  .main{width:100%}.chat{padding:22px 14px 136px}.msg{max-width:89%}
  .composer-wrap{left:0;right:0;padding:9px 10px calc(10px + env(safe-area-inset-bottom))}
  .composer{width:100%}.settings{width:94vw}
}
</style>
</head>
<body>
<div class="app">
  <aside class="sidebar" id="sidebar">
    <div class="side-brand">
      <div class="side-logo">✦</div>
      <div><div class="side-name">Aster Voss</div><div class="side-sub">Personal AI Agent</div></div>
    </div>
    <button class="side-new" id="new-chat-side">＋ 新对话</button>
    <nav class="side-nav">
      <button class="side-item active" id="nav-chat">⌂ <span>对话</span></button>
      <button class="side-item" id="nav-radar">✦ <span>AI Radar</span></button>
    </nav>
    <div class="conversation-list" id="conversation-list">
      <div class="conversation-empty">还没有过去的对话</div>
    </div>
    <div class="side-spacer"></div>
    <div class="side-foot"><button id="settings-side">⚙ 设置</button></div>
  </aside>

  <section class="main">
    <header class="topbar">
      <div class="top-actions">
        <button class="mobile-menu" id="mobile-menu" aria-label="打开菜单">☰</button>
        <div class="brand"><div class="top-logo">✦</div><div><div class="brand-name">Aster Voss</div><div class="brand-sub">Personal AI Agent · cloud memory</div></div></div>
      </div>
      <button class="new" id="new-chat-top">＋ 新对话</button>
    </header>

    <div id="chat" class="chat">
      <div class="msg a welcome">你好，我是 Aster Voss。<br>现在我有了云端长期记忆。你可以直接和我聊天，也可以说“记住：……”让我记住一件事。</div>
    </div>

    <section id="radar" class="radar-view" hidden>
      <div class="radar-head">
        <div>
          <div class="radar-kicker">ASTER INTELLIGENCE</div>
          <div class="radar-title">今日 AI 简报</div>
          <div class="radar-date" id="radar-date">正在加载…</div>
        </div>
        <button class="radar-refresh" id="radar-refresh" type="button">↻ 刷新</button>
      </div>
      <div class="radar-intro" id="radar-intro">Aster 正在整理多源 AI 热点。</div>
      <div class="radar-list" id="radar-list"><div class="radar-empty">正在读取今日简报…</div></div>
    </section>

    <div class="composer-wrap">
      <form class="composer" id="chat-form">
        <textarea id="input" rows="1" placeholder="和 Aster 说点什么…"></textarea>
        <button class="send" id="send" type="submit" aria-label="发送">↑</button>
      </form>
    </div>
  </section>
</div>

<div class="overlay" id="overlay"></div>
<aside class="settings" id="settings" aria-label="设置">
  <div class="settings-head"><div class="settings-title">设置</div><button class="close" id="settings-close" type="button" aria-label="关闭">×</button></div>
  <div class="settings-body">
    <section class="section">
      <div class="section-title">外观</div>
      <div class="section-copy">Aster 默认使用彩色玻璃空间，也可以切换到更纯净的浅色界面。</div>
      <div class="theme-row">
        <button class="theme-btn active" data-theme-choice="glass" type="button">彩色玻璃</button>
        <button class="theme-btn" data-theme-choice="clean" type="button">纯净浅色</button>
      </div>
    </section>
    <section class="section">
      <div class="section-title">🧠 长期记忆</div>
      <div class="section-copy">这里的内容会被 Aster 在后续对话中使用。你可以直接管理，也可以从最近对话里整理。</div>
      <div class="memory-compose">
        <input id="memory-input" placeholder="添加一条长期记忆…" autocomplete="off">
        <button class="memory-add" id="memory-add" type="button">添加</button>
      </div>
      <button class="memory-import" id="memory-summary" type="button">✨ 从最近对话整理</button>
      <div class="memory-list" id="memory-list"><div class="memory-empty">正在读取…</div></div>
    </section>
  </div>
</aside>
<div class="toast" id="toast"></div>

<script>
const chat=document.querySelector("#chat");
const input=document.querySelector("#input");
const form=document.querySelector("#chat-form");
const sendButton=document.querySelector("#send");
const sidebar=document.querySelector("#sidebar");
const overlay=document.querySelector("#overlay");
const settings=document.querySelector("#settings");
const toast=document.querySelector("#toast");
const memoryList=document.querySelector("#memory-list");
const conversationList=document.querySelector("#conversation-list");
let currentConversationId=localStorage.getItem("aster-current-conversation")||null;
const memoryInput=document.querySelector("#memory-input");
const radarView=document.querySelector("#radar");
const radarList=document.querySelector("#radar-list");
const radarIntro=document.querySelector("#radar-intro");
const radarDate=document.querySelector("#radar-date");

function scrollChat(){
  requestAnimationFrame(()=>{chat.scrollTo({top:chat.scrollHeight,behavior:"smooth"});});
}
function addMessage(text,kind){
  const el=document.createElement("div");
  el.className="msg "+kind;
  el.textContent=text;
  chat.appendChild(el);
  scrollChat();
  return el;
}
function addThinking(){
  const el=document.createElement("div");
  el.className="msg a thinking";
  el.innerHTML='<span class="thinking-name">Aster</span><span class="liquid"><i class="drop"></i><i class="drop"></i><i class="drop"></i><i class="drop"></i><i class="drop"></i></span>';
  chat.appendChild(el);
  scrollChat();
  return el;
}
function showToast(message){
  toast.textContent=message;
  toast.classList.add("show");
  clearTimeout(window._asterToast);
  window._asterToast=setTimeout(()=>toast.classList.remove("show"),1800);
}
async function sendMessage(){
  const value=input.value.trim();
  if(!value || sendButton.disabled)return;
  addMessage(value,"u");
  input.value="";
  input.style.height="44px";
  sendButton.disabled=true;
  const thinking=addThinking();
  try{
    const response=await fetch("/api/chat",{
      method:"POST",
      headers:{"Content-Type":"application/json"},
      body:JSON.stringify({message:value,conversation_id:currentConversationId})
    });
    const data=await response.json().catch(()=>({}));
    if(!response.ok)throw new Error(data.detail||data.error||"请求失败");
    thinking.remove();
    addMessage(data.text||"……","a");
    if(data.conversation_id){
      currentConversationId=data.conversation_id;
      localStorage.setItem("aster-current-conversation",currentConversationId);
    }
    if(data.conversation_persisted===false)showToast("回复成功，但历史记录暂时未保存");
    await loadConversations(false);
  }catch(error){
    thinking.remove();
    addMessage("刚才没有成功收到回复，请再试一次。","a");
    console.error(error);
  }finally{
    sendButton.disabled=false;
    input.focus();
  }
}
form.addEventListener("submit",event=>{event.preventDefault();sendMessage();});

function setWorkspace(view){
  const showingRadar=view==="radar";
  radarView.hidden=!showingRadar;
  chat.style.display=showingRadar?"none":"flex";
  document.querySelector(".composer-wrap").style.display=showingRadar?"none":"block";
  document.querySelector("#nav-chat").classList.toggle("active",!showingRadar);
  document.querySelector("#nav-radar").classList.toggle("radar-active",showingRadar);
  if(showingRadar)loadRadar();
}
async function loadRadar(){
  radarList.innerHTML='<div class="radar-empty">正在读取今日简报…</div>';
  try{
    const response=await fetch("/api/ai-radar/today",{cache:"no-store"});
    const data=await response.json();
    if(!response.ok)throw new Error(data.detail||"读取失败");
    const statusLabel=data.status==="ready"?"已生成":data.status==="failed"?"生成失败":"未生成";
    radarDate.textContent=(data.brief_date||"").replace(/-/g,".")+" · "+statusLabel;
    if(data.generated_at){
      radarDate.textContent += " · "+new Date(data.generated_at).toLocaleTimeString("zh-CN",{hour:"2-digit",minute:"2-digit"});
    }
    if(!data.items||!data.items.length){
      radarIntro.textContent=data.status==="empty"
        ?"Aster 还没有拿到今天的热点。点击“刷新”立即生成一份。"
        :"当前没有可展示的简报内容。点击“刷新”重试。";
      radarList.innerHTML='<div class="radar-empty">暂无内容</div>';
      return;
    }
    radarIntro.textContent=data.intro_zh||"Aster 已为你整理今天的 AI 热点。";
    radarList.innerHTML="";
    data.items.forEach(renderRadarCard);
  }catch(error){
    radarList.innerHTML='<div class="radar-empty">简报暂时无法读取，请点击刷新。</div>';
    console.error(error);
  }
}
function renderRadarCard(item){
  const card=document.createElement("article");card.className="radar-card";
  const top=document.createElement("div");top.className="radar-top";
  const company=document.createElement("span");company.className="radar-company";company.textContent=item.company||"AI";
  const score=document.createElement("span");score.className="radar-score";score.textContent="Aster 热点 "+(item.hot_score??"-");
  top.append(company,score);
  const headline=document.createElement("div");headline.className="radar-headline";headline.textContent=item.headline_zh||"";
  const summary=document.createElement("div");summary.className="radar-summary";summary.textContent=item.summary_zh||"";
  const why=document.createElement("div");why.className="radar-why";why.textContent=item.why_it_matters_zh?("为什么重要 · "+item.why_it_matters_zh):"";
  const tags=document.createElement("div");tags.className="radar-tags";
  (item.tags||[]).forEach(tag=>{const span=document.createElement("span");span.className="radar-tag";span.textContent=tag;tags.appendChild(span);});
  const link=document.createElement("a");link.className="radar-source";link.textContent=(item.source_list||[]).join(" · ")+"  ↗";link.href=item.url||"#";link.target="_blank";link.rel="noopener noreferrer";
  card.append(top,headline,summary,why,tags,link);radarList.appendChild(card);
}
document.querySelector("#nav-radar").addEventListener("click",()=>{setWorkspace("radar");sidebar.classList.remove("open");});
document.querySelector("#nav-chat").addEventListener("click",()=>{setWorkspace("chat");sidebar.classList.remove("open");});
document.querySelector("#radar-refresh").addEventListener("click",async()=>{
  const btn=document.querySelector("#radar-refresh");btn.disabled=true;btn.textContent="整理中…";
  radarList.innerHTML='<div class="radar-empty">正在抓取并整理最新 AI 热点…</div>';
  try{
    const response=await fetch("/api/ai-radar/refresh",{method:"POST"});
    const data=await response.json().catch(()=>({}));
    if(!response.ok)throw new Error(data.detail||data.error||"刷新失败");
    radarDate.textContent=(data.brief_date||"").replace(/-/g,".")+" · "+(data.status==="ready"?"刚刚更新":"已完成");
    if(data.generated_at)radarDate.textContent+=" · "+new Date(data.generated_at).toLocaleTimeString("zh-CN",{hour:"2-digit",minute:"2-digit"});
    radarIntro.textContent=data.intro_zh||"";
    radarList.innerHTML="";
    (data.items||[]).forEach(renderRadarCard);
    if(data.items&&data.items.length)showToast("AI 简报已更新，"+data.items.length+" 条");
    else showToast("简报生成完成，但暂无可展示内容");
  }catch(error){
    radarList.innerHTML='<div class="radar-empty">简报生成失败。'+(error.message?("<br>"+error.message):"")+'</div>';
    showToast("简报更新失败");
    console.error(error);
  }finally{btn.disabled=false;btn.textContent="↻ 刷新";}
});
function toggleSidebar(){sidebar.classList.toggle("open")}
document.querySelector("#mobile-menu").addEventListener("click",toggleSidebar);

async function resetChat(){
  currentConversationId=null;
  localStorage.removeItem("aster-current-conversation");
  try{await fetch("/api/reset",{method:"POST"});}catch(error){console.error(error)}
  chat.innerHTML='<div class="msg a welcome">新对话开始。<br>你好，我还是 Aster Voss。长期记忆不会因为新对话而消失。</div>';
  setWorkspace("chat");
  await loadConversations(false);
  input.focus();
  showToast("已开启新对话");
  sidebar.classList.remove("open");
}
document.querySelector("#new-chat-side").addEventListener("click",resetChat);
document.querySelector("#new-chat-top").addEventListener("click",resetChat);
document.querySelector("#nav-chat").addEventListener("click",()=>{setWorkspace("chat");sidebar.classList.remove("open");});
document.querySelector("#settings-side").addEventListener("click",event=>{
  event.preventDefault();
  event.stopPropagation();
  openSettings();
});

function openSettings(){
  settings.classList.add("open");
  overlay.classList.add("open");
  settings.setAttribute("aria-hidden","false");
  loadMemories();
  sidebar.classList.remove("open");
}
function closeSettings(){settings.classList.remove("open");overlay.classList.remove("open");settings.setAttribute("aria-hidden","true")}
document.querySelector("#settings-close").addEventListener("click",closeSettings);
overlay.addEventListener("click",closeSettings);
window.addEventListener("keydown",event=>{if(event.key==="Escape")closeSettings();});

function applyTheme(theme){
  document.body.classList.toggle("clean-mode",theme==="clean");
  document.querySelectorAll(".theme-btn").forEach(btn=>btn.classList.toggle("active",btn.dataset.themeChoice===theme));
  localStorage.setItem("aster-ui-theme",theme);
}
document.querySelectorAll(".theme-btn").forEach(btn=>btn.addEventListener("click",()=>applyTheme(btn.dataset.themeChoice)));
applyTheme(localStorage.getItem("aster-ui-theme")||"glass");


function formatConversationDate(value){
  if(!value)return "";
  try{
    const date=new Date(value);
    return date.toLocaleDateString("zh-CN",{month:"2-digit",day:"2-digit"});
  }catch(error){return ""}
}
function formatConversationTime(value){
  if(!value)return "";
  const d=new Date(value);
  if(Number.isNaN(d.getTime()))return "";
  const now=new Date();
  const sameDay=d.getFullYear()===now.getFullYear()&&d.getMonth()===now.getMonth()&&d.getDate()===now.getDate();
  if(sameDay)return d.toLocaleTimeString("zh-CN",{hour:"2-digit",minute:"2-digit"});
  const yesterday=new Date(now);yesterday.setDate(now.getDate()-1);
  const isYesterday=d.getFullYear()===yesterday.getFullYear()&&d.getMonth()===yesterday.getMonth()&&d.getDate()===yesterday.getDate();
  if(isYesterday)return "昨天 "+d.toLocaleTimeString("zh-CN",{hour:"2-digit",minute:"2-digit"});
  return d.toLocaleDateString("zh-CN",{month:"2-digit",day:"2-digit"});
}
function conversationGroup(item){
  if(!item.created_at)return "其他";
  const d=new Date(item.created_at), now=new Date();
  const startToday=new Date(now.getFullYear(),now.getMonth(),now.getDate());
  const yesterday=new Date(startToday);yesterday.setDate(yesterday.getDate()-1);
  if(d>=startToday)return "今天";
  if(d>=yesterday)return "昨天";
  return d.toLocaleDateString("zh-CN",{month:"long",day:"numeric"});
}
function renderConversations(items){
  conversationList.innerHTML="";
  if(!items.length){
    conversationList.innerHTML='<div class="conversation-empty">还没有过去的对话</div>';
    return;
  }
  let group="";
  items.forEach(item=>{
    const nextGroup=conversationGroup(item);
    if(nextGroup!==group){
      const heading=document.createElement("div");heading.className="conversation-group";heading.textContent=nextGroup;
      conversationList.appendChild(heading);group=nextGroup;
    }
    const row=document.createElement("div");
    row.className="conversation-item"+(item.id===currentConversationId?" active":"");
    const meta=document.createElement("div");meta.className="conversation-meta";
    const title=document.createElement("span");title.className="conversation-title";
    title.title=item.title||"新对话";title.textContent=item.title||"新对话";
    const time=document.createElement("time");time.className="conversation-time";
    const startTime=item.created_at?formatConversationTime(item.created_at):"";
    const updated=item.updated_at?formatConversationTime(item.updated_at):"";
    time.title=item.created_at?new Date(item.created_at).toLocaleString("zh-CN"):"";
    time.textContent=startTime?("开始 "+startTime+(updated&&updated!==startTime?(" · "+updated):"")):"";
    meta.append(title,time);
    const del=document.createElement("button");del.type="button";del.className="conversation-delete";
    del.setAttribute("aria-label","删除对话");del.textContent="×";
    row.append(meta,del);
    row.addEventListener("click",event=>{if(event.target!==del)openConversation(item.id);});
    del.addEventListener("click",async event=>{event.stopPropagation();await deleteConversation(item.id);});
    conversationList.appendChild(row);
  });
}
async function loadConversations(autoOpen=true){
  try{
    const response=await fetch("/api/conversations",{cache:"no-store"});
    const data=await response.json();
    if(!response.ok)throw new Error(data.detail||"读取对话失败");
    const items=Array.isArray(data.conversations)?data.conversations:[];
    renderConversations(items);
    if(!autoOpen)return;
    if(currentConversationId && items.some(item=>item.id===currentConversationId)){
      await openConversation(currentConversationId,false);
    }else if(items.length){
      await openConversation(items[0].id,false);
    }else{
      currentConversationId=null;
      localStorage.removeItem("aster-current-conversation");
    }
  }catch(error){
    conversationList.innerHTML='<div class="conversation-empty">历史对话暂时无法读取</div>';
    console.error(error);
  }
}
async function openConversation(id,closeSidebar=true){
  try{
    const response=await fetch("/api/conversations/"+encodeURIComponent(id),{cache:"no-store"});
    const data=await response.json();
    if(!response.ok)throw new Error(data.detail||"读取对话失败");
    currentConversationId=data.id;
    localStorage.setItem("aster-current-conversation",currentConversationId);
    chat.innerHTML="";
    const messages=Array.isArray(data.messages)?data.messages:[];
    if(!messages.length){
      chat.innerHTML='<div class="msg a welcome">这个对话还没有消息。</div>';
    }else{
      messages.forEach(message=>{
        if(message.role==="user"||message.role==="assistant"){
          addMessage(message.content||"",message.role==="user"?"u":"a");
        }
      });
    }
    await loadConversations(false);
    if(closeSidebar)sidebar.classList.remove("open");
    input.focus();
    scrollChat();
  }catch(error){
    showToast("打开对话失败");
    console.error(error);
  }
}
async function deleteConversation(id){
  if(!window.confirm("删除这段对话？删除后无法恢复。"))return;
  try{
    const response=await fetch("/api/conversations/"+encodeURIComponent(id),{method:"DELETE"});
    const data=await response.json().catch(()=>({}));
    if(!response.ok)throw new Error(data.detail||"删除失败");
    if(currentConversationId===id){
      currentConversationId=null;
      localStorage.removeItem("aster-current-conversation");
      chat.innerHTML='<div class="msg a welcome">新对话开始。<br>你可以继续和 Aster 聊天。</div>';
    }
    await loadConversations(false);
    showToast("对话已删除");
  }catch(error){
    showToast("删除对话失败");
    console.error(error);
  }
}

async function loadMemories(){
  memoryList.innerHTML='<div class="memory-empty">正在读取…</div>';
  try{
    const response=await fetch("/api/memory",{cache:"no-store"});
    const data=await response.json();
    if(!response.ok)throw new Error(data.detail||"读取失败");
    if(!Array.isArray(data.memories)||!data.memories.length){
      memoryList.innerHTML='<div class="memory-empty">还没有长期记忆。<br>可以手动添加，或者从最近对话整理。</div>';
      return;
    }
    memoryList.innerHTML="";
    data.memories.forEach(renderMemory);
  }catch(error){
    memoryList.innerHTML='<div class="memory-empty">长期记忆暂时无法读取，请稍后再试。</div>';
    console.error(error);
  }
}
function renderMemory(item){
  const card=document.createElement("div");
  card.className="memory-card";
  const top=document.createElement("div");top.className="memory-top";
  const source=document.createElement("span");source.className="memory-source";source.textContent=item.source||"manual";
  const actions=document.createElement("div");actions.className="memory-actions";
  const edit=document.createElement("button");edit.type="button";edit.className="memory-action";edit.textContent="编辑";
  const remove=document.createElement("button");remove.type="button";remove.className="memory-action";remove.textContent="删除";
  actions.append(edit,remove);top.append(source,actions);
  const text=document.createElement("div");text.className="memory-text";text.textContent=item.text||"";
  card.append(top,text);memoryList.appendChild(card);
  edit.addEventListener("click",()=>editMemory(item,card));
  remove.addEventListener("click",()=>deleteMemory(item.id));
}
async function addMemory(){
  const text=memoryInput.value.trim();
  if(!text)return;
  const button=document.querySelector("#memory-add");button.disabled=true;
  try{
    const response=await fetch("/api/memory",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({text})});
    const data=await response.json().catch(()=>({}));
    if(!response.ok)throw new Error(data.detail||"添加失败");
    memoryInput.value="";
    showToast("已加入长期记忆");
    await loadMemories();
  }catch(error){showToast("添加失败");console.error(error)}
  finally{button.disabled=false;memoryInput.focus();}
}
document.querySelector("#memory-add").addEventListener("click",addMemory);
memoryInput.addEventListener("keydown",event=>{if(event.key==="Enter"){event.preventDefault();addMemory();}});

function editMemory(item,card){
  const current=card.querySelector(".memory-text");
  card.innerHTML="";
  const area=document.createElement("textarea");area.className="memory-edit";area.value=item.text||"";
  const save=document.createElement("button");save.type="button";save.className="memory-save";save.textContent="保存";
  const cancel=document.createElement("button");cancel.type="button";cancel.className="memory-cancel";cancel.textContent="取消";
  card.append(area,save,cancel);area.focus();
  save.addEventListener("click",async()=>{
    const text=area.value.trim();if(!text)return;
    save.disabled=true;
    try{
      const response=await fetch("/api/memory/"+encodeURIComponent(item.id),{method:"PUT",headers:{"Content-Type":"application/json"},body:JSON.stringify({text})});
      const data=await response.json().catch(()=>({}));
      if(!response.ok)throw new Error(data.detail||"保存失败");
      showToast("已更新");await loadMemories();
    }catch(error){showToast("更新失败");console.error(error)}
    finally{save.disabled=false;}
  });
  cancel.addEventListener("click",loadMemories);
}
async function deleteMemory(id){
  if(!window.confirm("删除这条长期记忆？"))return;
  try{
    const response=await fetch("/api/memory/"+encodeURIComponent(id),{method:"DELETE"});
    const data=await response.json().catch(()=>({}));
    if(!response.ok)throw new Error(data.detail||"删除失败");
    showToast("已删除");await loadMemories();
  }catch(error){showToast("删除失败");console.error(error)}
}

async function summarizeMemories(){
  const button=document.querySelector("#memory-summary");button.disabled=true;button.textContent="正在整理…";
  try{
    if(!currentConversationId){showToast("先聊几句，再整理这段对话");button.disabled=false;button.textContent="✨ 从最近对话整理";return;}\n    const response=await fetch("/api/memory/summarize",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({conversation_id:currentConversationId})});
    const data=await response.json().catch(()=>({}));
    if(!response.ok)throw new Error(data.detail||data.error||"整理失败");
    showToast(data.added?("已整理 "+data.added+" 条记忆"):"没有发现新的长期记忆");
    await loadMemories();
  }catch(error){showToast("整理失败");console.error(error)}
  finally{button.disabled=false;button.textContent="✨ 从最近对话整理";}
}
document.querySelector("#memory-summary").addEventListener("click",summarizeMemories);

input.addEventListener("input",()=>{
  input.style.height="auto";
  input.style.height=Math.min(input.scrollHeight,140)+"px";
});
input.addEventListener("keydown",event=>{
  if(event.key==="Enter" && !event.shiftKey){
    event.preventDefault();
    sendMessage();
  }
});
loadConversations(true);
loadRadar();

</script>
</body>
</html>""")



@app.post("/api/chat")
def chat(body: ChatIn):
    if cloud.enabled():
        conversation_id = (body.conversation_id or "").strip() or str(uuid4())
        existing = CONVERSATIONS.get(conversation_id)
        history = existing.get("messages", []) if existing else []
        title = existing.get("title", "新对话") if existing else _conversation_title(body.message)
        created_at = existing.get("created_at") if existing else None

        request_agent = _agent_from_messages(history)
        r = request_agent.run(body.message)

        persisted = CONVERSATIONS.save(
            conversation_id,
            title,
            _message_dicts(request_agent.messages),
            created_at=created_at,
        )
        saved_record = CONVERSATIONS.get(conversation_id) if persisted else None
        return {
            "ok": True,
            "text": r.text,
            "provider": r.provider,
            "model": r.model,
            "conversation_id": conversation_id if persisted else None,
            "title": title,
            "conversation_persisted": bool(persisted),
            "server_time": int(time.time()),
            "created_at": saved_record.get("created_at") if saved_record else None,
            "updated_at": saved_record.get("updated_at") if saved_record else None,
            "usage": r.usage,
            "source": r.source,
            "complexity": r.complexity,
        }

    # Development fallback when cloud storage is not configured:
    # create a fresh request-scoped agent instead of sharing global state.
    request_agent = _agent_from_messages(
        [
            {"role": m.role, "content": m.content}
            for m in load_history()
            if m.role in {"user", "assistant"} and isinstance(m.content, str)
        ]
    )
    r = request_agent.run(body.message)
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
def get_conversations():
    return {
        "cloud": CONVERSATIONS.enabled,
        "conversations": CONVERSATIONS.list(),
        "server_time": int(time.time()),
    }


@app.get("/api/conversations/{conversation_id}")
def get_conversation(conversation_id: str):
    conversation = CONVERSATIONS.get(conversation_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="对话不存在")
    conversation["server_time"] = int(time.time())
    return conversation


@app.delete("/api/conversations/{conversation_id}")
def remove_conversation(conversation_id: str):
    if not CONVERSATIONS.delete(conversation_id):
        raise HTTPException(status_code=503, detail="对话暂时无法删除")
    return {"ok": True, "server_time": int(time.time())}


def _generate_ai_brief():
    try:
        provider = None
        provider_config = CONFIG.active_provider
        if provider_config and provider_config.is_configured:
            candidate = create_provider(CONFIG.main_provider, CONFIG)
            if candidate.is_available():
                provider = candidate
        return RADAR.generate(provider)
    except Exception as exc:
        raise HTTPException(status_code=502, detail="AI 热点抓取失败：" + type(exc).__name__) from exc


@app.get("/api/ai-radar/today")
def ai_radar_today():
    stored = RADAR.today()
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
def ai_radar_refresh():
    payload = _generate_ai_brief()
    payload["server_time"] = int(time.time())
    return payload


@app.get("/api/ai-radar/history")
def ai_radar_history():
    return {"briefs": cloud.list_ai_briefs(limit=14) if cloud.enabled() else []}


@app.get("/api/cron/ai-radar")
def ai_radar_cron(request: Request):
    user_agent = request.headers.get("user-agent", "")
    authorization = request.headers.get("authorization", "")
    secret = os.getenv("CRON_SECRET", "")
    authorized = (
        "vercel-cron/1.0" in user_agent
        or (secret and authorization == "Bearer " + secret)
    )
    if not authorized:
        raise HTTPException(status_code=401, detail="unauthorized")
    return _generate_ai_brief()


@app.post("/api/memory/suggestions")
def memory_suggestions(body: ConversationRefIn):
    conversation = CONVERSATIONS.get(body.conversation_id or "") if CONVERSATIONS.enabled else None
    source = conversation.get("messages", []) if conversation else []
    messages = extractor.messages_for_agent(source)
    if len(messages) < 2:
        return {"status": "empty", "suggestions": []}
    try:
        reviewer = _agent_from_messages([])
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
def get_memories():
    return {"cloud": MEMORY.cloud_enabled, "memories": MEMORY.list()}


@app.post("/api/memory")
def add_memory(body: MemoryIn):
    text_value = brain.scrub_secrets(body.text).strip()
    if not text_value:
        raise HTTPException(status_code=400, detail="记忆内容不能为空")
    if not MEMORY.add(text_value, source="manual"):
        raise HTTPException(status_code=503, detail="长期记忆暂时无法保存")
    return {"ok": True}


@app.put("/api/memory/{memory_id}")
def edit_memory(memory_id: str, body: MemoryEditIn):
    text_value = brain.scrub_secrets(body.text).strip()
    if not text_value:
        raise HTTPException(status_code=400, detail="记忆内容不能为空")
    memories = MEMORY.list()
    for item in memories:
        if str(item.get("id")) == str(memory_id):
            item["text"] = text_value
            item["source"] = item.get("source") or "manual"
            if not MEMORY.replace(memories):
                raise HTTPException(status_code=503, detail="长期记忆暂时无法保存")
            return {"ok": True}
    raise HTTPException(status_code=404, detail="记忆不存在")


@app.delete("/api/memory/{memory_id}")
def remove_memory(memory_id: str):
    if not MEMORY.delete(memory_id):
        raise HTTPException(status_code=503, detail="长期记忆暂时无法保存")
    return {"ok": True}


@app.post("/api/memory/summarize")
def summarize_memories(body: ConversationRefIn):
    conversation = cloud.load_conversation(body.conversation_id or "") if cloud.enabled() else None
    source_messages = conversation.get("messages", []) if conversation else _message_dicts(load_history())
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
        summarizer = _agent_from_messages([])
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
        if value and brain.add(value, source="conversation"):
            saved.append(value)
    return {"ok": True, "added": len(saved), "memories": saved}


@app.get("/api/status")
def status():
    return {
        "name": AGENT_IDENTITY.name,
        "provider": CONFIG.main_provider,
        "configured": bool(CONFIG.active_provider and CONFIG.active_provider.is_configured),
        "server_time": int(time.time()),
    }
