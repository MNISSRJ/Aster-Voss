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
      <button class="side-item" id="nav-memory">◉ <span>长期记忆</span></button>
    </nav>
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
const memoryInput=document.querySelector("#memory-input");

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
      body:JSON.stringify({message:value})
    });
    const data=await response.json().catch(()=>({}));
    if(!response.ok)throw new Error(data.detail||data.error||"请求失败");
    thinking.remove();
    addMessage(data.text||"……","a");
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

function toggleSidebar(){sidebar.classList.toggle("open")}
document.querySelector("#mobile-menu").addEventListener("click",toggleSidebar);

async function resetChat(){
  try{await fetch("/api/reset",{method:"POST"});}catch(error){console.error(error)}
  chat.innerHTML='<div class="msg a welcome">新对话开始。<br>你好，我还是 Aster Voss。长期记忆不会因为新对话而消失。</div>';
  input.focus();
  showToast("已开启新对话");
  sidebar.classList.remove("open");
}
document.querySelector("#new-chat-side").addEventListener("click",resetChat);
document.querySelector("#new-chat-top").addEventListener("click",resetChat);
document.querySelector("#nav-chat").addEventListener("click",()=>{sidebar.classList.remove("open");});
document.querySelector("#nav-memory").addEventListener("click",openSettings);
document.querySelector("#settings-side").addEventListener("click",openSettings);

function openSettings(){
  settings.classList.add("open");
  overlay.classList.add("open");
  loadMemories();
  sidebar.classList.remove("open");
}
function closeSettings(){settings.classList.remove("open");overlay.classList.remove("open")}
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
    const response=await fetch("/api/memory/summarize",{method:"POST"});
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
