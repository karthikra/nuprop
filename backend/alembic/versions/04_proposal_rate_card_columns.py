"""add rate_card_gaps and rate_card_override columns to proposals

Revision ID: 04_proposal_rate_card_columns
Revises: 03_proposal_context_brief
Create Date: 2026-05-24
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "04_proposal_rate_card_columns"
down_revision = "03_proposal_context_brief"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("proposals", sa.Column("rate_card_gaps", sa.JSON(), nullable=True))
    op.add_column("proposals", sa.Column("rate_card_override", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("proposals", "rate_card_override")
    op.drop_column("proposals", "rate_card_gaps")
