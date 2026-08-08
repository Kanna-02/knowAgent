"""add notification attempt fencing

Revision ID: 8f2c9d4a1b67
Revises: 3bed66d88cf4
Create Date: 2026-08-08 08:10:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "8f2c9d4a1b67"
down_revision: Union[str, Sequence[str], None] = "3bed66d88cf4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "notification_deliveries",
        sa.Column("active_attempt_id", sa.Uuid(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("notification_deliveries", "active_attempt_id")
