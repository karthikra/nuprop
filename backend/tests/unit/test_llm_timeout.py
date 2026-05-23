from __future__ import annotations


def test_ai_service_passes_timeout_to_bedrock_client(monkeypatch):
    """AIService must construct AsyncAnthropicBedrock with an explicit
    timeout so a hung Bedrock call cannot stall a pipeline phase."""
    captured: dict = {}

    class FakeBedrock:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr("app.services.llm.AsyncAnthropicBedrock", FakeBedrock)

    from app.services.llm import LLM_TIMEOUT_SECONDS, AIService

    AIService()

    assert captured["timeout"] == LLM_TIMEOUT_SECONDS
    assert LLM_TIMEOUT_SECONDS == 120.0
