"""add phase2 vector and lexical retrieval

Revision ID: c8784d439b23
Revises: 3ba86a4c3d35
Create Date: 2026-08-03 10:00:41.507052
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

revision: str = "c8784d439b23"
down_revision: str | Sequence[str] | None = "3ba86a4c3d35"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    if _is_postgresql():
        op.execute("CREATE EXTENSION IF NOT EXISTS vector")
        op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.add_column(
        "knowledge_chunks",
        sa.Column(
            "embedding",
            sa.JSON().with_variant(Vector(), "postgresql"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_knowledge_chunks_retrieval_trgm",
        "knowledge_chunks",
        ["retrieval_text"],
        unique=False,
        postgresql_using="gin",
        postgresql_ops={"retrieval_text": "gin_trgm_ops"},
    )


def downgrade() -> None:
    op.drop_index("ix_knowledge_chunks_retrieval_trgm", table_name="knowledge_chunks")
    op.drop_column("knowledge_chunks", "embedding")


def _is_postgresql() -> bool:
    return op.get_bind().dialect.name == "postgresql"
