from config import load_config
from agent import TaskRouter

def test_router_classifies_reasoning(monkeypatch):
    monkeypatch.setenv("MAIN_PROVIDER","deepseek")
    monkeypatch.setenv("AUTO_ROUTING","false")
    router=TaskRouter(load_config())
    decision=router.select("请帮我证明这个线性代数结论")
    assert decision.complexity >= 2
    assert decision.source.startswith("rules:")

def test_router_classifies_tools(monkeypatch):
    router=TaskRouter(load_config())
    decision=router.select("读取项目中的 agent.py")
    assert decision.complexity >= 2
