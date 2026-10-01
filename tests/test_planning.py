from types import SimpleNamespace

import pytest

from calendar_agent_protocol.messages import Clarification, Final
from calendar_agent_protocol.planning import Planner, PlanningError
from calendar_agent_protocol.tools import (
    CreateCalendarEventRequest,
    CreateReminderRequest,
    QueryCalendarRequest,
)


def parameter(value, status="valid"):
    return SimpleNamespace(value=value, status=status)


def task(object_, intent, parameters, batch_write=False):
    return SimpleNamespace(object=object_, intent=intent, parameters=parameters, batch_write=batch_write)


def analysis(task_value, needs_clarification=False, clarification=None):
    return SimpleNamespace(tasks=[task_value], needs_clarification=needs_clarification, clarification=clarification)


def ids():
    return dict(request_id="req_001", conversation_id="conv_001", task_id="task_001", step_id="step_001")


def test_calendar_create_returns_contract_valid_tool_request():
    result = Planner().plan(**ids(), analysis=analysis(task("calendar_event", "create", {
        "title": parameter("会议"), "start": parameter("2026-09-25T15:00:00+08:00"),
        "end": parameter("2026-09-25T16:00:00+08:00"),
    })))
    assert isinstance(result, CreateCalendarEventRequest)
    assert result.tool == "create_calendar_event"
    assert result.operation_id


def test_reminder_create_requires_calendar_reasonableness_context():
    value = analysis(task("reminder", "create", {
        "title": parameter("缴费"), "reminder_time": parameter("2026-09-25T09:00:00+08:00"),
    }))
    with pytest.raises(PlanningError, match="reasonableness"):
        Planner().plan(**ids(), analysis=value)
    result = Planner().plan(**ids(), analysis=value, context={"calendar_reasonableness_verified": True})
    assert isinstance(result, CreateReminderRequest)
    assert result.tool == "create_reminder"


def test_missing_or_ambiguous_parameter_returns_clarification():
    for status in ("missing", "ambiguous"):
        result = Planner().plan(**ids(), analysis=analysis(task("calendar_event", "create", {
            "title": parameter("会议"), "start": parameter(None, status),
        })))
        assert isinstance(result, Clarification)


def test_explicit_llm_clarification_is_preserved():
    details = SimpleNamespace(reason="ambiguous_parameter", message="请确认时间", fields=["start"], expected_answer_type="datetime")
    result = Planner().plan(**ids(), analysis=analysis(task("calendar_event", "create", {}), True, details))
    assert isinstance(result, Clarification)
    assert result.ambiguous_fields == ["start"]


def test_unsupported_operation_returns_protocol_failure():
    result = Planner().plan(**ids(), analysis=analysis(task("calendar_event", "update", {})))
    assert isinstance(result, Final)
    assert result.error.code == "unsupported_operation"


def test_query_has_no_operation_id_and_write_has_one():
    query = Planner().plan(**ids(), analysis=analysis(task("calendar_event", "query", {
        "start": parameter("2026-09-25T15:00:00+08:00"),
        "end": parameter("2026-09-25T16:00:00+08:00"),
    })))
    assert isinstance(query, QueryCalendarRequest)
    assert not hasattr(query, "operation_id")
    write = Planner().plan(**ids(), analysis=analysis(task("calendar_event", "create", {
        "title": parameter("会议"), "start": parameter("2026-09-25T15:00:00+08:00"),
        "end": parameter("2026-09-25T16:00:00+08:00"),
    })))
    assert isinstance(write, CreateCalendarEventRequest)
    assert write.operation_id
