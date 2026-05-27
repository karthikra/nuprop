"""Pure helpers over the section dict — never call S3 or fal directly.

Section shape (lives on the JSON column):
    {"content": str, "assets": list[Asset], "included": bool, "metadata": dict}

Asset URLs aren't trusted past their TTL — readers always re-sign through
``resign_assets`` before serving a proposal.
"""
from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy


def default_section_for_assets() -> dict:
    """Neutral section payload used when appending an asset to a NULL column."""
    return {"content": "", "assets": [], "included": True, "metadata": {}}


def append_asset_to_section(section: dict | None, asset: dict) -> dict:
    """Return a new section dict with ``asset`` appended to ``assets``."""
    base = deepcopy(section) if section else default_section_for_assets()
    base.setdefault("assets", [])
    base["assets"] = [*base["assets"], asset]
    return base


def remove_asset_from_section(section: dict, *, asset_id: str) -> tuple[dict, dict | None]:
    """Return ``(new_section, removed_asset_or_None)``."""
    assets = section.get("assets") or []
    removed = next((a for a in assets if a.get("id") == asset_id), None)
    if removed is None:
        return section, None
    new = deepcopy(section)
    new["assets"] = [a for a in assets if a.get("id") != asset_id]
    return new, removed


def resign_assets(
    section: dict | None,
    *,
    signer: Callable[[str], str],
) -> dict | None:
    """Return a new section with every asset's ``url`` re-signed.

    ``signer(s3_key) -> presigned_url``. No-op for sections with no assets;
    returns ``None`` if the section itself is ``None``.
    """
    if section is None:
        return None
    assets = section.get("assets") or []
    if not assets:
        return section
    new = deepcopy(section)
    new["assets"] = [
        {**a, "url": signer(a["s3_key"])} for a in assets
    ]
    return new
