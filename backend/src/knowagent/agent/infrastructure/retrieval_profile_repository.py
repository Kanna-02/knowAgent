from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from knowagent.agent.domain.conversation import RetrievalProfile
from knowagent.agent.infrastructure.sqlalchemy_models import RetrievalProfileRecord
from knowagent.common.errors import ConflictError, NotFoundError


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


class RetrievalProfileRepository:  # pylint: disable=too-few-public-methods
    """Loads versioned retrieval profiles from the database.

    ``get_active(name)`` returns the active row for a profile name. Callers
    pass the resolved ``RetrievalProfile`` into ``BasicRetrievalService``
    instead of the process-wide ``RetrievalSettings`` defaults, enabling
    per-request profile switching and version rollback.
    """

    def __init__(self, session: Session) -> None:
        self._session = session

    def get_active(self, name: str) -> RetrievalProfile | None:
        record = self._session.scalar(
            select(RetrievalProfileRecord).where(
                RetrievalProfileRecord.name == name,
                RetrievalProfileRecord.is_active.is_(True),
            )
        )
        if record is None:
            return None
        return self._to_domain(record)

    def list_page(
        self,
        *,
        name: str | None,
        page: int,
        page_size: int,
    ) -> tuple[tuple[RetrievalProfile, ...], int]:
        if page <= 0 or page_size <= 0:
            raise ValueError("retrieval profile pagination parameters must be positive")
        conditions = []
        if name is not None:
            conditions.append(RetrievalProfileRecord.name == name)
        total = self._session.scalar(
            select(func.count()).select_from(RetrievalProfileRecord).where(*conditions)
        )
        records = self._session.scalars(
            select(RetrievalProfileRecord)
            .where(*conditions)
            .order_by(RetrievalProfileRecord.created_at.desc(), RetrievalProfileRecord.version)
            .limit(page_size)
            .offset((page - 1) * page_size)
        ).all()
        return tuple(self._to_domain(record) for record in records), int(total or 0)

    def get_version(self, name: str, version: str) -> RetrievalProfile | None:
        record = self._session.scalar(
            select(RetrievalProfileRecord).where(
                RetrievalProfileRecord.name == name,
                RetrievalProfileRecord.version == version,
            )
        )
        if record is None:
            return None
        return self._to_domain(record)

    def save(self, profile: RetrievalProfile) -> RetrievalProfile:
        existing = self._session.scalar(
            select(RetrievalProfileRecord).where(
                RetrievalProfileRecord.name == profile.name,
                RetrievalProfileRecord.version == profile.version,
            )
        )
        if existing is not None:
            raise ConflictError("RETRIEVAL_PROFILE_EXISTS", "检索配置版本已存在")
        record = RetrievalProfileRecord(
            id=uuid4(),
            name=profile.name,
            version=profile.version,
            keyword_top_k=profile.keyword_top_k,
            vector_top_k=profile.vector_top_k,
            result_top_k=profile.result_top_k,
            rrf_k=profile.rrf_k,
            keyword_weight=profile.keyword_weight,
            vector_weight=profile.vector_weight,
            rerank_candidate_top_k=profile.rerank_candidate_top_k,
            rerank_top_k=profile.rerank_top_k,
            evidence_max_items=profile.evidence_max_items,
            evidence_max_characters=profile.evidence_max_characters,
            is_active=bool(profile.is_active),
            created_at=profile.created_at,
            change_note=profile.change_note,
        )
        with self._session.begin_nested():
            self._session.add(record)
            self._session.flush()
        return self._to_domain(record)

    def activate(self, name: str, version: str) -> RetrievalProfile:
        with self._session.begin_nested():
            rows = self._session.scalars(
                select(RetrievalProfileRecord)
                .where(RetrievalProfileRecord.name == name)
                .with_for_update()
            ).all()
            activated = next((row for row in rows if row.version == version), None)
            if activated is None:
                raise NotFoundError("RETRIEVAL_PROFILE_NOT_FOUND", "检索配置版本不存在")
            for row in rows:
                if row is not activated:
                    row.is_active = False
            self._session.flush()
            activated.is_active = True
            self._session.flush()
        return self._to_domain(activated)

    @staticmethod
    def _to_domain(record: RetrievalProfileRecord) -> RetrievalProfile:
        return RetrievalProfile(
            name=record.name,
            version=record.version,
            keyword_top_k=record.keyword_top_k,
            vector_top_k=record.vector_top_k,
            result_top_k=record.result_top_k,
            rrf_k=record.rrf_k,
            keyword_weight=record.keyword_weight,
            vector_weight=record.vector_weight,
            rerank_candidate_top_k=record.rerank_candidate_top_k,
            rerank_top_k=record.rerank_top_k,
            evidence_max_items=record.evidence_max_items,
            evidence_max_characters=record.evidence_max_characters,
            is_active=bool(record.is_active),
            created_at=_aware(record.created_at),
            change_note=record.change_note,
        )
