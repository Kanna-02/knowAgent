"""add ticket workflow and review tables

Revision ID: ee1a2b3c4d5e
Revises: cc99b700f739
Create Date: 2026-08-03 20:00:00.000000

Adds three tables for the ticket lifecycle and knowledge-review flow:

* ``ticket_replies``    — append-only messages from requester, assignee, or reviewer.
* ``ticket_transitions`` — immutable audit trail of every ticket status change.
* ``knowledge_candidates`` — answers pending/passed review, linked back to the
  knowledge source created on approval.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "ee1a2b3c4d5e"
down_revision: str | Sequence[str] | None = "cc99b700f739"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ticket_replies",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("ticket_id", sa.Uuid(), nullable=False),
        sa.Column("system_id", sa.Uuid(), nullable=False),
        sa.Column("author_id", sa.Uuid(), nullable=False),
        sa.Column(
            "author_role",
            sa.Enum(
                "requester",
                "assignee",
                "reviewer",
                name="reply_author_role",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["author_id"], ["accounts.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["ticket_id", "system_id"],
            ["tickets.id", "tickets.system_id"],
            ondelete="CASCADE",
            name="fk_ticket_replies_ticket_system",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_ticket_replies_ticket_created",
        "ticket_replies",
        ["ticket_id", "created_at"],
        unique=False,
    )

    op.create_table(
        "ticket_transitions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("ticket_id", sa.Uuid(), nullable=False),
        sa.Column("system_id", sa.Uuid(), nullable=False),
        sa.Column("actor_id", sa.Uuid(), nullable=False),
        sa.Column(
            "from_status",
            sa.Enum(
                "open",
                "assigned",
                "in_progress",
                "resolved",
                "closed",
                name="ticket_transition_from_status",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=True,
        ),
        sa.Column(
            "to_status",
            sa.Enum(
                "open",
                "assigned",
                "in_progress",
                "resolved",
                "closed",
                name="ticket_transition_to_status",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["actor_id"], ["accounts.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["ticket_id", "system_id"],
            ["tickets.id", "tickets.system_id"],
            ondelete="CASCADE",
            name="fk_ticket_transitions_ticket_system",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_ticket_transitions_ticket_created",
        "ticket_transitions",
        ["ticket_id", "created_at"],
        unique=False,
    )

    op.create_table(
        "knowledge_candidates",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("ticket_id", sa.Uuid(), nullable=False),
        sa.Column("system_id", sa.Uuid(), nullable=False),
        sa.Column("answer", sa.Text(), nullable=False),
        sa.Column("author_id", sa.Uuid(), nullable=False),
        sa.Column("reviewer_id", sa.Uuid(), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "pending",
                "approved",
                "rejected",
                name="candidate_status",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("knowledge_source_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("row_version", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["author_id"], ["accounts.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["knowledge_source_id"],
            ["knowledge_sources.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["reviewer_id"],
            ["accounts.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["ticket_id", "system_id"],
            ["tickets.id", "tickets.system_id"],
            ondelete="CASCADE",
            name="fk_knowledge_candidates_ticket_system",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_knowledge_candidates_ticket_status",
        "knowledge_candidates",
        ["ticket_id", "status"],
        unique=False,
    )
    op.create_index(
        "ix_knowledge_candidates_system_updated",
        "knowledge_candidates",
        ["system_id", "updated_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_knowledge_candidates_system_updated",
        table_name="knowledge_candidates",
    )
    op.drop_index(
        "ix_knowledge_candidates_ticket_status",
        table_name="knowledge_candidates",
    )
    op.drop_table("knowledge_candidates")
    op.drop_index(
        "ix_ticket_transitions_ticket_created",
        table_name="ticket_transitions",
    )
    op.drop_table("ticket_transitions")
    op.drop_index(
        "ix_ticket_replies_ticket_created",
        table_name="ticket_replies",
    )
    op.drop_table("ticket_replies")
