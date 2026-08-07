"""add phase3 conversation, prompt definitions and retrieval profiles

Revision ID: a3f7d2e9b61c
Revises: c1738febb896
Create Date: 2026-08-06 10:00:00.000000
"""

from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import UUID

import sqlalchemy as sa
from alembic import op

revision: str = "a3f7d2e9b61c"
down_revision: str | Sequence[str] | None = "c1738febb896"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "conversations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("system_id", sa.Uuid(), nullable=False),
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["accounts.id"],
            ondelete="CASCADE",
            name="fk_conversations_account",
        ),
        sa.ForeignKeyConstraint(
            ["system_id"],
            ["business_systems.id"],
            ondelete="CASCADE",
            name="fk_conversations_system",
        ),
        sa.UniqueConstraint("id", "system_id", name="uq_conversations_id_system"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_conversations_account_updated",
        "conversations",
        ["account_id", "updated_at"],
    )
    op.create_index(
        "ix_conversations_system_updated",
        "conversations",
        ["system_id", "updated_at"],
    )

    op.create_table(
        "conversation_messages",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("system_id", sa.Uuid(), nullable=False),
        sa.Column("sequence_number", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("intent", sa.String(length=16), nullable=True),
        sa.Column("rewritten_query", sa.Text(), nullable=True),
        sa.Column("rewrite_prompt_version", sa.String(length=100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["conversation_id", "system_id"],
            ["conversations.id", "conversations.system_id"],
            ondelete="CASCADE",
            name="fk_conversation_messages_conversation_system",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_conversation_messages_conversation_sequence",
        "conversation_messages",
        ["conversation_id", "sequence_number"],
        unique=True,
    )

    op.create_table(
        "prompt_definitions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("scenario", sa.String(length=64), nullable=False),
        sa.Column("version", sa.String(length=100), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("change_note", sa.String(length=500), nullable=False),
        sa.UniqueConstraint(
            "scenario",
            "version",
            name="uq_prompt_definitions_scenario_version",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_prompt_definitions_scenario_enabled",
        "prompt_definitions",
        ["scenario", "enabled"],
    )
    op.create_index(
        "uq_prompt_definitions_active_scenario",
        "prompt_definitions",
        ["scenario"],
        unique=True,
        postgresql_where=sa.text("enabled"),
        sqlite_where=sa.text("enabled = 1"),
    )
    prompt_definitions = sa.table(
        "prompt_definitions",
        sa.column("id", sa.Uuid()),
        sa.column("scenario", sa.String()),
        sa.column("version", sa.String()),
        sa.column("content", sa.Text()),
        sa.column("enabled", sa.Boolean()),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("change_note", sa.String()),
    )
    op.bulk_insert(
        prompt_definitions,
        [
            {
                "id": UUID("a3f7d2e9-b61c-4000-8000-000000000001"),
                "scenario": "grounded_answer",
                "version": "grounded-answer-v1",
                "content": (
                    "你是企业知识问答助手。只能使用用户消息中的编号证据回答。"
                    "输出必须是单个 JSON 对象，不得使用 Markdown，格式为："
                    '{"claims":[{"text":"逐字来自证据的完整声明","citations":'
                    '[{"evidence_id":"E1","quote":"包含该声明的证据原文"}]}]}。'
                    "每个 claims[].text 必须逐字出现在对应 quote 中；"
                    "evidence_id 只能引用给出的证据；quote 必须逐字来自对应证据。"
                    "证据不能支持回答时不要生成声明。"
                ),
                "enabled": True,
                "created_at": datetime(2026, 8, 3, tzinfo=UTC),
                "change_note": (
                    "Initial extractive grounded-answer prompt with claim-level citations."
                ),
            },
            {
                "id": UUID("a3f7d2e9-b61c-4000-8000-000000000002"),
                "scenario": "query_rewrite",
                "version": "query-rewrite-v1",
                "content": (
                    "你是问答系统的查询改写助手。将用户的追问改写为独立、完整的检索查询，"
                    "使其脱离对话历史也能被准确检索。只输出改写后的查询，不要解释。"
                ),
                "enabled": True,
                "created_at": datetime(2026, 8, 7, tzinfo=UTC),
                "change_note": "Initial multi-turn follow-up query rewrite prompt.",
            },
        ],
    )

    op.create_table(
        "retrieval_profiles",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("version", sa.String(length=100), nullable=False),
        sa.Column("keyword_top_k", sa.Integer(), nullable=False),
        sa.Column("vector_top_k", sa.Integer(), nullable=False),
        sa.Column("result_top_k", sa.Integer(), nullable=False),
        sa.Column("rrf_k", sa.Integer(), nullable=False),
        sa.Column("keyword_weight", sa.Float(), nullable=False),
        sa.Column("vector_weight", sa.Float(), nullable=False),
        sa.Column("rerank_candidate_top_k", sa.Integer(), nullable=False),
        sa.Column("rerank_top_k", sa.Integer(), nullable=False),
        sa.Column("evidence_max_items", sa.Integer(), nullable=False),
        sa.Column("evidence_max_characters", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("change_note", sa.String(length=500), nullable=False),
        sa.UniqueConstraint("name", "version", name="uq_retrieval_profiles_name_version"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_retrieval_profiles_name_active",
        "retrieval_profiles",
        ["name", "is_active"],
    )
    op.create_index(
        "uq_retrieval_profiles_active_name",
        "retrieval_profiles",
        ["name"],
        unique=True,
        postgresql_where=sa.text("is_active"),
        sqlite_where=sa.text("is_active = 1"),
    )
    retrieval_profiles = sa.table(
        "retrieval_profiles",
        sa.column("id", sa.Uuid()),
        sa.column("name", sa.String()),
        sa.column("version", sa.String()),
        sa.column("keyword_top_k", sa.Integer()),
        sa.column("vector_top_k", sa.Integer()),
        sa.column("result_top_k", sa.Integer()),
        sa.column("rrf_k", sa.Integer()),
        sa.column("keyword_weight", sa.Float()),
        sa.column("vector_weight", sa.Float()),
        sa.column("rerank_candidate_top_k", sa.Integer()),
        sa.column("rerank_top_k", sa.Integer()),
        sa.column("evidence_max_items", sa.Integer()),
        sa.column("evidence_max_characters", sa.Integer()),
        sa.column("is_active", sa.Boolean()),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("change_note", sa.String()),
    )
    op.bulk_insert(
        retrieval_profiles,
        [
            {
                "id": UUID("a3f7d2e9-b61c-4000-8000-000000000003"),
                "name": "default",
                "version": "profile-v1",
                "keyword_top_k": 20,
                "vector_top_k": 20,
                "result_top_k": 10,
                "rrf_k": 60,
                "keyword_weight": 1.0,
                "vector_weight": 1.0,
                "rerank_candidate_top_k": 20,
                "rerank_top_k": 10,
                "evidence_max_items": 6,
                "evidence_max_characters": 12000,
                "is_active": True,
                "created_at": datetime(2026, 8, 7, tzinfo=UTC),
                "change_note": "Initial profile matching the Phase 3 retrieval defaults.",
            }
        ],
    )


def downgrade() -> None:
    op.drop_index("uq_retrieval_profiles_active_name", table_name="retrieval_profiles")
    op.drop_index("ix_retrieval_profiles_name_active", table_name="retrieval_profiles")
    op.drop_table("retrieval_profiles")
    op.drop_index("uq_prompt_definitions_active_scenario", table_name="prompt_definitions")
    op.drop_index("ix_prompt_definitions_scenario_enabled", table_name="prompt_definitions")
    op.drop_table("prompt_definitions")
    op.drop_index(
        "ix_conversation_messages_conversation_sequence",
        table_name="conversation_messages",
    )
    op.drop_table("conversation_messages")
    op.drop_index("ix_conversations_system_updated", table_name="conversations")
    op.drop_index("ix_conversations_account_updated", table_name="conversations")
    op.drop_table("conversations")
