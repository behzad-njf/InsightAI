"""SQLAlchemy implementation of ``IApiKeyStore`` (Phase 16.3)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from insightai.domain.models.api_key import ApiKey, CreateApiKeyRequest, CreateApiKeyResult
from insightai.infrastructure.app_db.key_crypto import hash_api_key_secret, verify_api_key_secret
from insightai.infrastructure.app_db.key_format import (
    build_api_key_token,
    generate_key_prefix,
    generate_key_secret,
    parse_api_key_token,
)
from insightai.infrastructure.app_db.models.api_keys import ApiKeyRecord

if TYPE_CHECKING:
    from sqlalchemy.engine import Engine


class SqlApiKeyStore:
    """Persist API keys in the platform app database."""

    def __init__(self, engine: Engine) -> None:
        self._session_factory = sessionmaker(
            bind=engine,
            autoflush=False,
            autocommit=False,
            expire_on_commit=False,
        )

    def create(self, request: CreateApiKeyRequest) -> CreateApiKeyResult:
        key_id = str(uuid4())
        prefix = generate_key_prefix()
        secret_part = generate_key_secret()
        full_secret = build_api_key_token(key_prefix=prefix, secret=secret_part)
        now = datetime.now(UTC)
        record = ApiKeyRecord(
            id=key_id,
            key_prefix=prefix,
            key_hash=hash_api_key_secret(full_secret),
            label=request.label,
            roles_json=ApiKeyRecord.dump_roles(request.roles),
            attributes_json=ApiKeyRecord.dump_attributes(request.attributes),
            created_at=now,
            expires_at=request.expires_at,
            revoked_at=None,
        )
        with self._session() as session:
            session.add(record)
            session.commit()
        api_key = _record_to_domain(record)
        return CreateApiKeyResult(api_key=api_key, secret=full_secret)

    def verify(self, secret: str) -> ApiKey | None:
        parsed = parse_api_key_token(secret)
        if parsed is None:
            return None
        prefix, full_token = parsed
        with self._session() as session:
            record = session.scalar(
                select(ApiKeyRecord).where(ApiKeyRecord.key_prefix == prefix),
            )
            if record is None:
                return None
            if not verify_api_key_secret(full_token, record.key_hash):
                return None
            api_key = _record_to_domain(record)
            if not api_key.is_active:
                return None
            return api_key

    def revoke(self, *, key_id: str | None = None, key_prefix: str | None = None) -> bool:
        if not key_id and not key_prefix:
            msg = "revoke requires key_id or key_prefix"
            raise ValueError(msg)
        with self._session() as session:
            record = _fetch_record(session, key_id=key_id, key_prefix=key_prefix)
            if record is None:
                return False
            if record.revoked_at is not None:
                return True
            record.revoked_at = datetime.now(UTC)
            session.commit()
            return True

    def list_keys(self, *, include_revoked: bool = False) -> list[ApiKey]:
        with self._session() as session:
            rows = session.scalars(select(ApiKeyRecord).order_by(ApiKeyRecord.created_at.desc()))
            keys = [_record_to_domain(row) for row in rows]
        if include_revoked:
            return keys
        return [key for key in keys if not key.is_revoked]

    def get_by_id(self, key_id: str) -> ApiKey | None:
        with self._session() as session:
            record = session.get(ApiKeyRecord, key_id)
            if record is None:
                return None
            return _record_to_domain(record)

    def _session(self) -> Session:
        return self._session_factory()


def _fetch_record(
    session: Session,
    *,
    key_id: str | None,
    key_prefix: str | None,
) -> ApiKeyRecord | None:
    if key_id:
        return session.get(ApiKeyRecord, key_id)
    if key_prefix:
        return session.scalar(
            select(ApiKeyRecord).where(ApiKeyRecord.key_prefix == key_prefix),
        )
    return None


def _record_to_domain(record: ApiKeyRecord) -> ApiKey:
    created_at = _ensure_utc(record.created_at)
    expires_at = _ensure_utc(record.expires_at) if record.expires_at else None
    revoked_at = _ensure_utc(record.revoked_at) if record.revoked_at else None
    return ApiKey(
        id=record.id,
        key_prefix=record.key_prefix,
        label=record.label,
        roles=ApiKeyRecord.load_roles(record.roles_json),
        attributes=ApiKeyRecord.load_attributes(record.attributes_json),
        created_at=created_at,
        expires_at=expires_at,
        revoked_at=revoked_at,
    )


def _ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def require_api_key_store(engine: Engine) -> SqlApiKeyStore:
    """Factory helper for CLI and future DI."""
    return SqlApiKeyStore(engine)
