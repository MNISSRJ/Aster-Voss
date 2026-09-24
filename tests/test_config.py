from config import load_config

def test_config_defaults(monkeypatch):
    for key in [
        "MAIN_PROVIDER",
        "DEEPSEEK_API_KEY",
        "DEEPSEEK_MODEL",
        "OPENAI_API_KEY",
        "OPENAI_MODEL",
    ]:
        monkeypatch.delenv(key, raising=False)
    cfg = load_config()
    assert cfg.main_provider == "deepseek"
    assert cfg.provider("deepseek").model == "deepseek-flash"
