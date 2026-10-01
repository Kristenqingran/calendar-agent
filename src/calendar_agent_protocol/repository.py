from __future__ import annotations

import hashlib
import json
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.orm import Session

from .domain import ExchangeStatus, TaskEntity, TaskSnapshot, transition, utc_now
from .enums import Intent, ObjectType, OperationStatus, TaskStatus, Tool
from .persistence import (
    ClarificationRow,
    ConversationRow,
    InboundReceiptRow,
    OperationRow,
    StateTransitionRow,
    TaskParameterRow,
    TaskRow,
    TaskStepRow,
    ToolExchangeRow,
)


class RepositoryError(RuntimeError):
    pass


class DuplicateId(RepositoryError):
    pass


class ConcurrencyError(RepositoryError):
    pass


class IdempotencyConflict(RepositoryError):
    pass


class CorrelationError(RepositoryError):
    pass


class TerminalTaskError(RepositoryError):
    pass


class UnknownOperationLocked(RepositoryError):
    pass


def digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()


class UnitOfWork:
    def __init__(self, session: Session):
        self.session = session

    def __enter__(self) -> UnitOfWork:
        return self

    def __exit__(self, t: Any, v: Any, tb: Any) -> None:
        if t:
            self.session.rollback()
        else:
            self.session.commit()


class ConversationRepository:
    def __init__(self, s: Session):
        self.s = s

    def create(self, id: str, tz: str) -> ConversationRow:
        if self.s.get(ConversationRow, id) is not None:
            raise DuplicateId(id)
        row = ConversationRow(conversation_id=id, assistant_timezone=tz)
        self.s.add(row)
        self.s.flush()
        return row

    def get(self, id: str) -> ConversationRow | None:
        return self.s.get(ConversationRow, id)

    def update_timezone(self, id: str, timezone: str) -> ConversationRow:
        row = self.s.get(ConversationRow, id)
        if row is None:
            raise KeyError(id)
        row.assistant_timezone = timezone
        row.updated_at = utc_now()
        self.s.flush()
        return row


class TaskRepository:
    def __init__(self, s: Session):
        self.s = s

    def create(self, t: TaskEntity) -> TaskRow:
        row = TaskRow(
            task_id=t.task_id,
            conversation_id=t.conversation_id,
            original_message=t.original_message,
            object=t.object.value,
            intent=t.intent.value,
            current_state=t.current_state.value,
            final_status=t.final_status,
            current_step_id=t.current_step_id,
            version=t.version,
        )
        self.s.add(row)
        self.s.flush()
        return row

    def get(self, id: str) -> TaskRow | None:
        return self.s.get(TaskRow, id)

    def latest_for_conversation(self, conversation_id: str) -> TaskRow | None:
        return self.s.scalars(
            select(TaskRow)
            .where(TaskRow.conversation_id == conversation_id)
            .order_by(TaskRow.created_at.desc(), TaskRow.task_id.desc())
            .limit(1)
        ).first()

    def waiting_clarification_for_conversation(self, conversation_id: str) -> list[TaskRow]:
        return list(
            self.s.scalars(
                select(TaskRow)
                .where(
                    TaskRow.conversation_id == conversation_id,
                    TaskRow.current_state == TaskStatus.WAITING_CLARIFICATION.value,
                )
                .order_by(TaskRow.created_at, TaskRow.task_id)
            ).all()
        )

    def update_with_version(
        self, id: str, *, expected_version: int, current_step_id: str | None
    ) -> TaskRow:
        if self.s.get(TaskRow, id) is None:
            raise KeyError(id)
        result = self.s.execute(
            update(TaskRow)
            .where(TaskRow.task_id == id, TaskRow.version == expected_version)
            .values(
                current_step_id=current_step_id,
                version=expected_version + 1,
                updated_at=utc_now(),
            )
        )
        if not isinstance(result, CursorResult) or result.rowcount != 1:
            raise ConcurrencyError(id)
        self.s.flush()
        row = self.s.get(TaskRow, id)
        if row is None:
            raise KeyError(id)
        self.s.refresh(row)
        return row

    def transition(self, id: str, target: TaskStatus, reason: str, version: int) -> TaskRow:
        row = self.s.get(TaskRow, id)
        if row is None:
            raise KeyError(id)
        entity = TaskEntity(
            row.task_id,
            row.conversation_id,
            row.original_message,
            ObjectType(row.object),
            Intent(row.intent),
            TaskStatus(row.current_state),
            row.final_status,
            row.current_step_id,
            row.version,
            row.created_at,
            row.updated_at,
        )
        old, new, _ = transition(entity, target, reason)
        result = self.s.execute(
            update(TaskRow)
            .where(TaskRow.task_id == id, TaskRow.version == version)
            .values(
                current_state=new.value,
                final_status=entity.final_status,
                version=version + 1,
                updated_at=utc_now(),
            )
        )
        if not isinstance(result, CursorResult) or result.rowcount != 1:
            raise ConcurrencyError(id)
        self.s.add(
            StateTransitionRow(task_id=id, from_state=old.value, to_state=new.value, reason=reason)
        )
        self.s.flush()
        self.s.expire(row)
        return row

    def snapshot(self, id: str) -> TaskSnapshot:
        r = self.s.get(TaskRow, id)
        if r is None:
            raise KeyError(id)
        task = TaskEntity(
            r.task_id,
            r.conversation_id,
            r.original_message,
            ObjectType(r.object),
            Intent(r.intent),
            TaskStatus(r.current_state),
            r.final_status,
            r.current_step_id,
            r.version,
            r.created_at,
            r.updated_at,
        )

        def rows(cls: Any) -> list[dict[str, Any]]:
            return [
                {c.name: getattr(x, c.name) for c in x.__table__.columns}
                for x in self.s.scalars(select(cls).where(cls.task_id == id))
            ]

        clar = self.s.scalar(
            select(ClarificationRow).where(
                ClarificationRow.task_id == id, ClarificationRow.resolved_at.is_(None)
            )
        )
        return TaskSnapshot(
            task,
            rows(TaskParameterRow),
            rows(TaskStepRow),
            rows(ToolExchangeRow),
            rows(OperationRow),
            None
            if clar is None
            else {c.name: getattr(clar, c.name) for c in clar.__table__.columns},
        )


class TaskParameterRepository:
    def __init__(self, s: Session):
        self.s = s

    def get(self, task_id: str, name: str) -> TaskParameterRow | None:
        return self.s.get(TaskParameterRow, (task_id, name))

    def list(self, task_id: str) -> list[TaskParameterRow]:
        statement = (
            select(TaskParameterRow)
            .where(TaskParameterRow.task_id == task_id)
            .order_by(TaskParameterRow.name)
        )
        return list(self.s.scalars(statement))

    def upsert(
        self,
        task_id: str,
        name: str,
        *,
        value: Any,
        source: str | None,
        status: str,
        evidence: str | None,
    ) -> TaskParameterRow:
        row = self.get(task_id, name)
        if row is None:
            row = TaskParameterRow(task_id=task_id, name=name)
            self.s.add(row)
        row.value = value
        row.source = source
        row.status = status
        row.evidence = evidence
        row.updated_at = utc_now()
        self.s.flush()
        return row


class StepRepository:
    def __init__(self, s: Session):
        self.s = s

    def create(self, **kw: Any) -> TaskStepRow:
        r = TaskStepRow(**kw)
        self.s.add(r)
        self.s.flush()
        return r

    def get(self, step_id: str) -> TaskStepRow | None:
        return self.s.get(TaskStepRow, step_id)

    def complete(
        self, step_id: str, *, output_summary: dict[str, Any] | None = None
    ) -> TaskStepRow:
        row = self.get(step_id)
        if row is None:
            raise KeyError(step_id)
        row.status = "completed"
        row.output_summary = output_summary
        row.completed_at = utc_now()
        self.s.flush()
        return row


class ToolExchangeRepository:
    def __init__(self, s: Session):
        self.s = s

    def get(self, step_id: str) -> ToolExchangeRow | None:
        return self.s.get(ToolExchangeRow, step_id)

    def list_for_task(self, task_id: str) -> list[ToolExchangeRow]:
        return list(
            self.s.scalars(
                select(ToolExchangeRow)
                .where(ToolExchangeRow.task_id == task_id)
                .order_by(ToolExchangeRow.created_at, ToolExchangeRow.step_id)
            ).all()
        )

    def save_request(
        self, *, dependency_parameters: set[str] | None = None, **kw: Any
    ) -> ToolExchangeRow:
        r = ToolExchangeRow(
            status=ExchangeStatus.PENDING.value,
            dependency_parameters=sorted(dependency_parameters or set()),
            **kw,
        )
        self.s.add(r)
        self.s.flush()
        return r

    def save_result(self, step_id: str, payload: dict[str, Any]) -> tuple[ToolExchangeRow, bool]:
        r = self.s.get(ToolExchangeRow, step_id)
        if r is None:
            raise CorrelationError("unknown step")
        h = digest(payload)
        if r.result_hash:
            if r.result_hash == h:
                return r, False
            raise IdempotencyConflict("conflicting tool result")
        task = self.s.get(TaskRow, r.task_id)
        if task is None or TaskStatus(task.current_state) in {
            TaskStatus.SUCCEEDED,
            TaskStatus.FAILED,
            TaskStatus.UNKNOWN,
        }:
            raise TerminalTaskError(r.task_id)
        if (
            payload.get("task_id") != r.task_id
            or payload.get("step_id") != step_id
            or payload.get("tool") != r.tool
        ):
            raise CorrelationError("tool result mismatch")
        reqop = r.request_payload.get("operation_id")
        if reqop != payload.get("operation_id"):
            raise CorrelationError("operation mismatch")
        r.result_payload = payload
        r.result_hash = h
        r.status = payload["status"]
        self.s.flush()
        return r, True

    def invalidate(self, step_id: str, reason: str) -> None:
        r = self.s.get(ToolExchangeRow, step_id)
        if r is None:
            raise KeyError(step_id)
        r.is_stale = True
        r.stale_reason = reason
        r.invalidated_at = utc_now()
        self.s.flush()


class OperationRepository:
    def __init__(self, s: Session):
        self.s = s

    def get(self, operation_id: str) -> OperationRow | None:
        return self.s.get(OperationRow, operation_id)

    def mark_dispatched(self, operation_id: str) -> OperationRow:
        row = self.get(operation_id)
        if row is None:
            raise KeyError(operation_id)
        row.status = OperationStatus.DISPATCHED.value
        row.updated_at = utc_now()
        self.s.flush()
        return row

    def record_result(
        self,
        operation_id: str,
        *,
        status: OperationStatus,
        result_payload: dict[str, Any] | None,
    ) -> OperationRow:
        row = self.get(operation_id)
        if row is None:
            raise KeyError(operation_id)
        row.status = status.value
        row.result_payload = result_payload
        row.updated_at = utc_now()
        self.s.flush()
        return row

    def record_verification(
        self, operation_id: str, *, status: OperationStatus
    ) -> OperationRow:
        row = self.get(operation_id)
        if row is None:
            raise KeyError(operation_id)
        row.status = status.value
        row.verification_status = status.value
        row.updated_at = utc_now()
        self.s.flush()
        return row

    def create_or_replay(
        self, operation_id: str, task_id: str, tool: Tool, args: dict[str, Any]
    ) -> tuple[OperationRow, bool]:
        h = digest(args)
        r = self.s.get(OperationRow, operation_id)
        if r:
            if r.arguments_hash != h:
                raise IdempotencyConflict(operation_id)
            if r.status == OperationStatus.UNKNOWN.value:
                raise UnknownOperationLocked(operation_id)
            return r, False
        r = OperationRow(
            operation_id=operation_id,
            task_id=task_id,
            tool=tool.value,
            arguments_hash=h,
            status=OperationStatus.PLANNED.value,
        )
        self.s.add(r)
        self.s.flush()
        return r, True


class ClarificationRepository:
    def __init__(self, s: Session):
        self.s = s

    def save(self, **kw: Any) -> ClarificationRow:
        r = ClarificationRow(**kw)
        self.s.add(r)
        self.s.flush()
        return r

    def get_pending(self, task_id: str) -> ClarificationRow | None:
        statement = select(ClarificationRow).where(
            ClarificationRow.task_id == task_id,
            ClarificationRow.resolved_at.is_(None),
        )
        return self.s.scalar(statement)

    def list_for_task(self, task_id: str) -> list[ClarificationRow]:
        statement = (
            select(ClarificationRow)
            .join(TaskStepRow, TaskStepRow.step_id == ClarificationRow.step_id)
            .where(ClarificationRow.task_id == task_id)
            .order_by(TaskStepRow.created_at, TaskStepRow.step_id)
        )
        return list(self.s.scalars(statement).all())

    def pending_for_task(self, task_id: str) -> list[ClarificationRow]:
        statement = select(ClarificationRow).where(
            ClarificationRow.task_id == task_id,
            ClarificationRow.resolved_at.is_(None),
        )
        return list(self.s.scalars(statement).all())

    def resolve(self, task_id: str, step_id: str, response: Any) -> ClarificationRow:
        task = self.s.get(TaskRow, task_id)
        if task is None or TaskStatus(task.current_state) in {
            TaskStatus.SUCCEEDED,
            TaskStatus.FAILED,
            TaskStatus.UNKNOWN,
        }:
            raise TerminalTaskError(task_id)
        r = self.s.get(ClarificationRow, step_id)
        if r is None or r.task_id != task_id:
            raise CorrelationError("clarification mismatch")
        if r.resolved_at:
            return r
        r.user_response = response
        r.resolved_at = utc_now()
        self.s.flush()
        return r


class TransitionRepository:
    def __init__(self, s: Session):
        self.s = s

    def append(
        self,
        *,
        task_id: str,
        from_state: str,
        to_state: str,
        reason: str,
    ) -> StateTransitionRow:
        row = StateTransitionRow(
            task_id=task_id,
            from_state=from_state,
            to_state=to_state,
            reason=reason,
        )
        self.s.add(row)
        self.s.flush()
        return row

    def list(self, task_id: str) -> list[StateTransitionRow]:
        statement = (
            select(StateTransitionRow)
            .where(StateTransitionRow.task_id == task_id)
            .order_by(StateTransitionRow.id)
        )
        return list(self.s.scalars(statement))


class InboundReceiptRepository:
    def __init__(self, s: Session):
        self.s = s

    def get(self, request_id: str) -> InboundReceiptRow | None:
        return self.s.get(InboundReceiptRow, request_id)

    def accept(self, **kw: Any) -> tuple[InboundReceiptRow, bool]:
        r = self.s.get(InboundReceiptRow, kw["request_id"])
        if r:
            if r.payload_hash != kw["payload_hash"]:
                raise IdempotencyConflict(kw["request_id"])
            return r, False
        r = InboundReceiptRow(**kw)
        self.s.add(r)
        self.s.flush()
        return r, True

    def save_response(self, request_id: str, response_payload: dict[str, Any]) -> InboundReceiptRow:
        row = self.get(request_id)
        if row is None:
            raise KeyError(request_id)
        row.response_payload = response_payload
        self.s.flush()
        return row
