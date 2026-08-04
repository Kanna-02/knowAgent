from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from pgvector.sqlalchemy import Vector
from sqlalchemy import Select, String, case, cast, desc, func, literal, select
from sqlalchemy.engine import Row
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from knowagent.common.errors import ProviderUnavailableError
from knowagent.common.lifecycle import PublicationStatus
from knowagent.documents.domain.models import SourceLocator
from knowagent.documents.infrastructure.sqlalchemy_models import (
    DocumentRecord,
    DocumentVersionRecord,
)
from knowagent.knowledge.domain.models import KnowledgeSourceType
from knowagent.knowledge.infrastructure.sqlalchemy_models import (
    KnowledgeChunkRecord,
    KnowledgeSourceRecord,
)
from knowagent.retrieval.domain.models import SearchHit
from knowagent.tickets.infrastructure.sqlalchemy_models import TicketRecord

# SQLAlchemy's dynamic func namespace triggers false positives.
# pylint: disable=not-callable


class PostgresKnowledgeSearch:
    def __init__(self, session: Session) -> None:
        self._session = session

    def search(self, *, system_id: UUID, query: str, limit: int) -> tuple[SearchHit, ...]:
        normalized_query = query.strip()
        self._validate_limit(limit)
        if not normalized_query:
            raise ValueError("query must not be blank")
        similarity: ColumnElement[float] = func.similarity(
            KnowledgeChunkRecord.retrieval_text, normalized_query
        )
        statement = self._base_statement(similarity.label("score")).where(
            KnowledgeChunkRecord.system_id == system_id,
            KnowledgeChunkRecord.publish_status == PublicationStatus.PUBLISHED,
            KnowledgeSourceRecord.publish_status == PublicationStatus.PUBLISHED,
            similarity > 0,
        )
        statement = statement.order_by(desc(similarity), KnowledgeChunkRecord.id).limit(limit)
        return self._to_hits(self._session.execute(statement).all())

    def search_vectors(
        self,
        *,
        system_id: UUID,
        vector: tuple[float, ...],
        model: str,
        model_version: str,
        limit: int,
    ) -> tuple[SearchHit, ...]:
        self._validate_limit(limit)
        if not vector:
            raise ValueError("vector must not be empty")
        if not model.strip() or not model_version.strip():
            raise ValueError("vector model metadata must not be blank")
        distance: ColumnElement[float] = cast(
            KnowledgeChunkRecord.embedding, Vector()
        ).cosine_distance(list(vector))
        score: ColumnElement[float] = (1.0 - distance).label("score")
        statement = self._base_statement(score).where(
            KnowledgeChunkRecord.system_id == system_id,
            KnowledgeChunkRecord.publish_status == PublicationStatus.PUBLISHED,
            KnowledgeSourceRecord.publish_status == PublicationStatus.PUBLISHED,
            KnowledgeChunkRecord.embedding.is_not(None),
            KnowledgeChunkRecord.embedding_model == model,
            KnowledgeChunkRecord.embedding_model_version == model_version,
        )
        statement = statement.order_by(distance, KnowledgeChunkRecord.id).limit(limit)
        try:
            rows = self._session.execute(statement).all()
        except SQLAlchemyError as error:
            self._session.rollback()
            raise ProviderUnavailableError("vector_search") from error
        return self._to_hits(rows)

    @staticmethod
    def _base_statement(
        score: ColumnElement[float],
    ) -> Select[tuple[KnowledgeChunkRecord, str, str, float]]:
        source_name = case(
            (
                KnowledgeSourceRecord.source_type == KnowledgeSourceType.TICKET,
                literal("工单：") + TicketRecord.title,
            ),
            else_=DocumentRecord.name,
        )
        source_version = case(
            (
                KnowledgeSourceRecord.source_type == KnowledgeSourceType.TICKET,
                cast(TicketRecord.id, String),
            ),
            else_=cast(DocumentVersionRecord.version_no, String),
        )
        return (
            select(
                KnowledgeChunkRecord,
                source_name.label("source_name"),
                source_version.label("source_version"),
                score,
            )
            .join(
                KnowledgeSourceRecord,
                (KnowledgeSourceRecord.id == KnowledgeChunkRecord.source_id)
                & (KnowledgeSourceRecord.system_id == KnowledgeChunkRecord.system_id),
            )
            .outerjoin(
                DocumentVersionRecord,
                (DocumentVersionRecord.id == KnowledgeSourceRecord.document_version_id)
                & (DocumentVersionRecord.system_id == KnowledgeSourceRecord.system_id),
            )
            .outerjoin(
                DocumentRecord,
                (DocumentRecord.id == DocumentVersionRecord.document_id)
                & (DocumentRecord.system_id == DocumentVersionRecord.system_id),
            )
            .outerjoin(
                TicketRecord,
                (TicketRecord.id == KnowledgeSourceRecord.ticket_id)
                & (TicketRecord.system_id == KnowledgeSourceRecord.system_id),
            )
        )

    @staticmethod
    def _to_hits(
        rows: Sequence[Row[tuple[KnowledgeChunkRecord, str, str, float]]],
    ) -> tuple[SearchHit, ...]:
        hits: list[SearchHit] = []
        for chunk, source_name, source_version, score in rows:
            hits.append(
                SearchHit(
                    chunk_id=chunk.id,
                    source_id=chunk.source_id,
                    text=chunk.text,
                    locators=tuple(
                        SourceLocator.model_validate(locator) for locator in chunk.locators
                    ),
                    source_name=source_name,
                    source_version=str(source_version),
                    score=score,
                )
            )
        return tuple(hits)

    @staticmethod
    def _validate_limit(limit: int) -> None:
        if not 1 <= limit <= 100:
            raise ValueError("limit must be between 1 and 100")
