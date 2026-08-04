from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from knowagent.agent.domain.models import (
    AnswerSnapshot,
    CitationSnapshot,
    VerifiedAnswer,
    VerifiedClaim,
)
from knowagent.agent.infrastructure.sqlalchemy_models import AnswerCitationRecord, AnswerRecord
from knowagent.documents.domain.models import SourceLocator


class SqlAlchemyAnswerSnapshotRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add_or_get(self, snapshot: AnswerSnapshot) -> AnswerSnapshot:
        try:
            with self._session.begin_nested():
                self._add(snapshot)
        except IntegrityError:
            existing = self.get_by_run(system_id=snapshot.system_id, run_id=snapshot.run_id)
            if existing is None:
                raise
            return existing
        return snapshot

    def _add(self, snapshot: AnswerSnapshot) -> None:
        self._session.add(
            AnswerRecord(
                id=snapshot.id,
                run_id=snapshot.run_id,
                system_id=snapshot.system_id,
                text=snapshot.answer.text,
                claims=[
                    {
                        "rank": claim.rank,
                        "text": claim.text,
                        "citation_ranks": list(claim.citation_ranks),
                    }
                    for claim in snapshot.answer.claims
                ],
                degraded_reasons=list(snapshot.degraded_reasons),
                model=snapshot.answer.model,
                prompt_version=snapshot.answer.prompt_version,
                created_at=snapshot.created_at,
                updated_at=snapshot.created_at,
            )
        )
        for citation in snapshot.answer.citations:
            self._session.add(
                AnswerCitationRecord(
                    answer_id=snapshot.id,
                    system_id=snapshot.system_id,
                    rank=citation.rank,
                    claim_rank=citation.claim_rank,
                    chunk_id=citation.chunk_id,
                    source_id=citation.source_id,
                    source_name=citation.source_name,
                    source_version=citation.source_version,
                    quoted_text=citation.quoted_text,
                    locators=[locator.model_dump(mode="json") for locator in citation.locators],
                    created_at=snapshot.created_at,
                    updated_at=snapshot.created_at,
                )
            )
        self._session.flush()

    def get_by_run(self, *, system_id: UUID, run_id: UUID) -> AnswerSnapshot | None:
        answer = self._session.scalar(
            select(AnswerRecord).where(
                AnswerRecord.system_id == system_id,
                AnswerRecord.run_id == run_id,
            )
        )
        if answer is None:
            return None
        citations = self._session.scalars(
            select(AnswerCitationRecord)
            .where(
                AnswerCitationRecord.answer_id == answer.id,
                AnswerCitationRecord.system_id == system_id,
            )
            .order_by(AnswerCitationRecord.rank)
        ).all()
        return AnswerSnapshot(
            id=answer.id,
            run_id=answer.run_id,
            system_id=answer.system_id,
            answer=VerifiedAnswer(
                text=answer.text,
                claims=tuple(self._to_claim(claim) for claim in answer.claims),
                citations=tuple(self._to_citation(citation) for citation in citations),
                model=answer.model,
                prompt_version=answer.prompt_version,
            ),
            degraded_reasons=tuple(answer.degraded_reasons),
            created_at=_aware(answer.created_at),
        )

    @staticmethod
    def _to_citation(record: AnswerCitationRecord) -> CitationSnapshot:
        return CitationSnapshot(
            rank=record.rank,
            claim_rank=record.claim_rank,
            chunk_id=record.chunk_id,
            source_id=record.source_id,
            source_name=record.source_name,
            source_version=record.source_version,
            quoted_text=record.quoted_text,
            locators=tuple(SourceLocator.model_validate(locator) for locator in record.locators),
        )

    @staticmethod
    def _to_claim(payload: dict[str, object]) -> VerifiedClaim:
        rank = payload.get("rank")
        text = payload.get("text")
        citation_ranks = payload.get("citation_ranks")
        if not isinstance(rank, int) or not isinstance(text, str):
            raise ValueError("stored answer claim is invalid")
        if not isinstance(citation_ranks, list) or any(
            not isinstance(citation_rank, int) for citation_rank in citation_ranks
        ):
            raise ValueError("stored answer citation ranks are invalid")
        return VerifiedClaim(
            rank=rank,
            text=text,
            citation_ranks=tuple(citation_ranks),
        )


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)
