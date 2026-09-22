from copy import deepcopy

import pytest
from pydantic import TypeAdapter, ValidationError

from calendar_agent_protocol.messages import InboundMessage, ToolResult, UserRequest

USER_REQUEST = {
    "type": "user_request",
    "request_id": "req_001",
    "conversation_id": "conv_001",
    "message": "明天下午三点有什么安排？",
    "current_time": "2026-09-04T10:00:00+08:00",
    "assistant_timezone": "Asia/Shanghai",
    "source": "iphone_shortcut",
    "default_calendar": {"calendar_id": None, "name": "日历"},
}


def test_user_request_valid() -> None:
    parsed = TypeAdapter(InboundMessage).validate_python(USER_REQUEST)
    assert isinstance(parsed, UserRequest)


@pytest.mark.parametrize("field", ["message", "current_time", "assistant_timezone", "source"])
def test_user_request_required_fields(field: str) -> None:
    payload = deepcopy(USER_REQUEST)
    del payload[field]
    with pytest.raises(ValidationError):
        TypeAdapter(InboundMessage).validate_python(payload)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("type", "request"),
        ("request_id", "bad id"),
        ("assistant_timezone", "Mars/Olympus"),
        ("current_time", "2026-09-04T10:00:00"),
    ],
)
def test_user_request_rejects_invalid_values(field: str, value: str) -> None:
    payload = deepcopy(USER_REQUEST)
    payload[field] = value
    with pytest.raises(ValidationError):
        TypeAdapter(InboundMessage).validate_python(payload)


def test_clarification_response_valid() -> None:
    parsed = TypeAdapter(InboundMessage).validate_python(
        {
            "type": "clarification_response",
            "request_id": "req_002",
            "conversation_id": "conv_001",
            "task_id": "task_001",
            "reply_to_step_id": "step_004",
            "message": "一个小时",
        }
    )
    assert parsed.type == "clarification_response"


def test_write_tool_result_requires_operation_id() -> None:
    with pytest.raises(ValidationError):
        ToolResult.model_validate(
            {
                "type": "tool_result",
                "request_id": "req_003",
                "conversation_id": "conv_001",
                "task_id": "task_001",
                "step_id": "step_005",
                "tool": "create_reminder",
                "status": "success",
                "executed_at": "2026-09-04T10:00:02+08:00",
                "result": {"reminder_id": "rem_123"},
            }
        )


@pytest.mark.parametrize("scope", ["all_incomplete", "specific_list"])
def test_successful_non_time_range_reminder_result_needs_no_range(scope: str) -> None:
    result = ToolResult.model_validate(
        {
            "type": "tool_result",
            "request_id": "req_003",
            "conversation_id": "conv_001",
            "task_id": "task_001",
            "step_id": "step_005",
            "tool": "query_reminders",
            "status": "success",
            "executed_at": "2026-09-04T10:00:02+08:00",
            "fetched_at": "2026-09-04T10:00:02+08:00",
            "query_scope": scope,
            "results": [],
        }
    )
    assert result.queried_range is None


def test_successful_time_range_reminder_result_requires_range() -> None:
    with pytest.raises(ValidationError):
        ToolResult.model_validate(
            {
                "type": "tool_result",
                "request_id": "req_003",
                "conversation_id": "conv_001",
                "task_id": "task_001",
                "step_id": "step_005",
                "tool": "query_reminders",
                "status": "success",
                "executed_at": "2026-09-04T10:00:02+08:00",
                "fetched_at": "2026-09-04T10:00:02+08:00",
                "query_scope": "time_range",
                "results": [],
            }
        )


def test_failed_query_with_empty_results_is_still_failed() -> None:
    result = ToolResult.model_validate(
        {
            "type": "tool_result",
            "request_id": "req_003",
            "conversation_id": "conv_001",
            "task_id": "task_001",
            "step_id": "step_005",
            "tool": "query_calendar",
            "status": "failed",
            "executed_at": "2026-09-04T10:00:02+08:00",
            "results": [],
            "error": {"code": "permission_denied", "message": "拒绝访问", "retryable": False},
        }
    )
    assert result.status == "failed"
