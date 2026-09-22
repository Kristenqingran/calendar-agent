from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from .enums import Intent, ObjectType, TaskStatus


def utc_now() -> datetime:
    return datetime.now(UTC)


class StepType(StrEnum):
    INPUT_VALIDATION = "input_validation"
    SEMANTIC_ANALYSIS = "semantic_analysis"
    PLANNING = "planning"
    TOOL_QUERY = "tool_query"
    TOOL_WRITE = "tool_write"
    CLARIFICATION = "clarification"
    FINAL_VERIFICATION = "final_verification"
    RECOVERY = "recovery"


class StepStatus(StrEnum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    UNKNOWN = "unknown"
    CANCELLED = "cancelled"


class ExchangeStatus(StrEnum):
    PENDING = "pending"
    SUCCESS = "success"
    FAILED = "failed"
    UNKNOWN = "unknown"


@dataclass
class TaskEntity:
    task_id: str
    conversation_id: str
    original_message: str
    object: ObjectType
    intent: Intent
    current_state: TaskStatus = TaskStatus.RECEIVED
    final_status: str | None = None
    current_step_id: str | None = None
    version: int = 1
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)


@dataclass
class TaskSnapshot:
    task: TaskEntity
    parameters: list[dict[str, Any]] = field(default_factory=list)
    steps: list[dict[str, Any]] = field(default_factory=list)
    tool_exchanges: list[dict[str, Any]] = field(default_factory=list)
    operations: list[dict[str, Any]] = field(default_factory=list)
    pending_clarification: dict[str, Any] | None = None


TERMINAL_STATES = {TaskStatus.SUCCEEDED, TaskStatus.FAILED, TaskStatus.UNKNOWN}
ALLOWED_TRANSITIONS = {
    TaskStatus.RECEIVED: {TaskStatus.VALIDATING_INPUT},
    TaskStatus.VALIDATING_INPUT: {TaskStatus.ANALYZING, TaskStatus.FAILED},
    TaskStatus.ANALYZING: {
        TaskStatus.PLANNING,
        TaskStatus.WAITING_CLARIFICATION,
        TaskStatus.FAILED,
    },
    TaskStatus.PLANNING: {
        TaskStatus.WAITING_TOOL_RESULT,
        TaskStatus.WAITING_CLARIFICATION,
        TaskStatus.PRE_EXECUTION_CHECK,
        TaskStatus.SUCCEEDED,
        TaskStatus.FAILED,
    },
    TaskStatus.WAITING_TOOL_RESULT: {TaskStatus.VALIDATING_TOOL_RESULT},
    TaskStatus.VALIDATING_TOOL_RESULT: {
        TaskStatus.PLANNING,
        TaskStatus.PRE_EXECUTION_CHECK,
        TaskStatus.VERIFYING_FINAL_STATE,
        TaskStatus.RECOVERING,
        TaskStatus.WAITING_CLARIFICATION,
        TaskStatus.FAILED,
        TaskStatus.UNKNOWN,
    },
    TaskStatus.WAITING_CLARIFICATION: {TaskStatus.ANALYZING_CLARIFICATION},
    TaskStatus.ANALYZING_CLARIFICATION: {
        TaskStatus.PLANNING,
        TaskStatus.WAITING_CLARIFICATION,
        TaskStatus.FAILED,
    },
    TaskStatus.PRE_EXECUTION_CHECK: {
        TaskStatus.WAITING_TOOL_RESULT,
        TaskStatus.WAITING_CLARIFICATION,
        TaskStatus.FAILED,
    },
    TaskStatus.VERIFYING_FINAL_STATE: {
        TaskStatus.WAITING_TOOL_RESULT,
        TaskStatus.RECOVERING,
        TaskStatus.SUCCEEDED,
        TaskStatus.FAILED,
        TaskStatus.UNKNOWN,
    },
    TaskStatus.RECOVERING: {
        TaskStatus.WAITING_TOOL_RESULT,
        TaskStatus.WAITING_CLARIFICATION,
        TaskStatus.VERIFYING_FINAL_STATE,
        TaskStatus.FAILED,
        TaskStatus.UNKNOWN,
    },
}


class IllegalTransition(ValueError):
    pass


def can_transition(source: TaskStatus, target: TaskStatus) -> bool:
    return target in ALLOWED_TRANSITIONS.get(source, set())


def transition(
    task: TaskEntity, target: TaskStatus, reason: str
) -> tuple[TaskStatus, TaskStatus, str]:
    if not reason:
        raise ValueError("transition reason required")
    if not can_transition(task.current_state, target):
        raise IllegalTransition(f"{task.current_state}->{target}")
    old = task.current_state
    task.current_state = target
    task.updated_at = utc_now()
    if target in TERMINAL_STATES:
        task.final_status = target.value
    return old, target, reason
