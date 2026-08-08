from __future__ import annotations

import hashlib
from dataclasses import replace
from datetime import UTC, datetime
from typing import cast
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from knowagent.agent.domain.models import (
    EvidenceCandidateSummary,
    EvidenceDecision,
    EvidenceDecisionOutcome,
    EvidenceReasonCode,
)
from knowagent.agent.infrastructure.sqlalchemy_models import EvidenceDecisionRecord
from knowagent.common.errors import NotFoundError
from knowagent.identity.domain.models import AccountRole
from knowagent.identity.infrastructure.sqlalchemy_models import AccountRecord
from knowagent.platform.outbox import SqlAlchemyOutboxWriter
from knowagent.systems.domain.models import SystemRole
from knowagent.systems.infrastructure.sqlalchemy_models import AccountSystemRoleRecord
from knowagent.tickets.domain.models import (
    CandidateStatus,
    KnowledgeCandidate,
    ReplyAuthorRole,
    Ticket,
    TicketOccurrence,
    TicketReply,
    TicketStatus,
    TicketTransition,
)
from knowagent.tickets.infrastructure.sqlalchemy_models import (
    KnowledgeCandidateRecord,
    TicketOccurrenceRecord,
    TicketRecord,
    TicketReplyRecord,
    TicketTransitionRecord,
)

# SQLAlchemy exposes SQL functions dynamically; Pylint cannot infer that call contract.
# pylint: disable=not-callable


class SqlAlchemyTicketRepository:  # pylint: disable=too-many-public-methods
    def __init__(self, session: Session) -> None:
        self._session = session
        self._outbox = SqlAlchemyOutboxWriter(session)

    def get_decision(self, *, run_id: UUID) -> EvidenceDecision | None:
        record = self._session.scalar(
            select(EvidenceDecisionRecord).where(EvidenceDecisionRecord.run_id == run_id)
        )
        return self._to_decision(record) if record is not None else None

    def add_decision(
        self,
        *,
        decision: EvidenceDecision,
        ticket_id: UUID | None,
    ) -> EvidenceDecision:
        record = EvidenceDecisionRecord(
            id=decision.id,
            run_id=decision.run_id,
            system_id=decision.system_id,
            ticket_id=ticket_id,
            query=decision.query,
            normalized_query=decision.normalized_query,
            outcome=decision.outcome,
            reason_codes=[reason.value for reason in decision.reason_codes],
            score=decision.score,
            applied_score_threshold=decision.applied_score_threshold,
            policy_version=decision.policy_version,
            retrieval_profile_name=decision.retrieval_profile_name,
            retrieval_profile_version=decision.retrieval_profile_version,
            candidate_summaries=[
                {
                    "chunk_id": str(candidate.chunk_id),
                    "source_id": str(candidate.source_id),
                    "source_name": candidate.source_name,
                    "source_version": candidate.source_version,
                    "fused_score": candidate.fused_score,
                    "channels": list(candidate.channels),
                }
                for candidate in decision.candidates
            ],
            degraded_reasons=list(decision.degraded_reasons),
            created_at=decision.decided_at,
            updated_at=decision.decided_at,
        )
        self._session.add(record)
        self._session.flush()
        return replace(decision, ticket_id=ticket_id)

    def acquire_run_lock(self, *, run_id: UUID) -> None:
        self._pg_advisory_xact_lock(self._hash_lock_key(b"run", str(run_id).encode("utf-8")))

    def acquire_deduplication_lock(  # pylint: disable=unused-argument
        self,
        *,
        system_id: UUID,
        deduplication_key: str,
    ) -> None:
        self._pg_advisory_xact_lock(
            self._hash_lock_key(
                b"dedup",
                str(system_id).encode("utf-8"),
                deduplication_key.encode("utf-8"),
            )
        )

    def get_ticket(self, *, ticket_id: UUID) -> Ticket | None:
        record = self._session.get(TicketRecord, ticket_id)
        return self._to_ticket(record) if record is not None else None

    def get_ticket_by_deduplication_key(
        self,
        *,
        system_id: UUID,
        deduplication_key: str,
        updated_after: datetime,
    ) -> Ticket | None:
        record = self._session.scalar(
            select(TicketRecord)
            .where(
                TicketRecord.system_id == system_id,
                TicketRecord.deduplication_key == deduplication_key,
                TicketRecord.updated_at >= updated_after,
            )
            .with_for_update()
        )
        return self._to_ticket(record) if record is not None else None

    def add_ticket(self, ticket: Ticket) -> Ticket:
        self._session.add(
            TicketRecord(
                id=ticket.id,
                system_id=ticket.system_id,
                requester_id=ticket.requester_id,
                source_run_id=ticket.source_run_id,
                assignee_id=ticket.assignee_id,
                status=ticket.status,
                priority=ticket.priority,
                title=ticket.title,
                question=ticket.question,
                normalized_question=ticket.normalized_question,
                deduplication_key=ticket.deduplication_key,
                occurrence_count=ticket.occurrence_count,
                created_at=ticket.created_at,
                updated_at=ticket.updated_at,
            )
        )
        self._session.flush()
        self._outbox.publish(
            aggregate_type="ticket",
            aggregate_id=ticket.id,
            event_type="ticket_created",
            payload={
                "ticket_id": str(ticket.id),
                "system_id": str(ticket.system_id),
                "requester_id": str(ticket.requester_id),
                "title": ticket.title,
                "question": ticket.question,
                "created_at": ticket.created_at.isoformat(),
            },
            idempotency_key=f"ticket:{ticket.id}:created",
            occurred_at=ticket.created_at,
        )
        return ticket

    def increment_ticket_occurrence(self, *, ticket_id: UUID, now: datetime) -> Ticket:
        record = self._session.scalar(
            select(TicketRecord).where(TicketRecord.id == ticket_id).with_for_update()
        )
        if record is None:
            raise NotFoundError("TICKET_NOT_FOUND", "工单不存在")
        record.occurrence_count += 1
        record.updated_at = now
        self._session.flush()
        return self._to_ticket(record)

    def get_ticket_occurrence(self, *, run_id: UUID) -> TicketOccurrence | None:
        record = self._session.scalar(
            select(TicketOccurrenceRecord).where(TicketOccurrenceRecord.run_id == run_id)
        )
        return self._to_occurrence(record) if record is not None else None

    def add_ticket_occurrence(self, occurrence: TicketOccurrence) -> TicketOccurrence:
        self._session.add(
            TicketOccurrenceRecord(
                id=occurrence.id,
                ticket_id=occurrence.ticket_id,
                system_id=occurrence.system_id,
                run_id=occurrence.run_id,
                requester_id=occurrence.requester_id,
                question=occurrence.question,
                created_at=occurrence.created_at,
            )
        )
        self._session.flush()
        return occurrence

    def list_ticket_occurrences(self, *, ticket_id: UUID) -> tuple[TicketOccurrence, ...]:
        records = self._session.scalars(
            select(TicketOccurrenceRecord)
            .where(TicketOccurrenceRecord.ticket_id == ticket_id)
            .order_by(TicketOccurrenceRecord.created_at)
        )
        return tuple(self._to_occurrence(record) for record in records)

    def count_tickets(self) -> int:
        return int(self._session.scalar(select(func.count(TicketRecord.id))) or 0)

    def list_tickets_page(
        self,
        *,
        system_ids: list[UUID],
        status: TicketStatus | None,
        page: int,
        page_size: int,
    ) -> tuple[list[Ticket], int]:
        filters: list[ColumnElement[bool]] = []
        if system_ids:
            filters.append(TicketRecord.system_id.in_(system_ids))
        if status is not None:
            filters.append(TicketRecord.status == status)
        count_stmt = select(func.count(TicketRecord.id)).where(*filters)
        total = int(self._session.scalar(count_stmt) or 0)
        records = self._session.scalars(
            select(TicketRecord)
            .where(*filters)
            .order_by(TicketRecord.updated_at.desc(), TicketRecord.id)
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
        tickets = [self._to_ticket(record) for record in records]
        return tickets, total

    # ---- workflow ----

    def lock_ticket(self, *, ticket_id: UUID) -> Ticket | None:
        record = self._session.scalar(
            select(TicketRecord).where(TicketRecord.id == ticket_id).with_for_update()
        )
        return self._to_ticket(record) if record is not None else None

    def update_ticket_status(
        self,
        *,
        ticket_id: UUID,
        status: TicketStatus,
        assignee_id: UUID | None,
        now: datetime,
    ) -> None:
        record = self._session.get(TicketRecord, ticket_id)
        if record is None:
            raise NotFoundError("TICKET_NOT_FOUND", "工单不存在")
        record.status = status
        if assignee_id is not None:
            record.assignee_id = assignee_id
        record.updated_at = now
        self._session.flush()

    def add_reply(self, reply: TicketReply) -> TicketReply:
        self._session.add(
            TicketReplyRecord(
                id=reply.id,
                ticket_id=reply.ticket_id,
                system_id=reply.system_id,
                author_id=reply.author_id,
                author_role=reply.author_role,
                body=reply.body,
                created_at=reply.created_at,
            )
        )
        self._session.flush()
        if self._reply_notifies_requester(reply):
            ticket_record = self._session.get(TicketRecord, reply.ticket_id)
            if ticket_record is None:
                raise NotFoundError("TICKET_NOT_FOUND", "工单不存在")
            self._outbox.publish(
                aggregate_type="ticket",
                aggregate_id=reply.ticket_id,
                event_type="ticket_replied",
                payload={
                    "ticket_id": str(reply.ticket_id),
                    "system_id": str(reply.system_id),
                    "requester_id": str(ticket_record.requester_id),
                    "author_id": str(reply.author_id),
                    "reply_id": str(reply.id),
                    "reply_body": reply.body,
                    "title": ticket_record.title,
                    "question": ticket_record.question,
                    "created_at": reply.created_at.isoformat(),
                },
                idempotency_key=f"ticket:{reply.ticket_id}:reply:{reply.id}",
                occurred_at=reply.created_at,
            )
        return reply

    def _reply_notifies_requester(self, reply: TicketReply) -> bool:
        if reply.author_role is ReplyAuthorRole.REQUESTER:
            return False
        if reply.author_role is ReplyAuthorRole.ASSIGNEE:
            return True
        account_role = self._session.scalar(
            select(AccountRecord.role).where(AccountRecord.id == reply.author_id)
        )
        if account_role is AccountRole.ADMIN:
            return True
        if account_role is not AccountRole.SYSTEM_OWNER:
            return False
        assignment_id = self._session.scalar(
            select(AccountSystemRoleRecord.id).where(
                AccountSystemRoleRecord.account_id == reply.author_id,
                AccountSystemRoleRecord.system_id == reply.system_id,
                AccountSystemRoleRecord.role == SystemRole.SYSTEM_OWNER,
            )
        )
        return assignment_id is not None

    def list_replies(self, *, ticket_id: UUID) -> tuple[TicketReply, ...]:
        records = self._session.scalars(
            select(TicketReplyRecord)
            .where(TicketReplyRecord.ticket_id == ticket_id)
            .order_by(TicketReplyRecord.created_at)
        )
        return tuple(self._to_reply(record) for record in records)

    def add_transition(self, transition: TicketTransition) -> TicketTransition:
        self._session.add(
            TicketTransitionRecord(
                id=transition.id,
                ticket_id=transition.ticket_id,
                system_id=transition.system_id,
                actor_id=transition.actor_id,
                from_status=transition.from_status,
                to_status=transition.to_status,
                action=transition.action,
                created_at=transition.created_at,
            )
        )
        self._session.flush()
        return transition

    def list_transitions(self, *, ticket_id: UUID) -> tuple[TicketTransition, ...]:
        records = self._session.scalars(
            select(TicketTransitionRecord)
            .where(TicketTransitionRecord.ticket_id == ticket_id)
            .order_by(TicketTransitionRecord.created_at)
        )
        return tuple(self._to_transition(record) for record in records)

    def add_candidate(self, candidate: KnowledgeCandidate) -> KnowledgeCandidate:
        self._session.add(
            KnowledgeCandidateRecord(
                id=candidate.id,
                ticket_id=candidate.ticket_id,
                system_id=candidate.system_id,
                answer=candidate.answer,
                author_id=candidate.author_id,
                reviewer_id=candidate.reviewer_id,
                status=candidate.status,
                knowledge_source_id=candidate.knowledge_source_id,
                created_at=candidate.created_at,
                updated_at=candidate.updated_at,
            )
        )
        self._session.flush()
        return candidate

    def get_candidate(self, *, candidate_id: UUID) -> KnowledgeCandidate | None:
        record = self._session.get(KnowledgeCandidateRecord, candidate_id)
        return self._to_candidate(record) if record is not None else None

    def lock_candidate(self, *, candidate_id: UUID) -> KnowledgeCandidate | None:
        record = self._session.scalar(
            select(KnowledgeCandidateRecord)
            .where(KnowledgeCandidateRecord.id == candidate_id)
            .with_for_update()
        )
        return self._to_candidate(record) if record is not None else None

    def get_pending_candidate_by_ticket(self, *, ticket_id: UUID) -> KnowledgeCandidate | None:
        record = self._session.scalar(
            select(KnowledgeCandidateRecord).where(
                KnowledgeCandidateRecord.ticket_id == ticket_id,
                KnowledgeCandidateRecord.status == CandidateStatus.PENDING,
            )
        )
        return self._to_candidate(record) if record is not None else None

    def publish_candidate(
        self,
        *,
        candidate_id: UUID,
        reviewer_id: UUID,
        knowledge_source_id: UUID,
        now: datetime,
    ) -> KnowledgeCandidate:
        record = self._session.get(KnowledgeCandidateRecord, candidate_id)
        if record is None:
            raise NotFoundError("KNOWLEDGE_CANDIDATE_NOT_FOUND", "知识候选不存在")
        record.status = CandidateStatus.PUBLISHED
        record.reviewer_id = reviewer_id
        record.knowledge_source_id = knowledge_source_id
        record.updated_at = now
        self._session.flush()
        return self._to_candidate(record)

    def reject_candidate(
        self,
        *,
        candidate_id: UUID,
        reviewer_id: UUID,
        now: datetime,
    ) -> KnowledgeCandidate:
        record = self._session.get(KnowledgeCandidateRecord, candidate_id)
        if record is None:
            raise NotFoundError("KNOWLEDGE_CANDIDATE_NOT_FOUND", "知识候选不存在")
        record.status = CandidateStatus.REJECTED
        record.reviewer_id = reviewer_id
        record.updated_at = now
        self._session.flush()
        return self._to_candidate(record)

    def create_ticket_knowledge_source(
        self,
        *,
        system_id: UUID,
        ticket_id: UUID,
        now: datetime,
    ) -> UUID:
        # Deferred import: the knowledge ORM module depends on pgvector which
        # is only available in the deployment environment. Keeping this import
        # out of the module top level lets the ticket module and its tests run
        # without pgvector installed.
        # pylint: disable=import-outside-toplevel
        from knowagent.common.lifecycle import PublicationStatus
        from knowagent.knowledge.domain.models import KnowledgeSourceType
        from knowagent.knowledge.infrastructure.sqlalchemy_models import (
            KnowledgeSourceRecord,
        )

        source = KnowledgeSourceRecord(
            system_id=system_id,
            source_type=KnowledgeSourceType.TICKET,
            document_version_id=None,
            ticket_id=ticket_id,
            publish_status=PublicationStatus.PUBLISHED,
            created_at=now,
            updated_at=now,
        )
        self._session.add(source)
        self._session.flush()
        return source.id

    def create_published_chunk(  # pylint: disable=too-many-arguments,too-many-locals
        self,
        *,
        system_id: UUID,
        source_id: UUID,
        text: str,
        embedding_model: str,
        embedding_model_version: str,
        embedding: tuple[float, ...],
        now: datetime,
    ) -> UUID:
        # Deferred import: pgvector is only available in the deployment venv.
        # pylint: disable=import-outside-toplevel
        from knowagent.common.lifecycle import PublicationStatus
        from knowagent.documents.domain.models import SourceLocator, SourceType
        from knowagent.knowledge.infrastructure.sqlalchemy_models import (
            KnowledgeChunkRecord,
            KnowledgeSourceRecord,
        )

        trimmed = text.strip()
        if not trimmed:
            raise ValueError("knowledge chunk text must not be blank")
        source = self._session.get(KnowledgeSourceRecord, source_id)
        if source is None or source.system_id != system_id or source.ticket_id is None:
            raise NotFoundError("KNOWLEDGE_SOURCE_NOT_FOUND", "知识来源不存在")
        locator = SourceLocator(
            source_type=SourceType.TICKET,
            block_index=0,
            ticket_id=source.ticket_id,
        )
        chunk = KnowledgeChunkRecord(
            system_id=system_id,
            source_id=source_id,
            ordinal=0,
            text=trimmed,
            token_count=1,
            structure_path=[],
            locators=[locator.model_dump(mode="json")],
            retrieval_text=trimmed,
            embedding_model=embedding_model,
            embedding_model_version=embedding_model_version,
            embedding=list(embedding),
            publish_status=PublicationStatus.PUBLISHED,
            created_at=now,
            updated_at=now,
        )
        self._session.add(chunk)
        self._session.flush()
        return chunk.id

    @staticmethod
    def _to_reply(record: TicketReplyRecord) -> TicketReply:
        return TicketReply(
            id=record.id,
            ticket_id=record.ticket_id,
            system_id=record.system_id,
            author_id=record.author_id,
            author_role=record.author_role,
            body=record.body,
            created_at=_as_utc(record.created_at),
        )

    @staticmethod
    def _to_transition(record: TicketTransitionRecord) -> TicketTransition:
        return TicketTransition(
            id=record.id,
            ticket_id=record.ticket_id,
            system_id=record.system_id,
            actor_id=record.actor_id,
            from_status=record.from_status,
            to_status=record.to_status,
            action=record.action,
            created_at=_as_utc(record.created_at),
        )

    @staticmethod
    def _to_candidate(record: KnowledgeCandidateRecord) -> KnowledgeCandidate:
        return KnowledgeCandidate(
            id=record.id,
            ticket_id=record.ticket_id,
            system_id=record.system_id,
            answer=record.answer,
            author_id=record.author_id,
            reviewer_id=record.reviewer_id,
            status=record.status,
            knowledge_source_id=record.knowledge_source_id,
            created_at=_as_utc(record.created_at),
            updated_at=_as_utc(record.updated_at),
        )

    def _pg_advisory_xact_lock(self, lock_id: int) -> None:
        bind = self._session.get_bind()
        if bind.dialect.name == "postgresql":
            self._session.execute(select(func.pg_advisory_xact_lock(lock_id)))
        # Non-PostgreSQL dialects (e.g. the in-memory SQLite used in unit tests)
        # have no advisory locks; transactional isolation plus the unique
        # constraints on source_run_id/run_id already serialize concurrent work.

    @staticmethod
    def _hash_lock_key(*parts: bytes) -> int:
        digest = hashlib.sha256(b"|".join(parts)).digest()
        return int.from_bytes(digest[:8], "big", signed=True)

    @staticmethod
    def _to_decision(record: EvidenceDecisionRecord) -> EvidenceDecision:
        candidates = tuple(
            EvidenceCandidateSummary(
                chunk_id=UUID(str(candidate["chunk_id"])),
                source_id=UUID(str(candidate["source_id"])),
                source_name=str(candidate["source_name"]),
                source_version=str(candidate["source_version"]),
                fused_score=float(cast(str | int | float, candidate["fused_score"])),
                channels=tuple(
                    str(channel) for channel in cast(list[object], candidate["channels"])
                ),
            )
            for candidate in record.candidate_summaries
        )
        return EvidenceDecision(
            id=record.id,
            run_id=record.run_id,
            system_id=record.system_id,
            query=record.query,
            normalized_query=record.normalized_query,
            outcome=EvidenceDecisionOutcome(record.outcome),
            reason_codes=tuple(EvidenceReasonCode(code) for code in record.reason_codes),
            score=record.score,
            applied_score_threshold=record.applied_score_threshold,
            policy_version=record.policy_version,
            retrieval_profile_name=record.retrieval_profile_name,
            retrieval_profile_version=record.retrieval_profile_version,
            candidates=candidates,
            degraded_reasons=tuple(record.degraded_reasons),
            decided_at=_as_utc(record.created_at),
            ticket_id=record.ticket_id,
        )

    @staticmethod
    def _to_ticket(record: TicketRecord) -> Ticket:
        return Ticket(
            id=record.id,
            system_id=record.system_id,
            requester_id=record.requester_id,
            source_run_id=record.source_run_id,
            assignee_id=record.assignee_id,
            status=record.status,
            priority=record.priority,
            title=record.title,
            question=record.question,
            normalized_question=record.normalized_question,
            deduplication_key=record.deduplication_key,
            occurrence_count=record.occurrence_count,
            created_at=_as_utc(record.created_at),
            updated_at=_as_utc(record.updated_at),
        )

    @staticmethod
    def _to_occurrence(record: TicketOccurrenceRecord) -> TicketOccurrence:
        return TicketOccurrence(
            id=record.id,
            ticket_id=record.ticket_id,
            system_id=record.system_id,
            run_id=record.run_id,
            requester_id=record.requester_id,
            question=record.question,
            created_at=_as_utc(record.created_at),
        )


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)
