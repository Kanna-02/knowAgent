"""create business systems and owner roles

Revision ID: baaf88cba66a
Revises: 3f5d51a53981
Create Date: 2026-08-02 13:24:26.893971
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "baaf88cba66a"
down_revision: str | Sequence[str] | None = "3f5d51a53981"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "business_systems",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "ACTIVE",
                "DISABLED",
                name="business_system_status",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
    )
    op.create_index(
        "ix_business_systems_status_code",
        "business_systems",
        ["status", "code"],
        unique=False,
    )
    op.create_table(
        "account_system_roles",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("system_id", sa.Uuid(), nullable=False),
        sa.Column(
            "role",
            sa.Enum(
                "SYSTEM_OWNER",
                name="system_role",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["system_id"], ["business_systems.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "account_id",
            "system_id",
            "role",
            name="uq_account_system_roles_assignment",
        ),
    )
    op.create_index(
        "ix_account_system_roles_system_role",
        "account_system_roles",
        ["system_id", "role"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_account_system_roles_system_role", table_name="account_system_roles")
    op.drop_table("account_system_roles")
    op.drop_index("ix_business_systems_status_code", table_name="business_systems")
    op.drop_table("business_systems")
