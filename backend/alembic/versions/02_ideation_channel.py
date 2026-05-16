"""add channel column + index to chat_messages

Revision ID: 02_ideation_channel
Revises: 5d95cb487ab3
Create Date: 2026-05-15
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "02_ideation_channel"
down_revision = "5d95cb487ab3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # CONCURRENTLY can't run inside a transaction in PostgreSQL.
    # autocommit_block handles this; SQLite silently ignores it.
    op.add_column(
        "chat_messages",
        sa.Column(
            "channel",
            sa.String(length=20),
            server_default="main",
            nullable=False,
        ),
    )
    with op.get_context().autocommit_block():
        op.create_index(
            op.f("ix_chat_messages_proposal_channel_created"),
            "chat_messages",
            ["proposal_id", "channel", "created_at"],
            postgresql_concurrently=True,
        )


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.drop_index(
            op.f("ix_chat_messages_proposal_channel_created"),
            table_name="chat_messages",
            postgresql_concurrently=True,
        )
    op.drop_column("chat_messages", "channel")
