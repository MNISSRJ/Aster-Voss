from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from agent import AsterVoss
from aster import AGENT_IDENTITY, AGENT_TAGLINE, get_memory
from config import load_config
from memory.persistence import long_term_context
from memory.brain import load_entries, add as add_memory, delete as delete_memory, replace as replace_memory
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

class MemoryIn(BaseModel):
    text: str

class MemoryListIn(BaseModel):
    memories: list[dict]


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
.status{font-size:12px;color:#6f7785;text-align:center;padding:4px}.setting-card{background:#121620;border:1px solid #252c38;border-radius:18px;padding:18px}.setting-title{font-size:17px;font-weight:700}.setting-sub{font-size:13px;color:#7f8796;line-height:1.55;margin-top:7px}.memory-row{display:flex;gap:8px;align-items:center;background:#171b24;border:1px solid #2a3140;border-radius:12px;padding:10px}.memory-row input{flex:1;background:transparent;border:0;outline:0;color:#f4f5f7;font:inherit}.memory-del{border:0;background:transparent;color:#8b93a3;font-size:18px}.memory-add,.memory-ai{width:100%;margin-top:10px;border:1px solid #303746;background:#171b24;color:#e9edf5;border-radius:12px;padding:11px;font-weight:600}
</style>
</head>
<body>
<main>
<header>
  <div class="brand">
    <div class="logo">✦</div>
    <div><h1>Aster Voss</h1><div class="sub">Your Personal AI Agent · persistent memory</div></div>
  </div>
  <div style="display:flex;gap:8px"><button class="new" onclick="openSettings()">⚙ 设置</button><button class="new" onclick="newChat()">＋ 新对话</button></div>
</header>

<section id="settings" style="display:none;padding:8px 2px 120px"><div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:18px"><h2 style="margin:0;font-size:20px">设置</h2><button class="new" onclick="closeSettings()">完成</button></div><div class="setting-card"><div class="setting-title">🧠 长期记忆</div><div class="setting-sub">这里是 Aster 的云端大脑。你可以自己编辑，也可以让 Aster 从对话中整理值得长期记住的内容。</div><div id="memories" style="display:flex;flex-direction:column;gap:8px;margin-top:14px"></div><button class="memory-add" onclick="addMemory()">＋ 添加记忆</button><button class="memory-ai" onclick="summarizeMemory()">✨ 从最近对话整理</button></div></section><div id="chat" class="chat">
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
const s=document.querySelector("#status");\nconst settings=document.querySelector("#settings");

async function openSettings(){settings.style.display="block";c.style.display="none";document.querySelector(".bar").style.display="none";await loadMemories()}\nfunction closeSettings(){settings.style.display="none";c.style.display="flex";document.querySelector(".bar").style.display="flex"}\nasync function loadMemories(){const r=await fetch("/api/memory");const x=await r.json();const box=document.querySelector("#memories");box.innerHTML="";(x.memories||[]).forEach(m=>{const row=document.createElement("div");row.className="memory-row";const inp=document.createElement("input");inp.value=m.text||"";inp.onchange=()=>updateMemory(m.id,inp.value);const del=document.createElement("button");del.className="memory-del";del.textContent="×";del.onclick=()=>removeMemory(m.id);row.append(inp,del);box.appendChild(row)})}\nasync function addMemory(){const t=prompt("想让 Aster 长期记住什么？");if(!t||!t.trim())return;await fetch("/api/memory",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({text:t.trim()})});loadMemories()}\nasync function removeMemory(id){const r=await fetch("/api/memory/"+encodeURIComponent(id),{method:"DELETE"});loadMemories()}\nasync function updateMemory(id,text){const r=await fetch("/api/memory");const x=await r.json();const arr=(x.memories||[]).map(m=>String(m.id)===String(id)?{...m,text}:m);await fetch("/api/memory",{method:"PUT",headers:{"Content-Type":"application/json"},body:JSON.stringify({memories:arr})})}\nasync function summarizeMemory(){s.textContent="Aster 正在整理最近的对话…";try{const r=await fetch("/api/memory/summarize",{method:"POST"});const x=await r.json();s.textContent=x.message||"整理完成";await loadMemories()}catch(e){s.textContent="整理失败，请稍后再试"}setTimeout(()=>s.textContent="",1800)}\n\nfunction add(t,k){
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


@app.get("/api/memory")\ndef get_memories():\n    return {"memories": load_entries()}\n\n@app.post("/api/memory")\ndef post_memory(body: MemoryIn):\n    ok=add_memory(body.text, "manual")\n    return {"ok":ok}\n\n@app.put("/api/memory")\ndef put_memory(body: MemoryListIn):\n    return {"ok":replace_memory(body.memories)}\n\n@app.delete("/api/memory/{memory_id}")\ndef del_memory(memory_id: str):\n    return {"ok":delete_memory(memory_id)}\n\n@app.post("/api/memory/summarize")\ndef summarize_memory():\n    recent=[m for m in agent.messages if m.role in {"user","assistant"}][-12:]\n    if not recent: return {"ok":True,"message":"最近还没有足够的对话可以整理。"}\n    prompt="请从下面最近的对话中提取真正值得长期记住的用户信息。只提取稳定偏好、长期目标、持续项目、明确要求和重要事实；不要记录临时情绪、一次性任务、密码/API key等敏感信息。每条一行，直接写记忆内容，不要编号，不要解释。\\n\\n"+\\n        "\\n".join(f"{m.role}: {m.content}" for m in recent)\n    try:\n        p=agent.router.get_provider(CONFIG.main_provider)\n        r=p.complete([__import__("llm.base",fromlist=["LLMMessage"]).LLMMessage.system("你是记忆整理器。"),__import__("llm.base",fromlist=["LLMMessage"]).LLMMessage.user(prompt)])\n        lines=[x.strip("- •\\t ") for x in (r.text or "").splitlines() if x.strip()]\n        added=0\n        for line in lines:\n            if len(line)<3 or len(line)>300: continue\n            if add_memory(line,"conversation_summary"): added+=1\n        return {"ok":True,"message":f"整理完成，新增 {added} 条长期记忆。"}\n    except Exception as e:\n        return {"ok":False,"message":"暂时无法整理记忆。"}\n\n@app.get("/api/status")
def status():
    return {
        "name": AGENT_IDENTITY.name,
        "provider": CONFIG.main_provider,
        "configured": bool(CONFIG.active_provider and CONFIG.active_provider.is_configured),
    }
