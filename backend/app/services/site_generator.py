from __future__ import annotations

from datetime import datetime
from pathlib import Path

import markdown
from jinja2 import Environment, FileSystemLoader


class SiteGenerator:
    """Generates interactive proposal websites from Jinja2 theme templates."""

    VALID_THEMES = ("editorial", "bold", "minimal", "dark", "warm")
    DEFAULT_THEME = "editorial"

    def __init__(self):
        template_dir = Path(__file__).parent.parent / "proposal_site_themes"
        self._env = Environment(
            loader=FileSystemLoader(str(template_dir)),
            autoescape=False,  # we handle escaping in templates with |e where needed
        )
        self._env.filters["currency"] = self._currency_filter
        self._env.filters["md"] = self._md_filter
        self._env.filters["currency_short"] = self._currency_short_filter

    def generate(
        self,
        proposal_data: dict,
        agency: dict,
        theme: str = "editorial",
        proposal_id: str = "",
        tracking_endpoint: str = "/api/v1/track",
    ) -> str:
        """Render a complete, self-contained proposal site HTML."""
        theme = theme if theme in self.VALID_THEMES else self.DEFAULT_THEME

        # Enrich scope sections with cost data
        cost_by_deliverable = {
            item["deliverable"]: item
            for item in proposal_data.get("cost_model", {}).get("line_items", [])
        }
        for section in proposal_data.get("scope_sections", []):
            cost_item = cost_by_deliverable.get(section.get("deliverable", ""), {})
            section.setdefault("total", cost_item.get("total", 0))
            section.setdefault("quantity", cost_item.get("quantity", 1))
            section.setdefault("unit_cost", cost_item.get("unit_cost", 0))

        template = self._env.get_template(f"{theme}/index.html")
        return template.render(
            p=proposal_data,
            agency=agency,
            theme=theme,
            proposal_id=proposal_id,
            tracking_endpoint=tracking_endpoint,
            year=datetime.now().year,
        )

    @staticmethod
    def _currency_filter(value) -> str:
        """Format number as ₹X,XX,XXX."""
        if isinstance(value, (int, float)):
            return f"₹{int(value):,}"
        return str(value)

    @staticmethod
    def _currency_short_filter(value) -> str:
        """Format as ₹X.X L or ₹X.XX Cr."""
        if not isinstance(value, (int, float)):
            return str(value)
        v = int(value)
        if v >= 10_000_000:
            return f"₹{v / 10_000_000:.2f} Cr"
        if v >= 100_000:
            return f"₹{v / 100_000:.1f} L"
        return f"₹{v:,}"

    @staticmethod
    def _md_filter(text: str) -> str:
        """Convert markdown to HTML."""
        if not text:
            return ""
        return markdown.markdown(str(text), extensions=["tables", "smarty"])
