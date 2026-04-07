from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.db.models.base import IS_SQLITE
from app.infrastructure.db.models.template import StrategyTemplate

# Path to templates JSON — check multiple locations
_TEMPLATE_PATHS = [
    Path(__file__).parent.parent.parent.parent / "web_app_seed" / "veeville-templates.json",
    Path.home() / ".claude" / "skills" / "proposal-gen" / "templates" / "veeville-templates.json",
]


def _find_templates_file() -> Path | None:
    for p in _TEMPLATE_PATHS:
        if p.exists():
            return p
    return None


async def seed_templates(db: AsyncSession) -> int:
    """Seed system strategy templates if none exist. Returns count seeded."""
    result = await db.execute(
        select(StrategyTemplate).where(StrategyTemplate.is_system == True).limit(1)
    )
    if result.scalar_one_or_none():
        return 0  # already seeded

    templates_file = _find_templates_file()
    if not templates_file:
        return 0

    with open(templates_file) as f:
        data = json.load(f)

    count = 0
    for tmpl in data.get("templates", []):
        t = StrategyTemplate(
            template_key=tmpl["id"],
            name=tmpl["name"],
            description=tmpl.get("description", ""),
            category=tmpl.get("category", ""),
            config=tmpl,
            is_system=True,
            agency_id=None,
        )
        db.add(t)
        count += 1

    await db.flush()
    return count
