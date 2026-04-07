from __future__ import annotations

import json
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.db.models.template import StrategyTemplate


@dataclass
class TemplateMatch:
    template_key: str
    template_name: str
    category: str
    confidence: float
    config: dict
    description: str


class TemplateMatcher:
    async def match(self, brief: dict, db: AsyncSession) -> TemplateMatch | None:
        """Match a brief against all system templates. Returns the best match or None."""
        result = await db.execute(
            select(StrategyTemplate).where(StrategyTemplate.is_system == True)
        )
        templates = list(result.scalars().all())
        if not templates:
            return None

        # Build a text blob from the brief to match against
        brief_text = self._brief_to_text(brief).lower()

        best_match: TemplateMatch | None = None
        best_score = 0

        for tmpl in templates:
            config = tmpl.config if isinstance(tmpl.config, dict) else json.loads(tmpl.config)
            signals = config.get("brief_intake", {}).get("auto_detect_signals", [])
            score = sum(1 for s in signals if s.lower() in brief_text)
            confidence = score / max(len(signals), 1)

            if score > best_score:
                best_score = score
                best_match = TemplateMatch(
                    template_key=tmpl.template_key,
                    template_name=tmpl.name,
                    category=tmpl.category,
                    confidence=round(confidence, 2),
                    config=config,
                    description=tmpl.description or "",
                )

        # Only return if at least 1 signal matched
        if best_match and best_score > 0:
            return best_match
        return None

    def _brief_to_text(self, brief: dict) -> str:
        """Flatten brief dict into a searchable text string."""
        parts = []
        if "project" in brief:
            proj = brief["project"]
            parts.append(proj.get("type", ""))
            for d in proj.get("deliverables", []):
                parts.append(d.get("category", ""))
                parts.append(d.get("details", ""))
            parts.append(proj.get("timeline", ""))
        if "client" in brief:
            parts.append(brief["client"].get("industry", ""))
        return " ".join(parts)
