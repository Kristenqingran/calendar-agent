from datetime import datetime
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
from calendar_agent_protocol.types import IanaTimezone, OffsetDateTime, ProtocolId, TimeRange


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
        (ResponseType, {"tool_request", "clarification", "final"}),
        (InboundMessageType, {"user_request", "clarification_response", "tool_result"}),
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


@pytest.mark.parametrize("value", ["x", "REQ_001", "no-space allowed", "_missingprefix"])
def test_protocol_id_rejects_invalid_values(value: str) -> None:
    with pytest.raises(ValidationError):
        TypeAdapter(ProtocolId).validate_python(value)


def test_offset_datetime_requires_utc_offset() -> None:
    adapter = TypeAdapter(OffsetDateTime)
    assert adapter.validate_python("2026-09-05T15:00:00+08:00").utcoffset() is not None
    with pytest.raises(ValidationError):
        adapter.validate_python("2026-09-05T15:00:00")


def test_iana_timezone_is_registry_backed() -> None:
    adapter = TypeAdapter(IanaTimezone)
    assert adapter.validate_python("Asia/Shanghai") == "Asia/Shanghai"
    with pytest.raises(ValidationError):
        adapter.validate_python("Mars/Olympus")


def test_time_range_requires_increasing_instants() -> None:
    with pytest.raises(ValidationError):
        TimeRange(
            start=datetime.fromisoformat("2026-09-05T16:00:00+08:00"),
            end=datetime.fromisoformat("2026-09-05T15:00:00+08:00"),
        )


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
