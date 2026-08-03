"""add evidence decisions and refusal tickets

Revision ID: cc99b700f739
Revises: c8784d439b23
Create Date: 2026-08-03 16:46:54.471127
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "cc99b700f739"
down_revision: str | Sequence[str] | None = "c8784d439b23"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "tickets",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("system_id", sa.Uuid(), nullable=False),
        sa.Column("requester_id", sa.Uuid(), nullable=False),
        sa.Column("source_run_id", sa.Uuid(), nullable=False),
        sa.Column("assignee_id", sa.Uuid(), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "open",
                "assigned",
                "in_progress",
                "resolved",
                "closed",
                name="ticket_status",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column(
            "priority",
            sa.Enum(
                "normal",
                name="ticket_priority",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("title", sa.String(length=120), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("normalized_question", sa.Text(), nullable=False),
        sa.Column("deduplication_key", sa.String(length=64), nullable=False),
        sa.Column("occurrence_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("row_version", sa.Integer(), nullable=False),
        sa.CheckConstraint("occurrence_count > 0", name="ck_tickets_occurrence_count"),
        sa.ForeignKeyConstraint(["assignee_id"], ["accounts.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["requester_id"], ["accounts.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["system_id"],
            ["business_systems.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("id", "system_id", name="uq_tickets_id_system"),
        sa.UniqueConstraint("source_run_id"),
    )
    op.create_index(
        "ix_tickets_system_status_assignee",
        "tickets",
        ["system_id", "status", "assignee_id"],
        unique=False,
    )
    op.create_index(
        "ix_tickets_system_deduplication_updated",
        "tickets",
        ["system_id", "deduplication_key", "updated_at"],
        unique=False,
    )
    json_value = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")
    op.create_table(
        "evidence_decisions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("system_id", sa.Uuid(), nullable=False),
        sa.Column("ticket_id", sa.Uuid(), nullable=True),
        sa.Column("query", sa.Text(), nullable=False),
        sa.Column("normalized_query", sa.Text(), nullable=False),
        sa.Column(
            "outcome",
            sa.Enum(
                "sufficient",
                "insufficient",
                "conflicting",
                name="evidence_decision_outcome",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("reason_codes", json_value, nullable=False),
        sa.Column("score", sa.Float(), nullable=True),
        sa.Column("applied_score_threshold", sa.Float(), nullable=False),
        sa.Column("policy_version", sa.String(length=100), nullable=False),
        sa.Column("candidate_summaries", json_value, nullable=False),
        sa.Column("degraded_reasons", json_value, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["system_id"],
            ["business_systems.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["ticket_id", "system_id"],
            ["tickets.id", "tickets.system_id"],
            ondelete="RESTRICT",
            name="fk_evidence_decisions_ticket_system",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id"),
    )
    op.create_index(
        "ix_evidence_decisions_system_outcome_created",
        "evidence_decisions",
        ["system_id", "outcome", "created_at"],
        unique=False,
    )
    op.create_table(
        "ticket_occurrences",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("ticket_id", sa.Uuid(), nullable=False),
        sa.Column("system_id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("requester_id", sa.Uuid(), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["requester_id"],
            ["accounts.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["evidence_decisions.run_id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["ticket_id", "system_id"],
            ["tickets.id", "tickets.system_id"],
            ondelete="CASCADE",
            name="fk_ticket_occurrences_ticket_system",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id"),
    )
    op.create_index(
        "ix_ticket_occurrences_requester_created",
        "ticket_occurrences",
        ["requester_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_ticket_occurrences_requester_created",
        table_name="ticket_occurrences",
    )
    op.drop_table("ticket_occurrences")
    op.drop_index(
        "ix_evidence_decisions_system_outcome_created",
        table_name="evidence_decisions",
    )
    op.drop_table("evidence_decisions")
    op.drop_index("ix_tickets_system_deduplication_updated", table_name="tickets")
    op.drop_index("ix_tickets_system_status_assignee", table_name="tickets")
    op.drop_table("tickets")
