from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from agent import AsterVoss
from aster import AGENT_IDENTITY, AGENT_TAGLINE, get_memory
from config import load_config
from memory.persistence import long_term_context
from pathlib import Path

CONFIG = load_config()

def build_prompt():
    m = get_memory().context_block(reload=True)
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
</style>
</head>
<body>
<main>
<header>
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
    r = agent.run(body.message)
    return {"text": r.text, "provider": r.provider, "model": r.model}


@app.post("/api/reset")
def reset():
    agent.reset()
    return {"ok": True}


@app.get("/api/_phase3-test")
def phase3_test():
    """Temporary preview-only CRUD probe for Supabase cloud memory."""
    from memory import brain

    test_user = "phase3-test"
    test_text = "Aster Phase 3 cloud-memory connectivity test"
    ok = {
        "cloud_enabled": brain.enabled(),
        "saved": False,
        "loaded": False,
        "deleted": False,
        "remaining": False,
    }
    if not ok["cloud_enabled"]:
        return ok

    try:
        # Start from a clean test row, then exercise save -> read -> delete -> read.
        brain.replace([], user_id=test_user)
    except TypeError:
        # Backward-compatible path if the branch implementation still uses the
        # fixed Mint user id.
        test_user = brain.USER_ID

    try:
        entry = {
            "id": "phase3-test-entry",
            "text": test_text,
            "source": "phase3-test",
            "created_at": brain._now(),
        }
        ok["saved"] = bool(brain.save_entries([entry], user_id=test_user))
        loaded = brain.load_entries(user_id=test_user)
        ok["loaded"] = any(item.get("text") == test_text for item in loaded)
        ok["deleted"] = bool(brain.replace([], user_id=test_user))
        remaining = brain.load_entries(user_id=test_user)
        ok["remaining"] = any(item.get("text") == test_text for item in remaining)
    except Exception as exc:
        ok["error"] = str(exc)
    return ok


@app.get("/api/status")
def status():
    return {
        "name": AGENT_IDENTITY.name,
        "provider": CONFIG.main_provider,
        "configured": bool(CONFIG.active_provider and CONFIG.active_provider.is_configured),
    }
