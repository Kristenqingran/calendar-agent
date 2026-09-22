from copy import deepcopy

import pytest
from pydantic import TypeAdapter, ValidationError

from calendar_agent_protocol.messages import AgentResponse

BASE = {
    "type": "tool_request",
    "request_id": "req_001",
    "conversation_id": "conv_001",
    "task_id": "task_001",
    "step_id": "step_001",
}


@pytest.mark.parametrize(
    ("tool", "arguments"),
    [
        (
            "query_calendar",
            {"start": "2026-09-05T15:00:00+08:00", "end": "2026-09-05T16:00:00+08:00"},
        ),
        ("query_reminders", {"query_scope": "all_incomplete"}),
        ("query_reminders", {"query_scope": "specific_list", "list_id": "list_123"}),
        (
            "query_reminders",
            {
                "query_scope": "time_range",
                "start": "2026-09-05T00:00:00+08:00",
                "end": "2026-09-06T00:00:00+08:00",
            },
        ),
    ],
)
def test_query_tool_contracts(tool: str, arguments: dict[str, object]) -> None:
    payload = BASE | {"tool": tool, "purpose": "answer_query", "arguments": arguments}
    assert TypeAdapter(AgentResponse).validate_python(payload)


@pytest.mark.parametrize(
    ("tool", "arguments"),
    [
        (
            "create_calendar_event",
            {
                "title": "客户会议",
                "all_day": False,
                "start": "2026-09-05T15:00:00+08:00",
                "end": "2026-09-05T16:00:00+08:00",
                "calendar_id": "cal_123",
            },
        ),
        (
            "create_calendar_event",
            {
                "title": "休假",
                "all_day": True,
                "start_date": "2026-09-05",
                "end_date": "2026-09-05",
                "calendar_id": None,
                "calendar_name": "生活",
            },
        ),
        (
            "update_calendar_event",
            {"event_id": "event_123", "changes": {"title": "客户复盘"}},
        ),
        ("delete_calendar_event", {"event_id": "event_123"}),
        (
            "create_reminder",
            {"title": "交报告", "reminder_time": "2026-09-05T17:00:00+08:00"},
        ),
        (
            "update_reminder",
            {"reminder_id": "rem_123", "changes": {"completed": True}},
        ),
        ("delete_reminder", {"reminder_id": "rem_123"}),
    ],
)
def test_write_tool_contracts(tool: str, arguments: dict[str, object]) -> None:
    payload = BASE | {
        "operation_id": "op_001",
        "tool": tool,
        "arguments": arguments,
    }
    assert TypeAdapter(AgentResponse).validate_python(payload)


def test_timed_event_cannot_use_all_day_fields() -> None:
    payload = BASE | {
        "operation_id": "op_001",
        "tool": "create_calendar_event",
        "arguments": {
            "title": "会议",
            "all_day": False,
            "start_date": "2026-09-05",
            "end_date": "2026-09-05",
        },
    }
    with pytest.raises(ValidationError):
        TypeAdapter(AgentResponse).validate_python(payload)


def test_all_day_event_cannot_use_timed_fields() -> None:
    payload = BASE | {
        "operation_id": "op_001",
        "tool": "create_calendar_event",
        "arguments": {
            "title": "休假",
            "all_day": True,
            "start": "2026-09-05T00:00:00+08:00",
            "end": "2026-09-06T00:00:00+08:00",
        },
    }
    with pytest.raises(ValidationError):
        TypeAdapter(AgentResponse).validate_python(payload)


def test_calendar_name_is_not_accepted_as_calendar_id_substitute() -> None:
    payload = BASE | {
        "operation_id": "op_001",
        "tool": "create_calendar_event",
        "arguments": {
            "title": "会议",
            "all_day": False,
            "start": "2026-09-05T15:00:00+08:00",
            "end": "2026-09-05T16:00:00+08:00",
            "calendar_name": "工作",
        },
    }
    parsed = TypeAdapter(AgentResponse).validate_python(payload)
    assert parsed.arguments.calendar_id is None  # type: ignore[union-attr]
    assert parsed.arguments.calendar_name == "工作"  # type: ignore[union-attr]


def test_update_requires_stable_target_id() -> None:
    payload = BASE | {
        "operation_id": "op_001",
        "tool": "update_calendar_event",
        "arguments": {"changes": {"title": "改名"}},
    }
    with pytest.raises(ValidationError):
        TypeAdapter(AgentResponse).validate_python(payload)


def test_delete_requires_stable_target_id() -> None:
    payload = BASE | {
        "operation_id": "op_001",
        "tool": "delete_reminder",
        "arguments": {"title": "交报告"},
    }
    with pytest.raises(ValidationError):
        TypeAdapter(AgentResponse).validate_python(payload)


def test_extra_fields_are_rejected() -> None:
    payload = deepcopy(BASE)
    payload.update(
        {
            "tool": "query_reminders",
            "purpose": "answer_query",
            "arguments": {"query_scope": "all_incomplete", "start": "2026-09-05"},
        }
    )
    with pytest.raises(ValidationError):
        TypeAdapter(AgentResponse).validate_python(payload)
