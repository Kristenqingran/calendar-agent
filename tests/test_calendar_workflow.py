from types import SimpleNamespace

from calendar_agent_protocol.calendar_workflow import CalendarWorkflow
from calendar_agent_protocol.enums import Intent, ObjectType
from calendar_agent_protocol.messages import Clarification, Final
from calendar_agent_protocol.planning import Planner
from calendar_agent_protocol.tools import CreateCalendarEventRequest, QueryCalendarRequest


def parameter(value, status="valid"):
    return SimpleNamespace(value=value, status=status)


def task(intent, parameters):
    return SimpleNamespace(object="calendar_event", intent=intent, parameters=parameters)


def ids():
    return dict(request_id="req_001", conversation_id="conv_001", task_id="task_001", step_id="step_001")


def test_calendar_create():
    result = CalendarWorkflow().plan(**ids(), task=task("create", {
        "title": parameter("QA event"), "start": parameter("2026-09-25T15:00:00+08:00"),
        "end": parameter("2026-09-25T16:00:00+08:00"),
    }))
    assert isinstance(result, CreateCalendarEventRequest)
    assert result.arguments.title == "QA event"
    assert result.arguments.all_day is False
    assert result.operation_id.startswith("op_")


def test_calendar_query_has_no_operation_id():
    result = CalendarWorkflow().plan(**ids(), task=task("query", {
        "start": parameter("2026-09-25T15:00:00+08:00"),
        "end": parameter("2026-09-25T16:00:00+08:00"),
    }))
    assert isinstance(result, QueryCalendarRequest)
    assert not hasattr(result, "operation_id")


def test_missing_or_ambiguous_parameter_is_planned_as_clarification():
    for status in ("missing", "ambiguous"):
        task_value = SimpleNamespace(
            object=ObjectType.CALENDAR_EVENT,
            intent=Intent.CREATE,
            batch_write=False,
            parameters={
                "title": parameter("QA"),
                "start": parameter(None, status),
            },
        )
        analysis = SimpleNamespace(
            needs_clarification=False,
            tasks=[task_value],
            clarification=None,
        )
        result = Planner().plan(**ids(), analysis=analysis)
        assert isinstance(result, Clarification)
        assert "start" in result.missing_fields


def test_all_day_event():
    result = CalendarWorkflow().plan(**ids(), task=task("create", {
        "title": parameter("Holiday"), "all_day": parameter(True),
        "start_date": parameter("2026-09-25"), "end_date": parameter("2026-09-25"),
    }))
    assert isinstance(result, CreateCalendarEventRequest)
    assert result.arguments.all_day is True
    assert result.arguments.start_date.isoformat() == "2026-09-25"


def test_unsupported_calendar_operation_returns_failure():
    result = CalendarWorkflow().plan(**ids(), task=task("update", {}))
    assert isinstance(result, Final)
    assert result.error.code == "unsupported_operation"
