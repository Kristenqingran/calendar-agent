"""Single-request Tool Dispatcher and deterministic local adapters."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any, Protocol
from uuid import uuid4

from pydantic import TypeAdapter, ValidationError

from .enums import Tool
from .messages import ToolResult
from .runtime_contract import ToolAdapter
from .tools import ToolRequest


class ToolDispatchError(RuntimeError):
    """Raised when a dispatcher boundary or adapter response is invalid."""


class DispatcherAdapter(Protocol):
    def execute(self, request: ToolRequest) -> ToolResult: ...


class ToolDispatcher:
    """Dispatch exactly one already-validated request to one adapter."""

    def __init__(self, adapters: Mapping[Tool | str, DispatcherAdapter | ToolAdapter]):
        self.adapters = {Tool(tool): adapter for tool, adapter in adapters.items()}

    def dispatch(self, request: ToolRequest) -> ToolResult:
        validated = _validate_request(request)
        adapter = self.adapters.get(validated.tool)
        if adapter is None:
            return _failure(validated, "unsupported_operation", "当前 Tool 没有可用 Adapter。")
        try:
            result = adapter.execute(validated)
        except Exception as exc:
            return _failure(validated, "tool_execution_failed", str(exc) or "Tool 执行失败。")
        try:
            result = ToolResult.model_validate(result.model_dump(mode="json"))
        except (ValidationError, ValueError, TypeError, AttributeError) as exc:
            raise ToolDispatchError("adapter returned an invalid ToolResult") from exc
        _check_correlation(validated, result)
        return result


class MockToolAdapter:
    """Deterministic adapter for local boundary smoke tests only."""

    def __init__(self, *, fail_tools: set[Tool] | None = None):
        self.fail_tools = fail_tools or set()
        self.events: list[dict[str, Any]] = []

    def execute(self, request: ToolRequest) -> ToolResult:
        executed_at = datetime.now(UTC)
        if request.tool in self.fail_tools:
            return _failure(
                request, "tool_execution_failed", "Mock Adapter configured to fail."
            , executed_at=executed_at)
        if request.tool == Tool.CREATE_CALENDAR_EVENT:
            event = {"event_id": "event_mock_001", "title": request.arguments.title,
                     "start": request.arguments.start, "end": request.arguments.end}
            self.events.append(event)
            return ToolResult(
                type="tool_result", execution_id=request.execution_id,
                causation_request_id=request.causation_request_id,
                conversation_id=request.conversation_id, task_id=request.task_id,
                step_id=request.step_id, tool=request.tool, status="success",
                executed_at=executed_at, operation_id=request.operation_id,
                result={"event_id": "event_mock_001"},
            )
        if request.tool == Tool.QUERY_CALENDAR:
            args = request.arguments
            queried_range = None
            if args.start is not None and args.end is not None:
                queried_range = {"start": args.start, "end": args.end}
            return ToolResult(
                type="tool_result", execution_id=request.execution_id,
                causation_request_id=request.causation_request_id,
                conversation_id=request.conversation_id, task_id=request.task_id,
                step_id=request.step_id, tool=request.tool, status="success",
                executed_at=executed_at, queried_range=queried_range,
                fetched_at=executed_at,
                results=[event for event in self.events if _matches_query(event, args)],
            )
        return _failure(request, "unsupported_operation", "Mock Adapter 不支持该 Tool。", executed_at=executed_at)


def _validate_request(request: ToolRequest) -> ToolRequest:
    try:
        return TypeAdapter(ToolRequest).validate_python(request)
    except ValidationError as exc:
        raise ToolDispatchError("ToolRequest does not match its contract") from exc


def _matches_query(event: dict[str, Any], args: Any) -> bool:
    if args.target_id is not None and event["event_id"] != args.target_id:
        return False
    if args.start is not None and event["start"] != args.start:
        return False
    if args.end is not None and event["end"] != args.end:
        return False
    return True


def _check_correlation(request: ToolRequest, result: ToolResult) -> None:
    for name in ("execution_id", "causation_request_id", "conversation_id", "task_id", "step_id", "tool"):
        if getattr(result, name) != getattr(request, name):
            raise ToolDispatchError(f"ToolResult {name} correlation mismatch")
    if request.tool.is_write and result.operation_id != request.operation_id:
        raise ToolDispatchError("ToolResult operation_id correlation mismatch")
    if not request.tool.is_write and result.operation_id is not None:
        raise ToolDispatchError("query ToolResult must not contain operation_id")
    if result.operation_id != getattr(request, "operation_id", None):
        raise ToolDispatchError("ToolResult operation_id correlation mismatch")


def _failure(request: ToolRequest, code: str, message: str, *,
             executed_at: datetime | None = None) -> ToolResult:
    return ToolResult(
        type="tool_result", execution_id=request.execution_id,
        causation_request_id=request.causation_request_id,
        conversation_id=request.conversation_id, task_id=request.task_id,
        step_id=request.step_id, tool=request.tool, status="failed",
        executed_at=executed_at or datetime.now(UTC),
        operation_id=request.operation_id if request.tool.is_write else None,
        error={"code": code, "message": message, "retryable": False},
    )


__all__ = ["MockToolAdapter", "ToolDispatchError", "ToolDispatcher"]
