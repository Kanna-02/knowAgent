from __future__ import annotations

import hashlib
import os
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from io import BytesIO
from urllib.parse import urlparse
from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete, select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker

from knowagent.agent.application.answer_generation import (
    AnswerGenerator,
    StreamedAnswerCompleted,
    StreamedAnswerDelta,
)
from knowagent.agent.application.answer_snapshots import AnswerSnapshotService
from knowagent.agent.application.evidence_decision import DeterministicEvidencePolicy
from knowagent.agent.application.reliable_question import ReliableQuestionService
from knowagent.agent.domain.models import (
    CitationSnapshot,
    EvidenceDecisionOutcome,
    QuestionResolutionStatus,
    VerifiedAnswer,
    VerifiedClaim,
)
from knowagent.agent.infrastructure.openai_compatible import OpenAiCompatibleLlmProvider
from knowagent.agent.infrastructure.sqlalchemy_models import (
    AnswerCitationRecord,
    AnswerRecord,
    EvidenceDecisionRecord,
)
from knowagent.agent.infrastructure.sqlalchemy_repository import (
    SqlAlchemyAnswerSnapshotRepository,
)
from knowagent.agent.prompts import load_prompt_definition
from knowagent.common.lifecycle import PublicationStatus
from knowagent.documents.application.chunk_ingestion import ChunkIngestionService
from knowagent.documents.application.processor import ChunkManifest
from knowagent.documents.domain.ingestion import Document, DocumentVersion, DocumentVersionStatus
from knowagent.documents.domain.models import KnowledgeChunk as ParsedKnowledgeChunk
from knowagent.documents.domain.models import (
    SourceLocator,
    SourceType,
)
from knowagent.documents.infrastructure.sqlalchemy_models import DocumentRecord
from knowagent.identity.domain.models import AccountRole, AccountSource, AccountStatus
from knowagent.identity.infrastructure.sqlalchemy_models import AccountRecord
from knowagent.knowledge.application.indexing import KnowledgeIndexService
from knowagent.knowledge.application.publication import KnowledgePublicationService
from knowagent.knowledge.domain.models import KnowledgeChunkDraft
from knowagent.knowledge.infrastructure.sqlalchemy_models import (
    KnowledgeChunkRecord,
    KnowledgeSourceRecord,
)
from knowagent.knowledge.infrastructure.sqlalchemy_repository import (
    SqlAlchemyKnowledgeRepository,
)
from knowagent.platform.database import create_database_engine, create_session_factory
from knowagent.platform.settings import Settings
from knowagent.retrieval.application.evidence import EvidenceOrganizer
from knowagent.retrieval.application.retrieval_service import BasicRetrievalService
from knowagent.retrieval.domain.models import EvidenceBundle, EvidenceItem
from knowagent.retrieval.infrastructure.http_embedding import HttpEmbeddingProvider
from knowagent.retrieval.infrastructure.sqlalchemy_search import PostgresKnowledgeSearch
from knowagent.systems.domain.models import BusinessSystemStatus
from knowagent.systems.infrastructure.sqlalchemy_models import BusinessSystemRecord
from knowagent.tickets.application.refusal import RefusalTicketService
from knowagent.tickets.application.review import KnowledgeReviewService
from knowagent.tickets.application.workflow import TicketWorkflowService
from knowagent.tickets.domain.models import TicketStatus
from knowagent.tickets.infrastructure.sqlalchemy_models import (
    KnowledgeCandidateRecord,
    TicketOccurrenceRecord,
    TicketRecord,
    TicketReplyRecord,
    TicketTransitionRecord,
)
from knowagent.tickets.infrastructure.sqlalchemy_repository import (
    SqlAlchemyTicketRepository,
)

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("KNOWAGENT_RUN_PHASE2_INTEGRATION") != "1",
        reason="set KNOWAGENT_RUN_PHASE2_INTEGRATION=1 to run live Phase 2 integration",
    ),
]

SYSTEM_NAMES = ("Phase 2 Integration System A", "Phase 2 Integration System B")
ACCOUNT_NAMES = (
    "Phase 2 Integration Requester",
    "Phase 2 Integration Owner",
    "Phase 2 Integration Reviewer",
)


@dataclass(slots=True)
class RecordingMetrics:
    degradations: list[tuple[UUID, str, str]] = field(default_factory=list)

    def record_degradation(self, *, system_id: UUID, channel: str, reason: str) -> None:
        self.degradations.append((system_id, channel, reason))


@dataclass(frozen=True, slots=True)
class Participants:
    requester_id: UUID
    owner_id: UUID
    reviewer_id: UUID
    system_a: UUID
    system_b: UUID


class ManifestObjectStore:
    def __init__(self, manifest: ChunkManifest) -> None:
        self._payload = manifest.model_dump_json().encode("utf-8")

    def put(self, *, key: str, content: BytesIO, content_type: str, content_length: int) -> None:
        del key, content, content_type, content_length
        raise AssertionError("manifest store is read-only")

    def get(self, *, key: str) -> bytes:
        assert key == "phase2/chunks-v1.json"
        return self._payload

    def delete(self, *, key: str) -> None:
        del key
        raise AssertionError("manifest store is read-only")


def _require_safe_environment(settings: Settings) -> None:
    database = make_url(settings.database_url).database or ""
    redis_database = urlparse(settings.redis_url).path
    assert settings.environment == "integration"
    assert database == "knowagent_integration"
    assert redis_database == "/15"
    assert settings.retrieval.embedding_base_url == "http://127.0.0.1:8100/v1"
    assert settings.llm.configured


def _cleanup_phase2_records(factory: sessionmaker[Session]) -> None:
    with factory.begin() as session:
        system_ids = tuple(
            session.scalars(
                select(BusinessSystemRecord.id).where(BusinessSystemRecord.name.in_(SYSTEM_NAMES))
            )
        )
        account_ids = tuple(
            session.scalars(
                select(AccountRecord.id).where(AccountRecord.display_name.in_(ACCOUNT_NAMES))
            )
        )
        if system_ids:
            for record in (
                AnswerCitationRecord,
                AnswerRecord,
                KnowledgeCandidateRecord,
                KnowledgeChunkRecord,
                KnowledgeSourceRecord,
                TicketReplyRecord,
                TicketTransitionRecord,
                TicketOccurrenceRecord,
                EvidenceDecisionRecord,
                TicketRecord,
            ):
                session.execute(delete(record).where(record.system_id.in_(system_ids)))
            session.execute(delete(DocumentRecord).where(DocumentRecord.system_id.in_(system_ids)))
            session.execute(
                delete(BusinessSystemRecord).where(BusinessSystemRecord.id.in_(system_ids))
            )
        if account_ids:
            session.execute(delete(AccountRecord).where(AccountRecord.id.in_(account_ids)))


def _phase2_records_exist(factory: sessionmaker[Session]) -> bool:
    with factory() as session:
        system_id = session.scalar(
            select(BusinessSystemRecord.id)
            .where(BusinessSystemRecord.name.in_(SYSTEM_NAMES))
            .limit(1)
        )
        account_id = session.scalar(
            select(AccountRecord.id).where(AccountRecord.display_name.in_(ACCOUNT_NAMES)).limit(1)
        )
    return system_id is not None or account_id is not None


def _seed_participants(factory: sessionmaker[Session], run_id: str) -> Participants:
    requester_id, owner_id, reviewer_id = uuid4(), uuid4(), uuid4()
    system_a, system_b = uuid4(), uuid4()
    account_rows = (
        (requester_id, f"phase2.requester.{run_id}", ACCOUNT_NAMES[0], AccountRole.USER),
        (owner_id, f"phase2.owner.{run_id}", ACCOUNT_NAMES[1], AccountRole.SYSTEM_OWNER),
        (reviewer_id, f"phase2.reviewer.{run_id}", ACCOUNT_NAMES[2], AccountRole.ADMIN),
    )
    now = datetime.now(UTC)
    with factory.begin() as session:
        session.add_all(
            AccountRecord(
                id=account_id,
                username=username,
                display_name=display_name,
                password_hash="phase2-integration-no-login",
                role=role,
                source=AccountSource.ADMIN_CREATED,
                status=AccountStatus.ACTIVE,
                must_change_password=False,
                session_version=1,
                created_at=now,
                updated_at=now,
            )
            for account_id, username, display_name, role in account_rows
        )
        session.add_all(
            (
                BusinessSystemRecord(
                    id=system_a,
                    code=f"P2A{run_id}",
                    name=SYSTEM_NAMES[0],
                    description="Phase 2 live integration A",
                    status=BusinessSystemStatus.ACTIVE,
                    created_at=now,
                    updated_at=now,
                ),
                BusinessSystemRecord(
                    id=system_b,
                    code=f"P2B{run_id}",
                    name=SYSTEM_NAMES[1],
                    description="Phase 2 live integration B",
                    status=BusinessSystemStatus.ACTIVE,
                    created_at=now,
                    updated_at=now,
                ),
            )
        )
    return Participants(requester_id, owner_id, reviewer_id, system_a, system_b)


def _embedding_provider(settings: Settings) -> HttpEmbeddingProvider:
    return HttpEmbeddingProvider(
        base_url=settings.retrieval.embedding_base_url,
        model=settings.retrieval.embedding_model,
        timeout_seconds=settings.retrieval.embedding_timeout_seconds,
    )


async def _seed_document_knowledge(  # pylint: disable=too-many-arguments,too-many-locals
    factory: sessionmaker[Session],
    *,
    embeddings: HttpEmbeddingProvider,
    system_id: UUID,
    actor_id: UUID,
    run_id: str,
    suffix: str,
    text: str,
) -> tuple[UUID, UUID]:
    now = datetime.now(UTC)
    document_id, version_id = uuid4(), uuid4()
    with factory.begin() as session:
        repository = SqlAlchemyKnowledgeRepository(session)
        repository.add_document(
            Document(
                id=document_id,
                system_id=system_id,
                name=f"Phase 2 {suffix} guide",
                created_by=actor_id,
                created_at=now,
                updated_at=now,
            )
        )
        repository.add_version(
            DocumentVersion(
                id=version_id,
                document_id=document_id,
                system_id=system_id,
                version_no=1,
                object_key=f"phase2/{run_id}/{suffix}.md",
                filename=f"{suffix}.md",
                media_type="text/markdown",
                size_bytes=len(text.encode()),
                sha256=hashlib.sha256(text.encode()).hexdigest(),
                status=DocumentVersionStatus.READY_DRAFT,
                publish_status=PublicationStatus.DRAFT,
                created_by=actor_id,
                created_at=now,
                updated_at=now,
            )
        )
    locator = SourceLocator(
        document_id=document_id,
        document_version_id=version_id,
        source_type=SourceType.MARKDOWN,
        block_index=0,
        heading_path=("Phase 2 Integration",),
        paragraph_start=1,
        paragraph_end=1,
        line_start=1,
        line_end=1,
    )
    publication = KnowledgePublicationService(factory)
    publication.replace_draft_chunks(
        system_id=system_id,
        document_version_id=version_id,
        chunks=(
            KnowledgeChunkDraft(
                ordinal=0,
                text=text,
                retrieval_text=text,
                token_count=max(1, len(text) // 2),
                structure_path=("Phase 2 Integration",),
                locators=(locator,),
            ),
        ),
        now=now,
    )
    with factory() as session:
        source = SqlAlchemyKnowledgeRepository(session).get_source_by_version(
            system_id=system_id,
            document_version_id=version_id,
        )
        assert source is not None
        source_id = source.id
    summary = await KnowledgeIndexService(
        factory,
        embeddings=embeddings,
        batch_size=2,
    ).index_source(system_id=system_id, source_id=source_id, now=datetime.now(UTC))
    assert summary.dimension == 1024
    publication.publish(
        system_id=system_id,
        document_version_id=version_id,
        now=datetime.now(UTC),
    )
    return version_id, source_id


def _retrieval_service(
    settings: Settings,
    *,
    session: Session,
    embeddings: HttpEmbeddingProvider,
    metrics: RecordingMetrics,
) -> BasicRetrievalService:
    search = PostgresKnowledgeSearch(session)
    return BasicRetrievalService(
        embeddings=embeddings,
        lexical=search,
        vectors=search,
        keyword_top_k=settings.retrieval.keyword_top_k,
        vector_top_k=settings.retrieval.vector_top_k,
        result_top_k=settings.retrieval.result_top_k,
        rrf_k=settings.retrieval.rrf_k,
        metrics=metrics,
    )


def _question_service(
    settings: Settings,
    *,
    session: Session,
    embeddings: HttpEmbeddingProvider,
    metrics: RecordingMetrics,
) -> ReliableQuestionService:
    ticket_repository = SqlAlchemyTicketRepository(session)
    prompt = load_prompt_definition(settings.llm.prompt_version)
    llm = OpenAiCompatibleLlmProvider(
        base_url=settings.llm.base_url,
        api_key=settings.llm.api_key,
        model=settings.llm.model,
        timeout_seconds=settings.llm.timeout_seconds,
        prompt=prompt,
    )
    return ReliableQuestionService(
        retrieval=_retrieval_service(
            settings,
            session=session,
            embeddings=embeddings,
            metrics=metrics,
        ),
        evidence=EvidenceOrganizer(
            max_items=settings.retrieval.evidence_max_items,
            max_characters=settings.retrieval.evidence_max_characters,
        ),
        policy=DeterministicEvidencePolicy(
            policy_version=settings.evidence_policy.policy_version,
            minimum_fused_score=settings.evidence_policy.minimum_fused_score,
            minimum_score_gap=settings.evidence_policy.minimum_score_gap,
            degraded_score_multiplier=settings.evidence_policy.degraded_score_multiplier,
        ),
        answers=AnswerGenerator(llm),
        recorder=RefusalTicketService(
            repository=ticket_repository,
            deduplication_window=timedelta(hours=settings.tickets.deduplication_window_hours),
        ),
        snapshots=AnswerSnapshotService(repository=SqlAlchemyAnswerSnapshotRepository(session)),
        clock=lambda: datetime.now(UTC),
    )


def test_phase2_live_document_chunk_ingestion_indexes_embeddings() -> None:
    settings = Settings.from_environment()
    _require_safe_environment(settings)
    factory = create_session_factory(create_database_engine(settings.database_url))
    _cleanup_phase2_records(factory)
    run_id = uuid4().hex[:8]
    participants = _seed_participants(factory, run_id)
    document_id, version_id = uuid4(), uuid4()
    now = datetime.now(UTC)
    locator = SourceLocator(
        document_id=document_id,
        document_version_id=version_id,
        source_type=SourceType.MARKDOWN,
        block_index=0,
        heading_path=("Phase 2",),
        paragraph_start=1,
        paragraph_end=1,
        line_start=1,
        line_end=1,
    )
    manifest = ChunkManifest(
        document_id=document_id,
        document_version_id=version_id,
        source_type=SourceType.MARKDOWN,
        parser_name="phase2-live",
        parser_version="1",
        schema_version="chunks-v1",
        chunks=(
            ParsedKnowledgeChunk(
                ordinal=0,
                text=f"PHASE2-WORKER-{run_id} 发布前必须执行数据库迁移。",
                token_count=12,
                structure_path=("Phase 2",),
                locators=(locator,),
            ),
        ),
    )
    completed = False
    try:
        with factory.begin() as session:
            repository = SqlAlchemyKnowledgeRepository(session)
            repository.add_document(
                Document(
                    id=document_id,
                    system_id=participants.system_a,
                    name="Phase 2 worker integration",
                    created_by=participants.owner_id,
                    created_at=now,
                    updated_at=now,
                )
            )
            repository.add_version(
                DocumentVersion(
                    id=version_id,
                    document_id=document_id,
                    system_id=participants.system_a,
                    version_no=1,
                    object_key="phase2/worker.md",
                    filename="worker.md",
                    media_type="text/markdown",
                    size_bytes=64,
                    sha256=hashlib.sha256(b"phase2-worker").hexdigest(),
                    status=DocumentVersionStatus.CHUNKED,
                    created_by=participants.owner_id,
                    created_at=now,
                    updated_at=now,
                )
            )

        source_id, chunk_count = ChunkIngestionService(
            factory,
            object_store=ManifestObjectStore(manifest),
            embeddings=_embedding_provider(settings),
            embedding_batch_size=settings.retrieval.embedding_batch_size,
        ).ingest_chunks(
            system_id=participants.system_a,
            document_version_id=version_id,
            manifest_key="phase2/chunks-v1.json",
            now=now,
        )

        with factory() as session:
            repository = SqlAlchemyKnowledgeRepository(session)
            version = repository.get_version(
                system_id=participants.system_a,
                document_version_id=version_id,
            )
            chunks = repository.list_source_chunks(
                system_id=participants.system_a,
                source_id=source_id,
            )
        assert version is not None and version.status is DocumentVersionStatus.READY_DRAFT
        assert chunk_count == 1
        assert len(chunks) == 1
        assert chunks[0].embedding is not None and len(chunks[0].embedding) == 1024
        completed = True
    finally:
        if completed:
            _cleanup_phase2_records(factory)

    assert completed


@pytest.mark.anyio
@pytest.mark.skipif(
    os.getenv("KNOWAGENT_RUN_PHASE2_LLM_INTEGRATION") != "1",
    reason="set KNOWAGENT_RUN_PHASE2_LLM_INTEGRATION=1 to call the configured Qwen API",
)
async def test_phase2_live_qwen_grounded_answer_contract() -> None:
    settings = Settings.from_environment()
    _require_safe_environment(settings)
    locator = SourceLocator(
        source_type=SourceType.TICKET,
        block_index=0,
        ticket_id=uuid4(),
    )
    evidence = EvidenceBundle(
        items=(
            EvidenceItem(
                evidence_id="E1",
                chunk_id=uuid4(),
                source_id=uuid4(),
                quoted_text="ESB连接超时必须设置为30秒。",
                source_name="Phase 2 Qwen integration",
                source_version="1",
                locators=(locator,),
            ),
        ),
        prompt_text=("[E1] Phase 2 Qwen integration (1)\n" "ESB连接超时必须设置为30秒。"),
    )
    provider = OpenAiCompatibleLlmProvider(
        base_url=settings.llm.base_url,
        api_key=settings.llm.api_key,
        model=settings.llm.model,
        timeout_seconds=settings.llm.timeout_seconds,
        prompt=load_prompt_definition(settings.llm.prompt_version),
    )

    events = [
        event
        async for event in AnswerGenerator(provider).generate_stream(
            question="ESB连接超时必须设置为多少秒？",
            evidence=evidence,
        )
    ]
    assert any(isinstance(event, StreamedAnswerDelta) for event in events[:-1])
    assert isinstance(events[-1], StreamedAnswerCompleted)
    answer = events[-1].answer

    assert answer.citations
    assert all(
        citation.quoted_text in evidence.items[0].quoted_text for citation in answer.citations
    )
    assert answer.model == settings.llm.model


@pytest.mark.anyio
async def test_phase2_live_question_ticket_review_round_trip() -> (  # pylint: disable=too-many-locals,too-many-statements
    None
):
    settings = Settings.from_environment()
    _require_safe_environment(settings)
    factory = create_session_factory(create_database_engine(settings.database_url))
    _cleanup_phase2_records(factory)
    run_id = uuid4().hex[:8]
    participants = _seed_participants(factory, run_id)
    embeddings = _embedding_provider(settings)
    marker_a = f"PHASE2-A-{run_id}"
    marker_b = f"PHASE2-B-{run_id}"
    ticket_marker = f"PHASE2-TICKET-{run_id}"
    version_a: UUID | None = None
    completed = False

    try:
        version_a, _ = await _seed_document_knowledge(
            factory,
            embeddings=embeddings,
            system_id=participants.system_a,
            actor_id=participants.owner_id,
            run_id=run_id,
            suffix="a",
            text=f"{marker_a} ESB连接超时必须设置为30秒。",
        )
        await _seed_document_knowledge(
            factory,
            embeddings=embeddings,
            system_id=participants.system_b,
            actor_id=participants.owner_id,
            run_id=run_id,
            suffix="b",
            text=f"{marker_b} ESB连接超时必须设置为90秒。",
        )

        metrics = RecordingMetrics()
        answer_run_id = uuid4()
        with factory() as session:
            retrieval = _retrieval_service(
                settings,
                session=session,
                embeddings=embeddings,
                metrics=metrics,
            )
            hits_a = await retrieval.retrieve(
                system_id=participants.system_a,
                query="ESB连接超时必须设置为多少秒？",
            )
            hits_b = await retrieval.retrieve(
                system_id=participants.system_b,
                query="ESB连接超时必须设置为多少秒？",
            )
            assert hits_a.hits and hits_b.hits
            assert all(marker_b not in hit.text for hit in hits_a.hits)
            assert all(marker_a not in hit.text for hit in hits_b.hits)
            decision = DeterministicEvidencePolicy(
                policy_version=settings.evidence_policy.policy_version,
                minimum_fused_score=settings.evidence_policy.minimum_fused_score,
                minimum_score_gap=settings.evidence_policy.minimum_score_gap,
                degraded_score_multiplier=settings.evidence_policy.degraded_score_multiplier,
            ).decide(
                run_id=answer_run_id,
                system_id=participants.system_a,
                retrieval=hits_a,
                decided_at=datetime.now(UTC),
                required_terms=("30秒",),
            )
            assert decision.outcome is EvidenceDecisionOutcome.SUFFICIENT
            ticket_repository = SqlAlchemyTicketRepository(session)
            RefusalTicketService(
                repository=ticket_repository,
                deduplication_window=timedelta(hours=settings.tickets.deduplication_window_hours),
            ).record_sufficient(decision=decision)
            first_hit = hits_a.hits[0]
            claim_text = "ESB连接超时必须设置为30秒"
            answer = VerifiedAnswer(
                text=claim_text,
                claims=(VerifiedClaim(rank=1, text=claim_text, citation_ranks=(1,)),),
                citations=(
                    CitationSnapshot(
                        rank=1,
                        claim_rank=1,
                        chunk_id=first_hit.chunk_id,
                        source_id=first_hit.source_id,
                        source_name=first_hit.source_name,
                        source_version=first_hit.source_version,
                        quoted_text=first_hit.text,
                        locators=first_hit.locators,
                    ),
                ),
                model="phase2-integration-extractive",
                prompt_version=settings.llm.prompt_version,
            )
            AnswerSnapshotService(repository=SqlAlchemyAnswerSnapshotRepository(session)).record(
                decision=decision,
                answer=answer,
                degraded_reasons=hits_a.degraded_reasons,
                now=datetime.now(UTC),
            )
            session.commit()

        assert version_a is not None
        KnowledgePublicationService(factory).retire(
            system_id=participants.system_a,
            document_version_id=version_a,
            now=datetime.now(UTC),
        )
        with factory() as session:
            snapshot = AnswerSnapshotService(
                repository=SqlAlchemyAnswerSnapshotRepository(session)
            ).get_by_run(system_id=participants.system_a, run_id=answer_run_id)
            assert snapshot is not None
            assert snapshot.answer.citations
            assert marker_a in snapshot.answer.citations[0].quoted_text

        refusal_question = f"量子香蕉协议 {run_id} 的火星参数是什么？"
        first_refusal_run, second_refusal_run = uuid4(), uuid4()
        with factory() as session:
            questions = _question_service(
                settings,
                session=session,
                embeddings=embeddings,
                metrics=metrics,
            )
            first_refusal = await questions.resolve(
                run_id=first_refusal_run,
                requester_id=participants.requester_id,
                system_id=participants.system_a,
                question=refusal_question,
                required_terms=(f"MISSING-{run_id}",),
            )
            second_refusal = await questions.resolve(
                run_id=second_refusal_run,
                requester_id=participants.requester_id,
                system_id=participants.system_a,
                question=refusal_question,
                required_terms=(f"MISSING-{run_id}",),
            )
            assert first_refusal.status is QuestionResolutionStatus.REFUSED
            assert second_refusal.status is QuestionResolutionStatus.REFUSED
            assert first_refusal.ticket_id == second_refusal.ticket_id
            assert first_refusal.ticket_id is not None
            repository = SqlAlchemyTicketRepository(session)
            ticket = repository.get_ticket(ticket_id=first_refusal.ticket_id)
            assert ticket is not None and ticket.occurrence_count == 2

            workflow = TicketWorkflowService(repository=repository)
            workflow.assign(
                ticket_id=ticket.id,
                assignee_id=participants.owner_id,
                actor_id=participants.reviewer_id,
                now=datetime.now(UTC),
            )
            workflow.start(
                ticket_id=ticket.id,
                actor_id=participants.owner_id,
                now=datetime.now(UTC),
            )
            workflow.reply(
                ticket_id=ticket.id,
                author_id=participants.requester_id,
                body="补充：需要确认火星参数。",
                now=datetime.now(UTC),
            )
            workflow.reply(
                ticket_id=ticket.id,
                author_id=participants.owner_id,
                body="已确认，提交审核。",
                transition_to=TicketStatus.RESOLVED,
                action="resolve",
                now=datetime.now(UTC),
            )
            workflow.close(
                ticket_id=ticket.id,
                actor_id=participants.reviewer_id,
                now=datetime.now(UTC),
            )
            workflow.reopen(
                ticket_id=ticket.id,
                actor_id=participants.requester_id,
                now=datetime.now(UTC),
            )
            workflow.assign(
                ticket_id=ticket.id,
                assignee_id=participants.owner_id,
                actor_id=participants.reviewer_id,
                now=datetime.now(UTC),
            )
            workflow.start(
                ticket_id=ticket.id,
                actor_id=participants.owner_id,
                now=datetime.now(UTC),
            )

            review = KnowledgeReviewService(repository=repository, embeddings=embeddings)
            candidate = review.submit_answer(
                ticket_id=ticket.id,
                author_id=participants.owner_id,
                answer=f"{ticket_marker} 火星参数必须设置为42。",
                now=datetime.now(UTC),
            )
            search = _retrieval_service(
                settings,
                session=session,
                embeddings=embeddings,
                metrics=metrics,
            )
            before_approval = await search.retrieve(
                system_id=participants.system_a,
                query="火星参数必须设置为多少？",
            )
            assert all(ticket_marker not in hit.text for hit in before_approval.hits)
            started = time.monotonic()
            published = await review.approve(
                candidate_id=candidate.id,
                reviewer_id=participants.reviewer_id,
                now=datetime.now(UTC),
            )
            assert published.knowledge_source_id is not None
            after_approval = await search.retrieve(
                system_id=participants.system_a,
                query="火星参数必须设置为多少？",
            )
            assert time.monotonic() - started < 300
            ticket_hits = [hit for hit in after_approval.hits if ticket_marker in hit.text]
            assert ticket_hits
            assert ticket_hits[0].source_name.startswith("工单：")
            assert ticket_hits[0].locators[0].ticket_id == ticket.id
            cross_system = await search.retrieve(
                system_id=participants.system_b,
                query="火星参数必须设置为多少？",
            )
            assert all(ticket_marker not in hit.text for hit in cross_system.hits)
            workflow.resolve(
                ticket_id=ticket.id,
                actor_id=participants.owner_id,
                now=datetime.now(UTC),
            )
            session.commit()

        assert not metrics.degradations
        completed = True
    finally:
        if completed:
            _cleanup_phase2_records(factory)

    assert completed
    assert not _phase2_records_exist(factory)
