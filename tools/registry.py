from pathlib import Path
import json
ROOT=Path(__file__).resolve().parent.parent
def _status(args): return json.dumps({"project":"Aster Voss"},ensure_ascii=False)
def _read(args):
    p=(ROOT/str(args.get("path",""))).resolve()
    if ROOT not in p.parents and p!=ROOT:return "Refused: outside project."
    if not p.is_file():return "File not found."
    return p.read_text(encoding="utf-8",errors="replace")[:12000]
REGISTRY={"project_status":(_status,"Return project status."),"read_project_file":(_read,"Read a text file inside the project.")}
def tool_specs():
    return [{"type":"function","function":{"name":n,"description":d,"parameters":{"type":"object","properties":{"path":{"type":"string"}}}}} for n,(_,d) in REGISTRY.items()]
def run_tool(name,args):
    if name not in REGISTRY:return "Unknown tool."
    try:return REGISTRY[name][0](args or {})
    except Exception as e:return f"Tool error: {e}"
