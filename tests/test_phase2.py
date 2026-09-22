from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from calendar_agent_protocol.domain import (
    ALLOWED_TRANSITIONS,
    IllegalTransition,
    StepStatus,
    StepType,
    TaskEntity,
    can_transition,
    transition,
)
from calendar_agent_protocol.enums import Intent, ObjectType, OperationStatus, TaskStatus, Tool
from calendar_agent_protocol.persistence import Base, StateTransitionRow, TaskRow, make_engine
from calendar_agent_protocol.repository import (
    ClarificationRepository,
    ConcurrencyError,
    ConversationRepository,
    DuplicateId,
    IdempotencyConflict,
    InboundReceiptRepository,
    OperationRepository,
    StepRepository,
    TaskRepository,
    ToolExchangeRepository,
    UnknownOperationLocked,
)


@pytest.fixture
def session(tmp_path: Path):
    engine = make_engine(f"sqlite:///{tmp_path / 'test.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as value:
        yield value


@pytest.fixture
def seeded(session: Session):
    ConversationRepository(session).create("conv_1", "Asia/Shanghai")
    task = TaskEntity("task_1", "conv_1", "测试", ObjectType.CALENDAR_EVENT, Intent.CREATE)
    TaskRepository(session).create(task)
    session.commit()
    return task


@pytest.mark.parametrize(
    ("source", "target"), [(a, b) for a, values in ALLOWED_TRANSITIONS.items() for b in values]
)
def test_every_allowed_transition(source, target):
    assert can_transition(source, target)


@pytest.mark.parametrize("terminal", [TaskStatus.SUCCEEDED, TaskStatus.FAILED, TaskStatus.UNKNOWN])
def test_terminal_protection(terminal):
    task = TaskEntity("t", "c", "m", ObjectType.REMINDER, Intent.QUERY, current_state=terminal)
    with pytest.raises(IllegalTransition):
        transition(task, TaskStatus.PLANNING, "late")


def test_illegal_transition():
    with pytest.raises(IllegalTransition):
        transition(
            TaskEntity("t", "c", "m", ObjectType.REMINDER, Intent.QUERY),
            TaskStatus.SUCCEEDED,
            "bad",
        )


def test_unique_and_foreign_key(session):
    ConversationRepository(session).create("conv_1", "UTC")
    session.commit()
    with pytest.raises(DuplicateId):
        ConversationRepository(session).create("conv_1", "UTC")
    session.rollback()
    with pytest.raises(IntegrityError):
        TaskRepository(session).create(
            TaskEntity("task_x", "missing", "m", ObjectType.REMINDER, Intent.QUERY)
        )


@pytest.mark.parametrize(
    "state",
    [
        TaskStatus.WAITING_TOOL_RESULT,
        TaskStatus.WAITING_CLARIFICATION,
        TaskStatus.VERIFYING_FINAL_STATE,
        TaskStatus.RECOVERING,
    ],
)
def test_snapshot_restart_states(session, seeded, state):
    row = session.get(TaskRow, "task_1")
    row.current_state = state.value
    session.commit()
    session.expire_all()
    assert TaskRepository(session).snapshot("task_1").task.current_state == state


def test_transition_audit_and_version_conflict(session, seeded):
    repo = TaskRepository(session)
    repo.transition("task_1", TaskStatus.VALIDATING_INPUT, "start", 1)
    session.commit()
    assert session.scalar(select(StateTransitionRow)) is not None
    with pytest.raises(ConcurrencyError):
        repo.transition("task_1", TaskStatus.ANALYZING, "stale", 1)
    session.rollback()
    assert len(list(session.scalars(select(StateTransitionRow)))) == 1


def test_inbound_idempotency(session, seeded):
    repo = InboundReceiptRepository(session)
    data = dict(
        request_id="req_1",
        conversation_id="conv_1",
        task_id="task_1",
        message_type="user_request",
        payload_hash="a" * 64,
        response_payload={"ok": 1},
    )
    assert repo.accept(**data)[1]
    session.commit()
    assert not repo.accept(**data)[1]
    with pytest.raises(IdempotencyConflict):
        repo.accept(**(data | {"payload_hash": "b" * 64}))


def test_operation_idempotency_and_unknown_lock(session, seeded):
    repo = OperationRepository(session)
    operation, created = repo.create_or_replay(
        "op_1", "task_1", Tool.CREATE_REMINDER, {"title": "x"}
    )
    assert created
    assert not repo.create_or_replay("op_1", "task_1", Tool.CREATE_REMINDER, {"title": "x"})[1]
    with pytest.raises(IdempotencyConflict):
        repo.create_or_replay("op_1", "task_1", Tool.CREATE_REMINDER, {"title": "y"})
    operation.status = OperationStatus.UNKNOWN.value
    session.flush()
    with pytest.raises(UnknownOperationLocked):
        repo.create_or_replay("op_1", "task_1", Tool.CREATE_REMINDER, {"title": "x"})


def test_duplicate_tool_result(session, seeded):
    session.get(TaskRow, "task_1").current_state = TaskStatus.WAITING_TOOL_RESULT.value
    StepRepository(session).create(
        step_id="step_1",
        task_id="task_1",
        step_type=StepType.TOOL_QUERY.value,
        status=StepStatus.IN_PROGRESS.value,
    )
    repo = ToolExchangeRepository(session)
    repo.save_request(
        step_id="step_1",
        task_id="task_1",
        tool="query_calendar",
        purpose="answer_query",
        request_payload={"task_id": "task_1", "step_id": "step_1", "tool": "query_calendar"},
    )
    payload = {
        "task_id": "task_1",
        "step_id": "step_1",
        "tool": "query_calendar",
        "status": "success",
    }
    assert repo.save_result("step_1", payload)[1]
    assert not repo.save_result("step_1", payload)[1]
    with pytest.raises(IdempotencyConflict):
        repo.save_result("step_1", payload | {"status": "failed"})


def test_clarification_recovery(session, seeded):
    session.get(TaskRow, "task_1").current_state = TaskStatus.WAITING_CLARIFICATION.value
    StepRepository(session).create(
        step_id="step_c", task_id="task_1", step_type="clarification", status="in_progress"
    )
    repo = ClarificationRepository(session)
    repo.save(
        step_id="step_c",
        task_id="task_1",
        reason="missing_required_parameter",
        message="多久",
        expected_answer={"type": "duration"},
        missing_fields=["duration"],
        ambiguous_fields=None,
        blocked_from_state="planning",
    )
    assert repo.resolve("task_1", "step_c", {"message": "1小时"}).resolved_at


def test_migration_up_down_repeat(tmp_path):
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{tmp_path / 'migration.db'}")
    command.upgrade(cfg, "head")
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")
    command.upgrade(cfg, "head")
