from datetime import UTC, datetime

import pytest
from pydantic import TypeAdapter

from calendar_agent_protocol.dispatcher import MockToolAdapter, ToolDispatchError, ToolDispatcher
from calendar_agent_protocol.enums import Tool
from calendar_agent_protocol.messages import ToolResult
from calendar_agent_protocol.tools import (
    CreateCalendarEventRequest,
    QueryCalendarRequest,
)


def create_request() -> CreateCalendarEventRequest:
    return CreateCalendarEventRequest(
        type="tool_request", execution_id="exec_001", causation_request_id="req_001", conversation_id="conv_001",
        task_id="task_001", step_id="step_001", operation_id="op_001",
        tool="create_calendar_event", arguments={
            "title": "会议", "all_day": False,
            "start": "2026-09-25T15:00:00+08:00",
            "end": "2026-09-25T16:00:00+08:00",
        },
    )


def query_request() -> QueryCalendarRequest:
    return QueryCalendarRequest(
        type="tool_request", execution_id="exec_002", causation_request_id="req_002", conversation_id="conv_001",
        task_id="task_001", step_id="step_002", purpose="answer_query",
        tool="query_calendar", arguments={
            "start": "2026-09-25T15:00:00+08:00",
            "end": "2026-09-25T16:00:00+08:00",
        },
    )


def test_create_dispatches_to_mock_and_preserves_correlation():
    result = ToolDispatcher({Tool.CREATE_CALENDAR_EVENT: MockToolAdapter()}).dispatch(create_request())
    assert isinstance(result, ToolResult)
    assert result.status == "success"
    assert result.operation_id == "op_001"
    assert result.conversation_id == "conv_001"
    assert result.task_id == "task_001"
    assert result.step_id == "step_001"
    assert result.execution_id == "exec_001"
    assert result.causation_request_id == "req_001"
    assert result.result == {"event_id": "event_mock_001"}


def test_query_dispatches_without_operation_id():
    result = ToolDispatcher({Tool.QUERY_CALENDAR: MockToolAdapter()}).dispatch(query_request())
    assert result.status == "success"
    assert result.operation_id is None
    assert result.queried_range is not None
    assert result.fetched_at is not None
    assert result.results == []


def test_unsupported_tool_returns_failed_result():
    result = ToolDispatcher({}).dispatch(create_request())
    assert result.status == "failed"
    assert result.error is not None
    assert result.error.code == "unsupported_operation"
    assert result.operation_id == "op_001"


def test_adapter_failure_returns_failed_result():
    result = ToolDispatcher({
        Tool.CREATE_CALENDAR_EVENT: MockToolAdapter(fail_tools={Tool.CREATE_CALENDAR_EVENT})
    }).dispatch(create_request())
    assert result.status == "failed"
    assert result.error is not None
    assert result.error.code == "tool_execution_failed"
    assert result.operation_id == "op_001"


def test_results_are_validated_by_existing_tool_result_contract():
    result = ToolDispatcher({Tool.CREATE_CALENDAR_EVENT: MockToolAdapter()}).dispatch(create_request())
    TypeAdapter(ToolResult).validate_python(result)


def test_dispatcher_does_not_change_request_arguments():
    request = create_request()
    original = request.arguments.model_dump(mode="json")
    ToolDispatcher({Tool.CREATE_CALENDAR_EVENT: MockToolAdapter()}).dispatch(request)
    assert request.arguments.model_dump(mode="json") == original


def test_adapter_invalid_result_is_not_silently_accepted():
    class InvalidAdapter:
        def execute(self, request):
            return {"type": "tool_result"}

    with pytest.raises(ToolDispatchError, match="invalid ToolResult"):
        ToolDispatcher({Tool.CREATE_CALENDAR_EVENT: InvalidAdapter()}).dispatch(create_request())
