from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from agent import AsterVoss
from llm.base import LLMMessage
from aster import AGENT_IDENTITY, AGENT_TAGLINE, get_memory
from config import load_config
from memory.persistence import long_term_context
from memory import brain
from pathlib import Path
import json

CONFIG = load_config()

def build_prompt(user_id: str = "mint"):
    m = brain.context_block(user_id=user_id) if brain.enabled() else get_memory().context_block(reload=True)
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

agent = AsterVoss(
    CONFIG,
    system_prompt=build_prompt(),
    identity_name=AGENT_IDENTITY.name,
    identity_tagline=AGENT_TAGLINE,
)

app = FastAPI(title="Aster Voss")


class ChatIn(BaseModel):
    message: str


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
<meta name="theme-color" content="#0b0d12">
<title>Aster Voss</title>
<style>
*{box-sizing:border-box}
body{margin:0;background:#0b0d12;color:#f4f5f7;font-family:-apple-system,BlinkMacSystemFont,"SF Pro Display","Segoe UI",sans-serif}
main{max-width:820px;margin:auto;min-height:100vh;padding:18px 16px calc(24px + env(safe-area-inset-bottom))}
header{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:4px 0 18px}
.brand{display:flex;align-items:center;gap:10px}
.logo{width:42px;height:42px;border-radius:14px;background:#171b24;display:grid;place-items:center;font-size:21px}
h1{font-size:22px;margin:0;letter-spacing:-.4px}
.sub{font-size:12px;color:#7f8796;margin-top:3px}
.new{border:1px solid #303746;background:#121620;color:#e9edf5;border-radius:12px;padding:10px 13px;font-weight:600;font-size:14px}
.new:active{transform:scale(.97)}
.chat{min-height:calc(100vh - 220px);padding:10px 2px 150px;display:flex;flex-direction:column;gap:12px}
.msg{padding:12px 15px;border-radius:18px;white-space:pre-wrap;line-height:1.6;font-size:16px;max-width:88%;word-break:break-word}
.u{align-self:flex-end;background:#2b6cff;color:white;border-bottom-right-radius:6px}
.a{align-self:flex-start;background:#171b24;border-bottom-left-radius:6px}
.welcome{align-self:flex-start;background:#11151d;border:1px solid #252c38;color:#aeb6c4;max-width:92%}
.bar{position:fixed;left:50%;bottom:0;transform:translateX(-50%);width:min(820px,100%);padding:10px 16px calc(12px + env(safe-area-inset-bottom));background:linear-gradient(transparent,#0b0d12 20%);display:flex;gap:8px;align-items:flex-end}
textarea{flex:1;min-height:48px;max-height:140px;resize:none;border-radius:16px;border:1px solid #303746;background:#121620;color:white;padding:13px 14px;font:inherit;outline:none}
textarea:focus{border-color:#4c78d8}
.send{height:48px;border:0;border-radius:15px;padding:0 17px;background:#f4f5f7;color:#11151d;font-weight:700}
.send:disabled{opacity:.5}
.status{font-size:12px;color:#6f7785;text-align:center;padding:4px}

/* Phase 5: clean AI workspace inspired by modern ChatGPT / Claude patterns. */
.sidebar{position:fixed;inset:0 auto 0 0;width:238px;background:#0f1218;border-right:1px solid #252b36;padding:14px 11px;display:flex;flex-direction:column;z-index:10}
.side-brand{display:flex;align-items:center;gap:10px;padding:5px 8px 15px}
.side-logo{width:34px;height:34px;border-radius:11px;background:#171c25;display:grid;place-items:center;font-size:18px}
.side-name{font-size:14px;font-weight:700}.side-sub{font-size:11px;color:#7d8695;margin-top:2px}
.side-new{width:100%;border:1px solid #2b3340;background:transparent;color:#edf0f5;border-radius:10px;padding:9px 11px;text-align:left;font-size:13px;font-weight:650}
.side-nav{display:flex;flex-direction:column;gap:3px;margin-top:14px}
.side-item{border:0;background:transparent;color:#8c95a5;border-radius:9px;padding:9px 10px;text-align:left;font-size:13px;display:flex;gap:9px;align-items:center}
.side-item:hover,.side-item.active{background:#181d26;color:#eef1f6}
.side-spacer{flex:1}.side-foot{border-top:1px solid #252b36;padding-top:8px}
.side-foot button{width:100%;border:0;background:transparent;color:#8c95a5;border-radius:9px;padding:9px 10px;text-align:left;font-size:13px}
.side-foot button:hover{background:#181d26;color:#eef1f6}
.settings-panel{position:fixed;top:0;right:0;bottom:0;width:min(430px,94vw);background:#11151c;border-left:1px solid #2a303c;box-shadow:0 18px 70px rgba(0,0,0,.45);transform:translateX(100%);transition:transform .2s ease;z-index:31;display:flex;flex-direction:column}
.settings-panel.open{transform:translateX(0)}
.settings-overlay{position:fixed;inset:0;background:rgba(0,0,0,.45);opacity:0;pointer-events:none;transition:opacity .2s ease;z-index:30}
.settings-overlay.open{opacity:1;pointer-events:auto}
.settings-head{display:flex;align-items:center;justify-content:space-between;padding:18px;border-bottom:1px solid #2a303c}
.settings-title{font-size:18px;font-weight:700}.settings-close{border:0;background:transparent;color:#8c95a5;font-size:24px}
.settings-body{padding:18px;overflow:auto}.settings-section{margin-bottom:28px}
.settings-section h2{font-size:13px;margin:0 0 6px}.settings-section p{font-size:12px;color:#8c95a5;line-height:1.6;margin:0 0 12px}
.memory-compose{display:flex;gap:7px}.memory-compose input{flex:1;min-width:0;border:1px solid #303746;background:#171b24;color:#f4f5f7;border-radius:10px;padding:10px;outline:0}
.memory-compose input:focus{border-color:#4a6cae}.memory-primary{border:0;background:#f4f5f7;color:#11151d;border-radius:10px;padding:10px 12px;font-weight:700}
.memory-full{width:100%;margin-top:8px;border:1px solid #303746;background:transparent;color:#e8ebf0;border-radius:10px;padding:10px 12px;text-align:left;font-size:12px}
.memory-full:hover{background:#181d26}.memory-list{display:flex;flex-direction:column;gap:8px;margin-top:13px}
.memory-card{border:1px solid #2a303c;background:#151922;border-radius:12px;padding:11px}
.memory-row{display:flex;justify-content:space-between;align-items:center;gap:8px}.memory-label{font-size:10px;color:#7f8796;letter-spacing:.06em;text-transform:uppercase}
.memory-actions{display:flex;gap:4px}.memory-actions button{border:0;background:transparent;color:#8c95a5;font-size:11px;padding:4px 5px;border-radius:7px}
.memory-actions button:hover{background:#202631;color:#f3f5f7}.memory-text{font-size:12.5px;line-height:1.55;margin-top:7px;white-space:pre-wrap;word-break:break-word}
.memory-card textarea{width:100%;min-height:82px;resize:vertical;border:1px solid #303746;background:#11151c;color:#f4f5f7;border-radius:9px;padding:9px;margin-top:7px;outline:0;line-height:1.5}
.memory-save{border:0;background:#f4f5f7;color:#11151d;border-radius:8px;padding:7px 10px;font-size:11px;font-weight:700;margin-top:7px}
.memory-cancel{border:1px solid #303746;background:transparent;color:#d8dce3;border-radius:8px;padding:7px 10px;font-size:11px;margin:7px 0 0 5px}
.memory-empty{border:1px dashed #303746;border-radius:12px;padding:19px 12px;text-align:center;color:#7f8796;font-size:12px;line-height:1.6}
.settings-theme{display:flex;background:#171b24;border-radius:10px;padding:3px;gap:3px}.theme-option{flex:1;border:0;background:transparent;color:#8c95a5;border-radius:8px;padding:8px;font-size:12px}.theme-option.active{background:#11151c;color:#f4f5f7}
@media(min-width:900px){main{margin-left:238px;margin-right:0}.bar{width:min(820px,calc(100vw - 270px));left:calc(50% + 119px)}.settings-panel{width:430px}}
@media(max-width:899px){.sidebar{transform:translateX(-100%);transition:transform .2s ease;width:270px}.sidebar.open{transform:translateX(0)}.bar{width:100%}.mobile-side{display:grid!important}}
.mobile-side{display:none;border:0;background:transparent;color:#aab2bf;font-size:20px}</style>
</head>
<body>
<aside class="sidebar" id="sidebar">
  <div class="side-brand"><div class="side-logo">✦</div><div><div class="side-name">Aster Voss</div><div class="side-sub">Personal AI Agent</div></div></div>
  <button class="side-new" onclick="newChat()">＋ 新对话</button>
  <div class="side-nav">
    <button class="side-item active"><span>⌂</span>对话</button>
    <button class="side-item" onclick="openSettings()">◉ 长期记忆</button>
  </div>
  <div class="side-spacer"></div>
  <div class="side-foot"><button onclick="openSettings()">⚙ 设置</button></div>
</aside>
<main>
<header>
  <button class="mobile-side" onclick="toggleAsterSidebar()" aria-label="打开菜单">☰</button>
  <div class="brand">
    <div class="logo">✦</div>
    <div><h1>Aster Voss</h1><div class="sub">Your Personal AI Agent · persistent memory</div></div>
  </div>
  <button class="new" onclick="newChat()">＋ 新对话</button>
</header>

<div id="chat" class="chat">
  <div class="msg welcome">你好，我是 Aster Voss。<br>这是我的新对话空间。你可以直接和我聊天，也可以说“记住：……”让我记住一件事。</div>
</div>

<div class="status" id="status"></div>

<div class="bar">
  <textarea id="input" rows="1" placeholder="和 Aster 说点什么…"></textarea>
  <button class="send" id="send" onclick="send()">发送</button>
</div>
</main>

<div class="settings-overlay" id="settings-overlay" onclick="closeSettings()"></div>
<aside class="settings-panel" id="settings-panel" aria-label="设置">
  <div class="settings-head"><div class="settings-title">设置</div><button class="settings-close" onclick="closeSettings()" aria-label="关闭">×</button></div>
  <div class="settings-body">
    <section class="settings-section">
      <h2>外观</h2><p>保持简洁、安静的工作空间。主题会保存在当前设备。</p>
      <div class="settings-theme"><button class="theme-option" data-theme="dark" onclick="setAsterTheme("dark")">深色</button><button class="theme-option" data-theme="light" onclick="setAsterTheme("light")">浅色</button></div>
    </section>
    <section class="settings-section">
      <h2>🧠 长期记忆</h2><p>这里是 Aster 的可编辑长期记忆。记忆会参与后续对话，但不会因为“新对话”而被清空。</p>
      <div class="memory-compose"><input id="memory-input" placeholder="添加一条长期记忆…"><button class="memory-primary" onclick="addAsterMemory()">添加</button></div>
      <button class="memory-full" id="memory-summary" onclick="summarizeAsterMemory()">✨ 从最近对话整理</button>
      <div class="memory-list" id="memory-list"><div class="memory-empty">正在读取…</div></div>
    </section>
  </div>
</aside>
<div class="toast" id="toast"></div>

<script>
const c=document.querySelector("#chat");
const i=document.querySelector("#input");
const b=document.querySelector("#send");
const s=document.querySelector("#status");

function add(t,k){
  const d=document.createElement("div");
  d.className="msg "+k;
  d.textContent=t;
  c.appendChild(d);
  window.scrollTo({top:document.body.scrollHeight,behavior:"smooth"});
}

async function send(){
  const v=i.value.trim();
  if(!v || b.disabled)return;
  add(v,"u");
  i.value="";
  i.style.height="48px";
  b.disabled=true;
  s.textContent="Aster 正在思考…";
  try{
    const r=await fetch("/api/chat",{
      method:"POST",
      headers:{"Content-Type":"application/json"},
      body:JSON.stringify({message:v})
    });
    const x=await r.json();
    if(!r.ok) throw new Error(x.detail||x.error||"请求失败");
    add(x.text||"……","a");
  }catch(e){
    add("抱歉，刚才没有成功收到回复。请再试一次。","a");
    console.error(e);
  }finally{
    b.disabled=false;
    s.textContent="";
    i.focus();
  }
}

async function newChat(){
  if(!confirm("开启新对话？当前聊天会被清空，但 Aster 的长期记忆不会删除。"))return;
  try{
    await fetch("/api/reset",{method:"POST"});
  }catch(e){}
  c.innerHTML='<div class="msg welcome">新对话开始。<br>你好，我还是 Aster Voss。长期记忆不会因为新对话而消失。</div>';
  s.textContent="已开启新对话";
  setTimeout(()=>s.textContent="",1500);
  i.focus();
}

i.addEventListener("input",()=>{
  i.style.height="auto";
  i.style.height=Math.min(i.scrollHeight,140)+"px";
});
i.addEventListener("keydown",e=>{
  if(e.key==="Enter"&&!e.shiftKey){
    e.preventDefault();
    send();
  }
});
</script>
</body>
</html>""")


@app.post("/api/chat")
def chat(body: ChatIn):
    # Refresh durable memory before every model call so cloud changes are visible
    # without restarting the server.
    agent.refresh_system_prompt(build_prompt())
    r = agent.run(body.message)
    return {"text": r.text, "provider": r.provider, "model": r.model}


@app.post("/api/reset")
def reset():
    agent.reset()
    return {"ok": True}


@app.get("/api/memory")
def get_memories():
    return {"cloud": brain.enabled(), "memories": brain.load_entries()}


@app.post("/api/memory")
def add_memory(body: MemoryIn):
    text_value = brain.scrub_secrets(body.text).strip()
    if not text_value:
        raise HTTPException(status_code=400, detail="记忆内容不能为空")
    if not brain.add(text_value, source="manual"):
        raise HTTPException(status_code=503, detail="长期记忆暂时无法保存")
    agent.refresh_system_prompt(build_prompt())
    return {"ok": True}


@app.put("/api/memory/{memory_id}")
def edit_memory(memory_id: str, body: MemoryEditIn):
    text_value = brain.scrub_secrets(body.text).strip()
    if not text_value:
        raise HTTPException(status_code=400, detail="记忆内容不能为空")
    memories = brain.load_entries()
    for item in memories:
        if str(item.get("id")) == str(memory_id):
            item["text"] = text_value
            item["source"] = item.get("source") or "manual"
            if not brain.replace(memories):
                raise HTTPException(status_code=503, detail="长期记忆暂时无法保存")
            agent.refresh_system_prompt(build_prompt())
            return {"ok": True}
    raise HTTPException(status_code=404, detail="记忆不存在")


@app.delete("/api/memory/{memory_id}")
def remove_memory(memory_id: str):
    if not brain.delete(memory_id):
        raise HTTPException(status_code=503, detail="长期记忆暂时无法保存")
    agent.refresh_system_prompt(build_prompt())
    return {"ok": True}


@app.post("/api/memory/summarize")
def summarize_memories():
    messages = [
        m for m in agent.messages
        if m.role in {"user", "assistant"} and (m.content or "").strip()
    ][-16:]
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
        decision = agent.router.select("Summarize durable user memory")
        provider = agent.router.get_provider(decision.provider_name)
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
    if saved:
        agent.refresh_system_prompt(build_prompt())
    return {"ok": True, "added": len(saved), "memories": saved}


@app.get("/api/status")
def status():    return {
        "name": AGENT_IDENTITY.name,
        "provider": CONFIG.main_provider,
        "configured": bool(CONFIG.active_provider and CONFIG.active_provider.is_configured),
    }
