from __future__ import annotations

from app.services.media.section_assets import (
    append_asset_to_section,
    default_section_for_assets,
    remove_asset_from_section,
    resign_assets,
)


def test_default_section_for_assets_neutral_payload():
    s = default_section_for_assets()
    assert s == {"content": "", "assets": [], "included": True, "metadata": {}}


def test_append_asset_to_none_section_initialises_default():
    new = append_asset_to_section(None, {"id": "a1", "kind": "image", "s3_key": "k1"})
    assert new["content"] == ""
    assert new["included"] is True
    assert new["assets"] == [{"id": "a1", "kind": "image", "s3_key": "k1"}]


def test_append_asset_preserves_existing_content_and_assets():
    current = {
        "content": "hello",
        "assets": [{"id": "a1", "kind": "image", "s3_key": "k1"}],
        "included": True,
        "metadata": {"k": "v"},
    }
    new = append_asset_to_section(current, {"id": "a2", "kind": "image", "s3_key": "k2"})
    assert new["content"] == "hello"
    assert new["metadata"] == {"k": "v"}
    assert len(new["assets"]) == 2
    assert new["assets"][1]["id"] == "a2"


def test_remove_asset_returns_section_minus_matching_asset():
    current = {
        "content": "hi",
        "assets": [
            {"id": "a1", "kind": "image", "s3_key": "k1"},
            {"id": "a2", "kind": "image", "s3_key": "k2"},
        ],
        "included": True,
        "metadata": {},
    }
    new, removed = remove_asset_from_section(current, asset_id="a1")
    assert removed == {"id": "a1", "kind": "image", "s3_key": "k1"}
    assert [a["id"] for a in new["assets"]] == ["a2"]


def test_remove_asset_returns_none_when_not_found():
    current = {
        "content": "",
        "assets": [{"id": "a1", "kind": "image", "s3_key": "k1"}],
        "included": True,
        "metadata": {},
    }
    new, removed = remove_asset_from_section(current, asset_id="missing")
    assert removed is None
    assert new == current


def test_resign_assets_replaces_url_using_provided_signer():
    section = {
        "content": "",
        "assets": [
            {"id": "a1", "kind": "image", "s3_key": "k1", "url": "stale"},
            {"id": "a2", "kind": "image", "s3_key": "k2"},
        ],
        "included": True,
        "metadata": {},
    }
    resigned = resign_assets(section, signer=lambda key: f"signed://{key}")
    assert resigned["assets"][0]["url"] == "signed://k1"
    assert resigned["assets"][1]["url"] == "signed://k2"
    # Original list/dicts not mutated
    assert section["assets"][0]["url"] == "stale"


def test_resign_assets_on_none_or_empty_returns_input_unchanged():
    assert resign_assets(None, signer=lambda _: "x") is None
    assert resign_assets({"assets": []}, signer=lambda _: "x") == {"assets": []}
