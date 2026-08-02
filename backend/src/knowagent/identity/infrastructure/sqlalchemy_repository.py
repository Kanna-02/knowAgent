from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from knowagent.common.errors import ConflictError
from knowagent.identity.domain.models import Account, AccountRole, AccountStatus
from knowagent.identity.infrastructure.sqlalchemy_models import AccountRecord, AuditLogRecord


class SqlAlchemyAccountRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get_by_username(self, username: str) -> Account | None:
        record = self._session.scalar(
            select(AccountRecord).where(AccountRecord.username == username)
        )
        return self._to_domain(record) if record else None

    def get_by_id(self, account_id: UUID) -> Account | None:
        record = self._session.get(AccountRecord, account_id)
        return self._to_domain(record) if record else None

    def save(self, account: Account) -> Account:
        record = self._session.get(AccountRecord, account.id)
        if record is None:
            raise ConflictError("ACCOUNT_NOT_FOUND", "账号不存在")
        self._copy_to_record(account, record)
        self._session.flush()
        return self._to_domain(record)

    def add(self, account: Account) -> Account:
        record = AccountRecord(
            id=account.id,
            username=account.username,
            display_name=account.display_name,
            password_hash=account.password_hash,
            role=account.role,
            source=account.source,
            status=account.status,
            must_change_password=account.must_change_password,
            session_version=account.session_version,
            credential_batch=account.credential_batch,
            external_provider=account.external_provider,
            external_subject=account.external_subject,
            created_at=account.created_at,
            updated_at=account.updated_at,
        )
        self._session.add(record)
        try:
            self._session.flush()
        except IntegrityError as error:
            raise ConflictError("ACCOUNT_EXISTS", "账号已存在") from error
        return self._to_domain(record)

    def list(
        self,
        *,
        page: int,
        page_size: int,
        role: AccountRole | None,
        status: AccountStatus | None,
        search: str | None,
    ) -> tuple[list[Account], int]:
        filters = []
        if role is not None:
            filters.append(AccountRecord.role == role)
        if status is not None:
            filters.append(AccountRecord.status == status)
        normalized_search = search.strip() if search else ""
        if normalized_search:
            filters.append(
                or_(
                    AccountRecord.username.icontains(normalized_search, autoescape=True),
                    AccountRecord.display_name.icontains(normalized_search, autoescape=True),
                )
            )
        total = self._session.scalar(
            select(func.count()).select_from(AccountRecord).where(*filters)
        )
        records = self._session.scalars(
            select(AccountRecord)
            .where(*filters)
            .order_by(AccountRecord.created_at.desc(), AccountRecord.username)
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
        return [self._to_domain(record) for record in records], int(total or 0)

    def count_active_admins(self) -> int:
        count = self._session.scalar(
            select(func.count())
            .select_from(AccountRecord)
            .where(
                AccountRecord.role == AccountRole.ADMIN,
                AccountRecord.status == AccountStatus.ACTIVE,
            )
        )
        return int(count or 0)

    def lock_active_admins(self) -> int:
        active_admin_ids = self._session.scalars(
            select(AccountRecord.id)
            .where(
                AccountRecord.role == AccountRole.ADMIN,
                AccountRecord.status == AccountStatus.ACTIVE,
            )
            .order_by(AccountRecord.id)
            .with_for_update()
        ).all()
        return len(active_admin_ids)

    @staticmethod
    def _copy_to_record(account: Account, record: AccountRecord) -> None:
        record.username = account.username
        record.display_name = account.display_name
        record.password_hash = account.password_hash
        record.role = account.role
        record.source = account.source
        record.status = account.status
        record.must_change_password = account.must_change_password
        record.session_version = account.session_version
        record.credential_batch = account.credential_batch
        record.external_provider = account.external_provider
        record.external_subject = account.external_subject
        record.updated_at = account.updated_at

    @staticmethod
    def _to_domain(record: AccountRecord) -> Account:
        return Account(
            id=record.id,
            username=record.username,
            display_name=record.display_name,
            password_hash=record.password_hash,
            role=record.role,
            source=record.source,
            status=record.status,
            must_change_password=record.must_change_password,
            session_version=record.session_version,
            credential_batch=record.credential_batch,
            external_provider=record.external_provider,
            external_subject=record.external_subject,
            created_at=record.created_at,
            updated_at=record.updated_at,
        )


class SqlAlchemyAuditSink:
    def __init__(self, session: Session) -> None:
        self._session = session

    def record(
        self,
        action: str,
        result: str,
        *,
        actor_id: UUID | None = None,
        object_type: str | None = None,
        object_id: UUID | None = None,
        request_id: str | None = None,
        metadata: dict[str, str | int | bool] | None = None,
    ) -> None:
        self._session.add(
            AuditLogRecord(
                actor_id=actor_id,
                action=action,
                result=result,
                object_type=object_type,
                object_id=object_id,
                request_id=request_id,
                context_data=metadata,
            )
        )
        self._session.flush()
        self._session.commit()
