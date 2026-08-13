from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from knowagent.documents.domain.ingestion import (
    IngestionJob,
    IngestionStage,
    IngestionStatus,
)

NOW = datetime(2026, 8, 2, 8, 0, tzinfo=UTC)


def make_job(*, max_attempts: int = 3) -> IngestionJob:
    return IngestionJob.new(
        document_version_id=uuid4(),
        actor_id=uuid4(),
        system_id=uuid4(),
        idempotency_key="upload-001",
        max_attempts=max_attempts,
        now=NOW,
    )


def test_claim_sets_lease_and_advancing_stage_keeps_progress_monotonic() -> None:
    job = make_job()

    claimed = job.claim(owner="worker-1", now=NOW, lease_seconds=120)
    parsing = claimed.advance(IngestionStage.PARSING, progress=25, now=NOW)
    chunking = parsing.advance(IngestionStage.CHUNKING, progress=70, now=NOW)
    completed = chunking.complete(now=NOW)

    assert claimed.status is IngestionStatus.RUNNING
    assert claimed.attempt == 1
    assert claimed.lease_owner == "worker-1"
    assert claimed.lease_expires_at == NOW + timedelta(seconds=120)
    assert completed.status is IngestionStatus.SUCCEEDED
    assert completed.stage is IngestionStage.COMPLETED
    assert completed.progress == 100
    assert completed.lease_owner is None


def test_stage_regression_and_invalid_claim_are_rejected() -> None:
    running = make_job().claim(owner="worker-1", now=NOW, lease_seconds=60)
    chunking = running.advance(IngestionStage.CHUNKING, progress=70, now=NOW)

    with pytest.raises(ValueError, match="progress"):
        chunking.advance(IngestionStage.PARSING, progress=20, now=NOW)
    with pytest.raises(ValueError, match="claim"):
        running.claim(owner="worker-2", now=NOW, lease_seconds=60)


def test_continuation_claim_releases_without_consuming_attempt_budget() -> None:
    running = make_job().claim(owner="worker-1", now=NOW, lease_seconds=60)
    chunking = running.advance(IngestionStage.CHUNKING, progress=70, now=NOW)
    queued = chunking.release_for_continuation(now=NOW)
    reclaimed = queued.claim_continuation(owner="worker-2", now=NOW, lease_seconds=60)

    assert queued.status is IngestionStatus.QUEUED
    assert queued.lease_owner is None
    assert queued.progress == 70
    assert reclaimed.status is IngestionStatus.RUNNING
    assert reclaimed.attempt == 1
    assert reclaimed.stage is IngestionStage.CHUNKING


def test_retry_and_expired_chunking_preserve_resume_stage_and_progress() -> None:
    running = make_job().claim(owner="worker-1", now=NOW, lease_seconds=60)
    chunking = running.advance(IngestionStage.CHUNKING, progress=78, now=NOW)
    retry = chunking.fail(
        error_code="EMBEDDING_UNAVAILABLE",
        error_message="temporary failure",
        retryable=True,
        now=NOW,
        retry_base_seconds=10,
    )
    reclaimed = retry.claim(owner="worker-2", now=retry.next_retry_at or NOW, lease_seconds=60)
    expired = reclaimed.recover_expired(now=NOW + timedelta(seconds=71))

    assert reclaimed.stage is IngestionStage.CHUNKING
    assert reclaimed.progress == 78
    assert expired.stage is IngestionStage.CHUNKING
    assert expired.progress == 78


def test_retry_scheduled_chunking_claims_continuation_and_consumes_attempt() -> None:
    running = make_job(max_attempts=3).claim(owner="worker-1", now=NOW, lease_seconds=60)
    chunking = running.advance(IngestionStage.CHUNKING, progress=75, now=NOW)
    retry = chunking.fail(
        error_code="EMBEDDING_UNAVAILABLE",
        error_message="temporary failure",
        retryable=True,
        now=NOW,
        retry_base_seconds=10,
    )
    assert retry.next_retry_at is not None

    continued = retry.claim_continuation(
        owner="worker-2",
        now=retry.next_retry_at,
        lease_seconds=60,
    )

    assert continued.status is IngestionStatus.RUNNING
    assert continued.attempt == 2
    assert continued.stage is IngestionStage.CHUNKING
    assert continued.progress == 75
    assert continued.error_code is None
    assert continued.last_dispatched_at is None


def test_retryable_failures_back_off_then_exhaust_attempts() -> None:
    first = make_job(max_attempts=2).claim(owner="worker-1", now=NOW, lease_seconds=60)
    retry = first.fail(
        error_code="OBJECT_STORE_UNAVAILABLE",
        error_message="temporary failure",
        retryable=True,
        now=NOW,
        retry_base_seconds=10,
    )

    assert retry.status is IngestionStatus.RETRY_SCHEDULED
    assert retry.next_retry_at == NOW + timedelta(seconds=10)
    assert retry.last_dispatched_at is None
    assert retry.celery_task_id is None
    second = retry.claim(owner="worker-2", now=retry.next_retry_at, lease_seconds=60)
    exhausted = second.fail(
        error_code="OBJECT_STORE_UNAVAILABLE",
        error_message="still unavailable",
        retryable=True,
        now=retry.next_retry_at,
        retry_base_seconds=10,
    )

    assert exhausted.status is IngestionStatus.FAILED
    assert exhausted.attempt == 2
    assert exhausted.next_retry_at is None


def test_expired_lease_recovers_or_fails_closed_and_manual_retry_resets_budget() -> None:
    running = make_job(max_attempts=2).claim(owner="worker-1", now=NOW, lease_seconds=10)
    recovered = running.recover_expired(now=NOW + timedelta(seconds=11))

    assert recovered.status is IngestionStatus.QUEUED
    assert recovered.error_code == "LEASE_EXPIRED"

    second = recovered.claim(owner="worker-2", now=NOW + timedelta(seconds=11), lease_seconds=10)
    terminal = second.recover_expired(now=NOW + timedelta(seconds=22))
    manual = terminal.manual_retry(now=NOW + timedelta(seconds=23))

    assert terminal.status is IngestionStatus.FAILED
    assert manual.status is IngestionStatus.QUEUED
    assert manual.attempt == 0
    assert manual.error_code is None


def test_invalid_job_transitions_and_configuration_fail_fast() -> None:
    with pytest.raises(ValueError, match="max_attempts"):
        IngestionJob.new(
            document_version_id=uuid4(),
            actor_id=uuid4(),
            system_id=uuid4(),
            idempotency_key="invalid",
            max_attempts=0,
            now=NOW,
        )
    queued = make_job()
    with pytest.raises(ValueError, match="owner"):
        queued.claim(owner="", now=NOW, lease_seconds=0)
    with pytest.raises(ValueError, match="running"):
        queued.advance(IngestionStage.PARSING, progress=20, now=NOW)
    with pytest.raises(ValueError, match="running"):
        queued.complete(now=NOW)
    with pytest.raises(ValueError, match="running"):
        queued.fail(
            error_code="FAILED",
            error_message="failed",
            retryable=False,
            now=NOW,
            retry_base_seconds=1,
        )
    with pytest.raises(ValueError, match="expired"):
        queued.recover_expired(now=NOW)
    with pytest.raises(ValueError, match="failed"):
        queued.manual_retry(now=NOW)
