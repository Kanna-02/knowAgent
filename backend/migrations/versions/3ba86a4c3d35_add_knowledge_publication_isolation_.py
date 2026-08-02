"""add knowledge publication isolation model

Revision ID: 3ba86a4c3d35
Revises: d1a97d2e451b
Create Date: 2026-08-02 19:10:26.124574
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "3ba86a4c3d35"
down_revision: Union[str, Sequence[str], None] = "d1a97d2e451b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

publication_status = sa.Enum(
    "DRAFT",
    "PUBLISHED",
    "RETIRED",
    name="publication_status",
    native_enum=False,
    create_constraint=True,
    length=32,
)


def upgrade() -> None:
    with op.batch_alter_table("documents") as batch_op:
        batch_op.add_column(sa.Column("current_published_version_id", sa.Uuid(), nullable=True))
        batch_op.create_unique_constraint("uq_documents_id_system", ["id", "system_id"])

    with op.batch_alter_table("document_versions") as batch_op:
        batch_op.add_column(sa.Column("system_id", sa.Uuid(), nullable=True))
        batch_op.add_column(
            sa.Column(
                "publish_status",
                publication_status,
                nullable=False,
                server_default="DRAFT",
            )
        )
        batch_op.add_column(sa.Column("published_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("retired_at", sa.DateTime(timezone=True), nullable=True))

    op.execute(
        sa.text(
            "UPDATE document_versions "
            "SET system_id = ("
            "SELECT documents.system_id FROM documents "
            "WHERE documents.id = document_versions.document_id"
            ")"
        )
    )

    with op.batch_alter_table("document_versions") as batch_op:
        batch_op.alter_column("system_id", existing_type=sa.Uuid(), nullable=False)
        batch_op.alter_column(
            "publish_status",
            existing_type=publication_status,
            server_default=None,
            existing_nullable=False,
        )
        batch_op.create_unique_constraint("uq_document_versions_id_system", ["id", "system_id"])
        batch_op.create_unique_constraint(
            "uq_document_versions_id_document_system",
            ["id", "document_id", "system_id"],
        )
        batch_op.create_foreign_key(
            "fk_document_versions_document_system",
            "documents",
            ["document_id", "system_id"],
            ["id", "system_id"],
            ondelete="CASCADE",
        )
        batch_op.create_index(
            "ix_document_versions_system_publish",
            ["system_id", "publish_status", "updated_at"],
            unique=False,
        )

    with op.batch_alter_table("ingestion_jobs") as batch_op:
        batch_op.add_column(sa.Column("requested_document_id", sa.Uuid(), nullable=True))

    op.create_table(
        "knowledge_sources",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("system_id", sa.Uuid(), nullable=False),
        sa.Column(
            "source_type",
            sa.Enum(
                "DOCUMENT",
                "TICKET",
                name="knowledge_source_type",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("document_version_id", sa.Uuid(), nullable=True),
        sa.Column("ticket_id", sa.Uuid(), nullable=True),
        sa.Column("publish_status", publication_status, nullable=False),
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
        sa.Column("row_version", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "(source_type = 'DOCUMENT' AND document_version_id IS NOT NULL "
            "AND ticket_id IS NULL) OR "
            "(source_type = 'TICKET' AND ticket_id IS NOT NULL "
            "AND document_version_id IS NULL)",
            name="ck_knowledge_sources_reference",
        ),
        sa.ForeignKeyConstraint(
            ["document_version_id", "system_id"],
            ["document_versions.id", "document_versions.system_id"],
            name="fk_knowledge_sources_version_system",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("document_version_id", name="uq_knowledge_sources_document_version"),
        sa.UniqueConstraint("id", "system_id", name="uq_knowledge_sources_id_system"),
    )
    op.create_index(
        "ix_knowledge_sources_system_publish",
        "knowledge_sources",
        ["system_id", "publish_status", "updated_at"],
        unique=False,
    )
    op.create_table(
        "knowledge_chunks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("system_id", sa.Uuid(), nullable=False),
        sa.Column("source_id", sa.Uuid(), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=False),
        sa.Column(
            "structure_path",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column(
            "locators",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("retrieval_text", sa.Text(), nullable=False),
        sa.Column("embedding_model", sa.String(length=255), nullable=True),
        sa.Column("embedding_model_version", sa.String(length=255), nullable=True),
        sa.Column("publish_status", publication_status, nullable=False),
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
        sa.CheckConstraint("ordinal >= 0", name="ck_knowledge_chunks_ordinal"),
        sa.CheckConstraint("token_count > 0", name="ck_knowledge_chunks_token_count"),
        sa.ForeignKeyConstraint(
            ["source_id", "system_id"],
            ["knowledge_sources.id", "knowledge_sources.system_id"],
            name="fk_knowledge_chunks_source_system",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_id", "ordinal", name="uq_knowledge_chunks_source_ordinal"),
    )
    op.create_index(
        "ix_knowledge_chunks_system_publish",
        "knowledge_chunks",
        ["system_id", "publish_status", "source_id"],
        unique=False,
    )

    with op.batch_alter_table("documents") as batch_op:
        batch_op.create_foreign_key(
            "fk_documents_current_published_version",
            "document_versions",
            ["current_published_version_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_foreign_key(
            "fk_documents_current_published_version_scope",
            "document_versions",
            ["current_published_version_id", "id", "system_id"],
            ["id", "document_id", "system_id"],
            deferrable=True,
            initially="DEFERRED",
        )


def downgrade() -> None:
    with op.batch_alter_table("documents") as batch_op:
        batch_op.drop_constraint(
            "fk_documents_current_published_version_scope",
            type_="foreignkey",
        )
        batch_op.drop_constraint("fk_documents_current_published_version", type_="foreignkey")

    op.drop_index("ix_knowledge_chunks_system_publish", table_name="knowledge_chunks")
    op.drop_table("knowledge_chunks")
    op.drop_index("ix_knowledge_sources_system_publish", table_name="knowledge_sources")
    op.drop_table("knowledge_sources")

    with op.batch_alter_table("ingestion_jobs") as batch_op:
        batch_op.drop_column("requested_document_id")

    with op.batch_alter_table("document_versions") as batch_op:
        batch_op.drop_index("ix_document_versions_system_publish")
        batch_op.drop_constraint("fk_document_versions_document_system", type_="foreignkey")
        batch_op.drop_constraint(
            "uq_document_versions_id_document_system",
            type_="unique",
        )
        batch_op.drop_constraint("uq_document_versions_id_system", type_="unique")
        batch_op.drop_constraint("publication_status", type_="check")
        batch_op.drop_column("retired_at")
        batch_op.drop_column("published_at")
        batch_op.drop_column("publish_status")
        batch_op.drop_column("system_id")

    with op.batch_alter_table("documents") as batch_op:
        batch_op.drop_constraint("uq_documents_id_system", type_="unique")
        batch_op.drop_column("current_published_version_id")
