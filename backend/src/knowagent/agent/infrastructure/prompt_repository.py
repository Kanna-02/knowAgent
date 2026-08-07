from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from knowagent.agent.domain.models import PromptDefinition
from knowagent.agent.infrastructure.sqlalchemy_models import PromptDefinitionRecord
from knowagent.agent.prompts import load_prompt_definition as load_packaged_prompt
from knowagent.common.errors import ConflictError, NotFoundError


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


class PromptRepository:  # pylint: disable=too-few-public-methods
    """Loads versioned prompt definitions from the database.

    Resolution order for ``get_active(scenario)``:
    1. The enabled database row for the scenario (``enabled=1``).
    2. The packaged ``grounded-answer-v1.json`` resource when no DB row is
       present. This keeps the fallback working before any DB seed exists.

    ``get_version(scenario, version)`` returns a specific version regardless of
    its enabled flag, supporting rollback and comparison without activation.
    """

    def __init__(self, session: Session) -> None:
        self._session = session

    def get_active(self, scenario: str) -> PromptDefinition | None:
        record = self._session.scalar(
            select(PromptDefinitionRecord).where(
                PromptDefinitionRecord.scenario == scenario,
                PromptDefinitionRecord.enabled.is_(True),
            )
        )
        if record is None:
            return None
        return self._to_domain(record)

    def get_version(self, scenario: str, version: str) -> PromptDefinition:
        record = self._session.scalar(
            select(PromptDefinitionRecord).where(
                PromptDefinitionRecord.scenario == scenario,
                PromptDefinitionRecord.version == version,
            )
        )
        if record is None:
            try:
                packaged = load_packaged_prompt(version)
            except ValueError as error:
                raise NotFoundError("PROMPT_VERSION_NOT_FOUND", "提示词版本不存在") from error
            if packaged.scenario != scenario:
                raise NotFoundError("PROMPT_VERSION_NOT_FOUND", "提示词版本不存在")
            return packaged
        return self._to_domain(record)

    def list_page(
        self,
        *,
        scenario: str | None,
        page: int,
        page_size: int,
    ) -> tuple[tuple[PromptDefinition, ...], int]:
        if page <= 0 or page_size <= 0:
            raise ValueError("prompt pagination parameters must be positive")
        conditions = []
        if scenario is not None:
            conditions.append(PromptDefinitionRecord.scenario == scenario)
        total = self._session.scalar(
            select(func.count()).select_from(PromptDefinitionRecord).where(*conditions)
        )
        records = self._session.scalars(
            select(PromptDefinitionRecord)
            .where(*conditions)
            .order_by(PromptDefinitionRecord.created_at.desc(), PromptDefinitionRecord.version)
            .limit(page_size)
            .offset((page - 1) * page_size)
        ).all()
        return tuple(self._to_domain(record) for record in records), int(total or 0)

    def save(self, definition: PromptDefinition) -> PromptDefinition:
        existing = self._session.scalar(
            select(PromptDefinitionRecord).where(
                PromptDefinitionRecord.scenario == definition.scenario,
                PromptDefinitionRecord.version == definition.version,
            )
        )
        if existing is not None:
            raise ConflictError(
                "PROMPT_VERSION_EXISTS",
                "提示词版本已存在",
            )
        record = PromptDefinitionRecord(
            id=uuid4(),
            scenario=definition.scenario,
            version=definition.version,
            content=definition.content,
            enabled=bool(definition.enabled),
            created_at=definition.created_at,
            change_note=definition.change_note,
        )
        with self._session.begin_nested():
            self._session.add(record)
            self._session.flush()
        return self._to_domain(record)

    def activate(self, scenario: str, version: str) -> PromptDefinition:
        with self._session.begin_nested():
            rows = self._session.scalars(
                select(PromptDefinitionRecord)
                .where(PromptDefinitionRecord.scenario == scenario)
                .with_for_update()
            ).all()
            activated = next((row for row in rows if row.version == version), None)
            if activated is None:
                raise NotFoundError("PROMPT_VERSION_NOT_FOUND", "提示词版本不存在")
            for row in rows:
                if row is not activated:
                    row.enabled = False
            self._session.flush()
            activated.enabled = True
            self._session.flush()
        return self._to_domain(activated)

    @staticmethod
    def _to_domain(record: PromptDefinitionRecord) -> PromptDefinition:
        return PromptDefinition(
            scenario=record.scenario,
            version=record.version,
            content=record.content,
            enabled=bool(record.enabled),
            created_at=_aware(record.created_at),
            change_note=record.change_note,
        )
