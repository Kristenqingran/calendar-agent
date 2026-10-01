from datetime import date, datetime
from typing import get_args

import pytest
from pydantic import TypeAdapter, ValidationError

from calendar_agent_protocol.enums import (
    InboundMessageType,
    Intent,
    ObjectType,
    OperationStatus,
    Purpose,
    QueryScope,
    ResponseType,
    TaskStatus,
    Tool,
    ToolStatus,
)
from calendar_agent_protocol.types import (
    AllDayCalendarEvent,
    DefaultCalendar,
    ErrorModel,
    IanaTimezone,
    NonEmptyString,
    OffsetDateTime,
    ProtocolId,
    Reminder,
    StableId,
    TimeRange,
    TimedCalendarEvent,
)


@pytest.mark.parametrize(
    ("enum_type", "expected"),
    [
        (ObjectType, {"calendar_event", "reminder"}),
        (Intent, {"query", "create", "update", "delete"}),
        (
            Purpose,
            {
                "answer_query",
                "check_conflict",
                "detect_duplicate",
                "find_availability",
                "resolve_target",
                "verify_state",
            },
        ),
        (QueryScope, {"all_incomplete", "specific_list", "time_range"}),
        (ToolStatus, {"success", "failed", "unknown"}),
        (ResponseType, {"clarification", "final"}),
        (InboundMessageType, {"user_request", "clarification_response"}),
    ],
)
def test_frozen_enum_values(enum_type: type, expected: set[str]) -> None:
    assert {item.value for item in enum_type} == expected


def test_all_tool_and_status_values_are_snake_case() -> None:
    enum_types = (Tool, TaskStatus, OperationStatus)
    for enum_type in enum_types:
        assert all(
            value.value == value.value.lower() and " " not in value.value for value in enum_type
        )


@pytest.mark.parametrize("value", ["req_001", "conv_A-1", "task_x", "step_2", "op_retry_1"])
def test_protocol_id_accepts_valid_values(value: str) -> None:
    assert TypeAdapter(ProtocolId).validate_python(value) == value


@pytest.mark.parametrize("length", [3, 128])
def test_protocol_id_accepts_length_boundaries(length: int) -> None:
    value = "a_" + "x" * (length - 2)
    assert len(value) == length
    assert TypeAdapter(ProtocolId).validate_python(value) == value


@pytest.mark.parametrize(
    "value",
    [
        "x",
        "REQ_001",
        "no-space allowed",
        "_missingprefix",
        "a_" + "x" * 127,
    ],
)
def test_protocol_id_rejects_invalid_values(value: str) -> None:
    with pytest.raises(ValidationError):
        TypeAdapter(ProtocolId).validate_python(value)


def test_offset_datetime_requires_utc_offset() -> None:
    adapter = TypeAdapter(OffsetDateTime)
    assert adapter.validate_python("2026-09-05T15:00:00+08:00").utcoffset() is not None
    assert adapter.validate_python("2026-09-05T07:00:00Z").utcoffset() is not None
    with pytest.raises(ValidationError):
        adapter.validate_python("2026-09-05T15:00:00")
    with pytest.raises(ValidationError):
        adapter.validate_python("not-a-datetime")


def test_iana_timezone_is_registry_backed() -> None:
    adapter = TypeAdapter(IanaTimezone)
    assert adapter.validate_python("Asia/Shanghai") == "Asia/Shanghai"
    assert adapter.validate_python("America/New_York") == "America/New_York"
    with pytest.raises(ValidationError):
        adapter.validate_python("Mars/Olympus")
    with pytest.raises(ValidationError):
        adapter.validate_python("")


def test_time_range_requires_increasing_instants() -> None:
    valid = TimeRange(
        start=datetime.fromisoformat("2026-09-05T15:00:00+08:00"),
        end=datetime.fromisoformat("2026-09-05T16:00:00+08:00"),
    )
    assert valid.start < valid.end

    with pytest.raises(ValidationError):
        TimeRange(
            start=datetime.fromisoformat("2026-09-05T16:00:00+08:00"),
            end=datetime.fromisoformat("2026-09-05T15:00:00+08:00"),
        )
    with pytest.raises(ValidationError):
        TimeRange(
            start=datetime.fromisoformat("2026-09-05T15:00:00+08:00"),
            end=datetime.fromisoformat("2026-09-05T15:00:00+08:00"),
        )
    with pytest.raises(ValidationError):
        TimeRange(
            start=datetime.fromisoformat("2026-09-05T15:00:00"),
            end=datetime.fromisoformat("2026-09-05T16:00:00+08:00"),
        )


def test_stable_id_and_non_empty_string_require_content() -> None:
    assert TypeAdapter(StableId).validate_python("event_1") == "event_1"
    assert TypeAdapter(NonEmptyString).validate_python("title") == "title"
    with pytest.raises(ValidationError):
        TypeAdapter(StableId).validate_python("")
    with pytest.raises(ValidationError):
        TypeAdapter(NonEmptyString).validate_python("")


def test_strict_model_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError):
        TimeRange(
            start=datetime.fromisoformat("2026-09-05T15:00:00+08:00"),
            end=datetime.fromisoformat("2026-09-05T16:00:00+08:00"),
            unexpected=True,
        )


def test_default_calendar_validates_required_fields_and_nullable_id() -> None:
    calendar = DefaultCalendar(calendar_id=None, name="工作")
    assert calendar.calendar_id is None
    assert calendar.name == "工作"
    with pytest.raises(ValidationError):
        DefaultCalendar(calendar_id="calendar_1", name="")
    with pytest.raises(ValidationError):
        DefaultCalendar(name="工作")
    with pytest.raises(ValidationError):
        DefaultCalendar(calendar_id=None, name="工作", unexpected=True)


def test_error_model_validates_required_and_optional_fields() -> None:
    without_details = ErrorModel(code="failed", message="failed", retryable=True)
    with_details = ErrorModel(
        code="failed", message="failed", retryable=False, details={"reason": "timeout"}
    )
    assert without_details.details is None
    assert with_details.details == {"reason": "timeout"}
    with pytest.raises(ValidationError):
        ErrorModel(code="", message="failed", retryable=True)
    with pytest.raises(ValidationError):
        ErrorModel(code="failed", message="", retryable=True)
    with pytest.raises(ValidationError):
        ErrorModel(code="failed", message="failed", retryable=True, unexpected=True)


def test_timed_calendar_event_validates_mode_range_and_optional_fields() -> None:
    event = TimedCalendarEvent(
        event_id="event_1",
        title="Meeting",
        all_day=False,
        start=datetime.fromisoformat("2026-09-05T15:00:00+08:00"),
        end=datetime.fromisoformat("2026-09-05T16:00:00+08:00"),
        calendar_id="calendar_1",
        location="Room 1",
        notes="Bring notes",
    )
    assert event.all_day is False
    with pytest.raises(ValidationError):
        TimedCalendarEvent(
            event_id="event_1",
            title="Meeting",
            all_day=True,
            start=datetime.fromisoformat("2026-09-05T15:00:00+08:00"),
            end=datetime.fromisoformat("2026-09-05T16:00:00+08:00"),
        )
    for end in ["2026-09-05T15:00:00+08:00", "2026-09-05T14:00:00+08:00"]:
        with pytest.raises(ValidationError):
            TimedCalendarEvent(
                event_id="event_1",
                title="Meeting",
                all_day=False,
                start=datetime.fromisoformat("2026-09-05T15:00:00+08:00"),
                end=datetime.fromisoformat(end),
            )
    with pytest.raises(ValidationError):
        TimedCalendarEvent(
            event_id="event_1",
            title="Meeting",
            all_day=False,
            start=datetime.fromisoformat("2026-09-05T15:00:00+08:00"),
            end=datetime.fromisoformat("2026-09-05T16:00:00+08:00"),
            unexpected=True,
        )


def test_all_day_calendar_event_validates_mode_and_inclusive_dates() -> None:
    single_day = AllDayCalendarEvent(
        event_id="event_1",
        title="Holiday",
        all_day=True,
        start_date=date(2026, 9, 5),
        end_date=date(2026, 9, 5),
    )
    multi_day = AllDayCalendarEvent(
        event_id="event_2",
        title="Trip",
        all_day=True,
        start_date=date(2026, 9, 5),
        end_date=date(2026, 9, 7),
        calendar_id="calendar_1",
        location="Shanghai",
        notes="Travel",
    )
    assert single_day.start_date == single_day.end_date
    assert multi_day.start_date < multi_day.end_date
    with pytest.raises(ValidationError):
        AllDayCalendarEvent(
            event_id="event_1",
            title="Holiday",
            all_day=False,
            start_date=date(2026, 9, 5),
            end_date=date(2026, 9, 5),
        )
    with pytest.raises(ValidationError):
        AllDayCalendarEvent(
            event_id="event_1",
            title="Holiday",
            all_day=True,
            start_date=date(2026, 9, 7),
            end_date=date(2026, 9, 5),
        )
    with pytest.raises(ValidationError):
        AllDayCalendarEvent(
            event_id="event_1",
            title="Holiday",
            all_day=True,
            start_date=date(2026, 9, 5),
            end_date=date(2026, 9, 5),
            unexpected=True,
        )


def test_reminder_validates_required_and_optional_fields() -> None:
    without_time = Reminder(reminder_id="reminder_1", title="Call", completed=False)
    with_time = Reminder(
        reminder_id="reminder_2",
        title="Submit report",
        completed=True,
        list_id="list_1",
        reminder_time=datetime.fromisoformat("2026-09-05T18:00:00+08:00"),
        notes="Before dinner",
    )
    assert without_time.reminder_time is None
    assert with_time.completed is True
    with pytest.raises(ValidationError):
        Reminder(reminder_id="reminder_1", title="", completed=False)
    with pytest.raises(ValidationError):
        Reminder(reminder_id="reminder_1", title="Call", completed=False, unexpected=True)


def test_public_enum_type_list_is_not_empty() -> None:
    assert get_args(ProtocolId)


@pytest.mark.parametrize(
    ("definition", "enum_type"),
    [
        ("object", ObjectType),
        ("intent", Intent),
        ("purpose", Purpose),
        ("query_scope", QueryScope),
        ("tool", Tool),
        ("task_status", TaskStatus),
        ("tool_status", ToolStatus),
        ("operation_status", OperationStatus),
    ],
)
def test_python_enums_equal_frozen_schema_enums(
    definition: str,
    enum_type: type,
    schemas: dict[str, dict[str, object]],
) -> None:
    definitions = schemas["common-v1.schema.json"]["$defs"]
    assert isinstance(definitions, dict)
    schema_definition = definitions[definition]
    assert isinstance(schema_definition, dict)
    assert set(schema_definition["enum"]) == {item.value for item in enum_type}
