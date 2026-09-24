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


def test_multimodal_content_builder():
    from llm.content import multimodal_content
    content = multimodal_content("look at this", ["https://example.com/a.png"])
    assert content[0]["type"] == "text"
    assert content[1]["type"] == "image_url"
