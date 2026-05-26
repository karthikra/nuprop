"""drop legacy text columns; add nine per-section JSON columns

Revision ID: 05_proposal_section_columns
Revises: 04_proposal_rate_card_columns
Create Date: 2026-05-26
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "05_proposal_section_columns"
down_revision = "04_proposal_rate_card_columns"
branch_labels = None
depends_on = None


_LEGACY_COLUMNS = [
    "covering_letter",
    "covering_letter_alt",
    "executive_summary",  # re-added below as JSON
    "scope_sections",
    "cost_rationale",
    "terms",
    "email_draft",
]

_SECTION_COLUMNS = [
    "cover_page",
    "executive_summary",
    "problem_statement",
    "proposed_solution",
    "scope_of_work",
    "timeline",
    "pricing",
    "qualifications",
    "terms_and_conditions",
]


def upgrade() -> None:
    for col in _LEGACY_COLUMNS:
        op.drop_column("proposals", col)
    for col in _SECTION_COLUMNS:
        op.add_column("proposals", sa.Column(col, sa.JSON(), nullable=True))


def downgrade() -> None:
    for col in reversed(_SECTION_COLUMNS):
        op.drop_column("proposals", col)
    op.add_column("proposals", sa.Column("covering_letter", sa.Text(), nullable=True))
    op.add_column("proposals", sa.Column("covering_letter_alt", sa.Text(), nullable=True))
    op.add_column("proposals", sa.Column("executive_summary", sa.Text(), nullable=True))
    op.add_column("proposals", sa.Column("scope_sections", sa.JSON(), nullable=True))
    op.add_column("proposals", sa.Column("cost_rationale", sa.Text(), nullable=True))
    op.add_column("proposals", sa.Column("terms", sa.Text(), nullable=True))
    op.add_column("proposals", sa.Column("email_draft", sa.Text(), nullable=True))
