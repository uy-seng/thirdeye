from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from core.utils import dump_json, utcnow
from jobs.models import Operation


ACTIVE_OPERATION_STATUSES = {"pending", "running"}


@dataclass(frozen=True)
class OperationRecord:
    id: str
    job_id: str | None
    kind: str
    status: str
    idempotency_key: str | None
    created: bool = False


class OperationRepository:
    def __init__(self, session_factory: sessionmaker) -> None:
        self.session_factory = session_factory

    def get_or_create(
        self,
        *,
        job_id: str | None,
        kind: str,
        idempotency_key: str,
        payload: dict[str, Any] | None = None,
    ) -> OperationRecord:
        with self.session_factory() as session:
            existing = session.execute(
                select(Operation)
                .where(
                    Operation.idempotency_key == idempotency_key,
                    Operation.status.in_(ACTIVE_OPERATION_STATUSES),
                )
                .order_by(Operation.created_at.desc())
            ).scalars().first()
            if existing is not None:
                return self._record(existing, created=False)

            now = utcnow()
            operation = Operation(
                id=uuid.uuid4().hex,
                job_id=job_id,
                kind=kind,
                status="pending",
                idempotency_key=idempotency_key,
                created_at=now,
                updated_at=now,
                payload_json=dump_json(payload or {}),
                result_json=None,
                error_message=None,
            )
            session.add(operation)
            session.commit()
            return self._record(operation, created=True)

    def mark_running(self, operation_id: str) -> None:
        self._update(operation_id, status="running")

    def mark_completed(self, operation_id: str, result: dict[str, Any] | None = None) -> None:
        self._update(operation_id, status="completed", result_json=dump_json(result or {}), error_message=None)

    def mark_failed(self, operation_id: str, message: str) -> None:
        self._update(operation_id, status="failed", error_message=message)

    def _update(self, operation_id: str, **fields: Any) -> None:
        with self.session_factory() as session:
            operation = session.get(Operation, operation_id)
            if operation is None:
                return
            for key, value in fields.items():
                setattr(operation, key, value)
            operation.updated_at = utcnow()
            session.add(operation)
            session.commit()

    @staticmethod
    def _record(operation: Operation, *, created: bool) -> OperationRecord:
        return OperationRecord(
            id=operation.id,
            job_id=operation.job_id,
            kind=operation.kind,
            status=operation.status,
            idempotency_key=operation.idempotency_key,
            created=created,
        )
