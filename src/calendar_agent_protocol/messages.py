from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import Field, model_validator

from .enums import ClarificationReason, FinalStatus, QueryScope, Tool, ToolStatus
from .tools import ToolRequest
from .types import (
    DefaultCalendar,
    ErrorModel,
    ExecutionId,
    CauseRequestId,
    IanaTimezone,
    NonEmptyString,
    OffsetDateTime,
    OperationId,
    ProtocolId,
    StrictModel,
    TimeRange,
)


class UserRequest(StrictModel):
    type: Literal["user_request"]
    request_id: ProtocolId
    conversation_id: ProtocolId
    message: NonEmptyString
    current_time: OffsetDateTime
    assistant_timezone: IanaTimezone
    source: NonEmptyString
    device_timezone: IanaTimezone | None = None
    default_calendar: DefaultCalendar | None = None


class ClarificationResponse(StrictModel):
    type: Literal["clarification_response"]
    request_id: ProtocolId
    conversation_id: ProtocolId
    task_id: ProtocolId
    reply_to_step_id: ProtocolId
    message: NonEmptyString


class ToolResult(StrictModel):
    type: Literal["tool_result"]
    execution_id: ExecutionId
    causation_request_id: CauseRequestId
    conversation_id: ProtocolId
    task_id: ProtocolId
    step_id: ProtocolId
    tool: Tool
    status: ToolStatus
    executed_at: OffsetDateTime
    operation_id: OperationId | None = None
    queried_range: TimeRange | None = None
    query_scope: QueryScope | None = None
    fetched_at: OffsetDateTime | None = None
    results: list[dict[str, Any]] | None = None
    result: dict[str, Any] | None = None
    error: ErrorModel | None = None

    @model_validator(mode="after")
    def validate_by_tool_and_status(self) -> ToolResult:
        if self.tool.is_write and self.operation_id is None:
            raise ValueError("write tool result requires operation_id")
        if self.status in {ToolStatus.FAILED, ToolStatus.UNKNOWN} and self.error is None:
            raise ValueError("failed or unknown tool result requires error")

        if self.status == ToolStatus.SUCCESS:
            if self.tool == Tool.QUERY_CALENDAR:
                if self.queried_range is None or self.fetched_at is None or self.results is None:
                    raise ValueError(
                        "successful Calendar query requires queried_range, fetched_at, and results"
                    )
            elif self.tool == Tool.QUERY_REMINDERS:
                if self.query_scope is None or self.fetched_at is None or self.results is None:
                    raise ValueError(
                        "successful Reminder query requires query_scope, fetched_at, and results"
                    )
                if self.query_scope == QueryScope.TIME_RANGE and self.queried_range is None:
                    raise ValueError("time_range Reminder query requires queried_range")
            elif self.result is None:
                raise ValueError("successful write tool result requires result")
        return self


InboundMessage = Annotated[
    UserRequest | ClarificationResponse,
    Field(discriminator="type"),
]


class Clarification(StrictModel):
    type: Literal["clarification"]
    request_id: ProtocolId
    conversation_id: ProtocolId
    task_id: ProtocolId
    step_id: ProtocolId
    reason: ClarificationReason
    message: NonEmptyString
    expected_answer: dict[str, Any] = Field(min_length=1)
    missing_fields: list[str] | None = None
    ambiguous_fields: list[str] | None = None
    candidates: list[dict[str, Any]] | None = None


class Final(StrictModel):
    type: Literal["final"]
    request_id: ProtocolId
    conversation_id: ProtocolId
    task_id: ProtocolId
    status: FinalStatus
    message: NonEmptyString
    result_summary: dict[str, Any] | None = None
    error: ErrorModel | None = None

    @model_validator(mode="after")
    def failure_requires_error(self) -> Final:
        if self.status == FinalStatus.FAILURE and self.error is None:
            raise ValueError("failure final requires error")
        return self


AgentResponse = Clarification | Final
RuntimeDecision = ToolRequest | AgentResponse
RuntimeMessage = InboundMessage | ToolResult
