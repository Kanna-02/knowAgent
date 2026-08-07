"""record retrieval profile on question runs

Revision ID: f6b2c4d8e901
Revises: a3f7d2e9b61c
Create Date: 2026-08-07 08:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f6b2c4d8e901"
down_revision: str | Sequence[str] | None = "a3f7d2e9b61c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("evidence_decisions") as batch_op:
        batch_op.add_column(
            sa.Column("retrieval_profile_name", sa.String(length=64), nullable=True)
        )
        batch_op.add_column(
            sa.Column("retrieval_profile_version", sa.String(length=100), nullable=True)
        )
        batch_op.create_check_constraint(
            "ck_evidence_decisions_retrieval_profile_pair",
            "(retrieval_profile_name IS NULL) = (retrieval_profile_version IS NULL)",
        )


def downgrade() -> None:
    with op.batch_alter_table("evidence_decisions") as batch_op:
        batch_op.drop_constraint(
            "ck_evidence_decisions_retrieval_profile_pair",
            type_="check",
        )
        batch_op.drop_column("retrieval_profile_version")
        batch_op.drop_column("retrieval_profile_name")
