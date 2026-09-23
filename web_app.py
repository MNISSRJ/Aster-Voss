from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from agent import AsterVoss
from aster import AGENT_IDENTITY,AGENT_TAGLINE,get_memory
from config import load_config
CONFIG=load_config()
def build_prompt():
    m=get_memory().context_block(reload=True)
    return AGENT_IDENTITY.render_system_prompt()+("\n\n"+m if m else "")
agent=AsterVoss(CONFIG,system_prompt=build_prompt(),identity_name=AGENT_IDENTITY.name,identity_tagline=AGENT_TAGLINE)
app=FastAPI(title="Aster Voss")
class ChatIn(BaseModel): message:str
@app.get("/",response_class=HTMLResponse)
def home():
    return HTMLResponse("""<!doctype html><meta name="viewport" content="width=device-width,initial-scale=1"><title>Aster Voss</title><style>body{margin:0;background:#0b0d12;color:#f4f5f7;font-family:-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif}main{max-width:760px;margin:auto;padding:24px 16px}h1{font-size:30px}.chat{min-height:60vh;display:flex;flex-direction:column;gap:12px}.msg{padding:13px 15px;border-radius:16px;white-space:pre-wrap;line-height:1.55}.u{align-self:flex-end;background:#2b6cff;max-width:85%}.a{background:#171b24;max-width:90%}.bar{display:flex;gap:8px;position:sticky;bottom:10px}textarea{flex:1;border-radius:14px;border:1px solid #303746;background:#121620;color:white;padding:12px;font:inherit}button{border:0;border-radius:14px;padding:0 18px;font-weight:700}small{color:#777}</style><main><h1>✦ Aster Voss</h1><p>Your Personal AI Agent · persistent memory</p><div id="chat" class="chat"></div><div class="bar"><textarea id="input" rows="2" placeholder="和 Aster 说点什么…"></textarea><button onclick="send()">发送</button></div><small>“记住：……”会写入长期记忆；/reset 只清当前聊天。</small></main><script>const c=document.querySelector("#chat"),i=document.querySelector("#input");function add(t,k){let d=document.createElement("div");d.className="msg "+k;d.textContent=t;c.appendChild(d);scrollTo(0,document.body.scrollHeight)}async function send(){let v=i.value.trim();if(!v)return;add(v,"u");i.value="";let r=await fetch("/api/chat",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({message:v})});let x=await r.json();add(x.text||x.error||"出错了","a")}i.addEventListener("keydown",e=>{if(e.key==="Enter"&&!e.shiftKey){e.preventDefault();send()}})</script>""")
@app.post("/api/chat")
def chat(body:ChatIn):
    r=agent.run(body.message); return {"text":r.text,"provider":r.provider,"model":r.model}
@app.post("/api/reset")
def reset(): agent.reset(); return {"ok":True}
@app.get("/api/status")
def status(): return {"name":AGENT_IDENTITY.name,"provider":CONFIG.main_provider,"configured":bool(CONFIG.active_provider and CONFIG.active_provider.is_configured)}
