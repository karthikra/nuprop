"""Unit tests for ChatViewModel._merge_preferences_into_config — overlays user
preferences onto a strategy-template config without mutating the input."""

from __future__ import annotations

from app.viewmodels.chat_viewmodel import ChatViewModel

_merge = ChatViewModel._merge_preferences_into_config


def test_no_config_and_no_prefs_is_empty():
    assert _merge(None, {}) == {}


def test_empty_prefs_returns_a_copy_of_config():
    config = {"narrative": {"letter_strategy": "vision"}}
    merged = _merge(config, {})
    assert merged == config
    assert merged is not config  # a copy, not the same object


def test_prefs_override_and_extend_narrative_section():
    config = {"narrative": {"letter_strategy": "vision", "scope_detail_level": "high"}}
    merged = _merge(config, {"letter_strategy": "warm", "letter_length": "short"})
    assert merged["narrative"]["letter_strategy"] == "warm"      # overridden
    assert merged["narrative"]["letter_length"] == "short"       # added
    assert merged["narrative"]["scope_detail_level"] == "high"   # untouched


def test_prefs_populate_cost_model_and_output_sections():
    merged = _merge(
        {},
        {"pricing_model": "tiered", "discount_tags": ["existing_client"], "site_theme": "dark"},
    )
    assert merged["cost_model"]["pricing_model"] == "tiered"
    assert merged["cost_model"]["default_multipliers"] == ["existing_client"]
    assert merged["output"]["site_theme"] == "dark"


def test_merge_does_not_mutate_the_input_config():
    config = {"narrative": {"letter_strategy": "vision"}}
    _merge(config, {"letter_strategy": "warm"})
    assert config["narrative"]["letter_strategy"] == "vision"
