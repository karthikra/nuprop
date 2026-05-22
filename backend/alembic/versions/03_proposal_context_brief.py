"""add context_brief column to proposals

Revision ID: 03_proposal_context_brief
Revises: 02_ideation_channel
Create Date: 2026-05-21
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "03_proposal_context_brief"
down_revision = "02_ideation_channel"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("proposals", sa.Column("context_brief", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("proposals", "context_brief")
