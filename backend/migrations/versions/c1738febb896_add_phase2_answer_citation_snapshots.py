"""add phase2 answer citation snapshots

Revision ID: c1738febb896
Revises: ee1a2b3c4d5e
Create Date: 2026-08-04 07:51:37.160482
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "c1738febb896"
down_revision: str | Sequence[str] | None = "ee1a2b3c4d5e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    json_value = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")
    with op.batch_alter_table("evidence_decisions") as batch_op:
        batch_op.create_unique_constraint(
            "uq_evidence_decisions_run_system",
            ["run_id", "system_id"],
        )
    op.create_table(
        "answers",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("system_id", sa.Uuid(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("claims", json_value, nullable=False),
        sa.Column("degraded_reasons", json_value, nullable=False),
        sa.Column("model", sa.String(length=255), nullable=False),
        sa.Column("prompt_version", sa.String(length=100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["run_id", "system_id"],
            ["evidence_decisions.run_id", "evidence_decisions.system_id"],
            name="fk_answers_run_system",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("id", "system_id", name="uq_answers_id_system"),
        sa.UniqueConstraint("run_id"),
    )
    op.create_index(
        "ix_answers_system_created",
        "answers",
        ["system_id", "created_at"],
        unique=False,
    )
    op.create_table(
        "answer_citations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("answer_id", sa.Uuid(), nullable=False),
        sa.Column("system_id", sa.Uuid(), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("claim_rank", sa.Integer(), nullable=False),
        sa.Column("chunk_id", sa.Uuid(), nullable=False),
        sa.Column("source_id", sa.Uuid(), nullable=False),
        sa.Column("source_name", sa.String(length=500), nullable=False),
        sa.Column("source_version", sa.String(length=255), nullable=False),
        sa.Column("quoted_text", sa.Text(), nullable=False),
        sa.Column("locators", json_value, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["answer_id", "system_id"],
            ["answers.id", "answers.system_id"],
            name="fk_answer_citations_answer_system",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_answer_citations_answer_rank",
        "answer_citations",
        ["answer_id", "rank"],
        unique=True,
    )
    op.create_index(
        "ix_answer_citations_source",
        "answer_citations",
        ["system_id", "source_id"],
        unique=False,
    )
    with op.batch_alter_table("knowledge_sources") as batch_op:
        batch_op.create_foreign_key(
            "fk_knowledge_sources_ticket_system",
            "tickets",
            ["ticket_id", "system_id"],
            ["id", "system_id"],
            ondelete="RESTRICT",
        )
    _replace_candidate_status_constraint(include_published=True)


def downgrade() -> None:
    op.execute(
        sa.text("UPDATE knowledge_candidates SET status = 'approved' " "WHERE status = 'published'")
    )
    _replace_candidate_status_constraint(include_published=False)
    with op.batch_alter_table("knowledge_sources") as batch_op:
        batch_op.drop_constraint(
            "fk_knowledge_sources_ticket_system",
            type_="foreignkey",
        )
    op.drop_index("ix_answer_citations_source", table_name="answer_citations")
    op.drop_index("ix_answer_citations_answer_rank", table_name="answer_citations")
    op.drop_table("answer_citations")
    op.drop_index("ix_answers_system_created", table_name="answers")
    op.drop_table("answers")
    with op.batch_alter_table("evidence_decisions") as batch_op:
        batch_op.drop_constraint(
            "uq_evidence_decisions_run_system",
            type_="unique",
        )


def _replace_candidate_status_constraint(*, include_published: bool) -> None:
    values = "'pending', 'approved', 'rejected'"
    if include_published:
        values = "'pending', 'approved', 'published', 'rejected'"
    with op.batch_alter_table("knowledge_candidates") as batch_op:
        batch_op.drop_constraint("candidate_status", type_="check")
        batch_op.create_check_constraint("candidate_status", f"status IN ({values})")
