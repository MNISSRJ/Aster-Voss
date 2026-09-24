from config import ProviderConfig
from llm.factory import available_providers

def test_registry_exposes_deepseek():
    result = available_providers()
    assert "deepseek" in result

def test_provider_config_shape():
    cfg = ProviderConfig(
        name="test",
        api_key="x",
        model="m",
        base_url="https://example.com",
        timeout=1,
        max_tokens=10,
    )
    assert cfg.is_configured
