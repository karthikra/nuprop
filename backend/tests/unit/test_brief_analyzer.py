"""Unit tests for app.services.ai.brief_analyzer — response parsing & message build."""

from __future__ import annotations

from app.services.ai.brief_analyzer import BriefAnalyzer


def test_parse_plain_text_is_not_complete():
    analyzer = BriefAnalyzer()
    result = analyzer._parse_response("What's the client's name and industry?")
    assert result.brief_complete is False
    assert result.brief_data == {}
    assert result.response_text == "What's the client's name and industry?"


def test_parse_extracts_completed_brief_and_strips_json_block():
    analyzer = BriefAnalyzer()
    text = (
        "Here's the brief I've put together:\n\n"
        "```json\n"
        '{"brief_complete": true, "brief": {"client": {"name": "Acme"}}}\n'
        "```\n\n"
        "Does this look right?"
    )
    result = analyzer._parse_response(text)
    assert result.brief_complete is True
    assert result.brief_data == {"client": {"name": "Acme"}}
    assert "```json" not in result.response_text
    assert "Here's the brief" in result.response_text
    assert "Does this look right?" in result.response_text


def test_parse_malformed_json_fence_is_graceful():
    analyzer = BriefAnalyzer()
    text = '```json\n{"brief_complete": true, "brief": {bad json}\n```'
    result = analyzer._parse_response(text)
    assert result.brief_complete is False
    assert result.brief_data == {}


def test_build_messages_injects_current_brief_context():
    analyzer = BriefAnalyzer()
    msgs = analyzer._build_messages(
        chat_history=[{"role": "user", "content": "hi"}],
        current_brief={"client": {"name": "Acme"}},
    )
    # first two messages are the synthetic brief-context priming pair
    assert msgs[0]["role"] == "user"
    assert "Current brief state" in msgs[0]["content"]
    assert msgs[1]["role"] == "assistant"
    assert msgs[-1] == {"role": "user", "content": "hi"}


def test_build_messages_without_brief_just_maps_history():
    analyzer = BriefAnalyzer()
    msgs = analyzer._build_messages(
        chat_history=[
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi there"},
        ],
        current_brief={},
    )
    assert msgs == [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "hi there"},
    ]
