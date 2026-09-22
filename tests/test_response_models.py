import pytest
from pydantic import TypeAdapter, ValidationError

from calendar_agent_protocol.messages import AgentResponse


def parse(payload: dict[str, object]) -> object:
    return TypeAdapter(AgentResponse).validate_python(payload)


BASE = {
    "type": "tool_request",
    "request_id": "req_001",
    "conversation_id": "conv_001",
    "task_id": "task_001",
    "step_id": "step_001",
}


def test_query_tool_request_has_no_operation_id() -> None:
    parsed = parse(
        BASE
        | {
            "tool": "query_calendar",
            "purpose": "answer_query",
            "arguments": {
                "start": "2026-09-05T12:00:00+08:00",
                "end": "2026-09-05T18:00:00+08:00",
            },
        }
    )
    assert parsed.tool == "query_calendar"  # type: ignore[union-attr]


def test_query_tool_request_rejects_operation_id() -> None:
    with pytest.raises(ValidationError):
        parse(
            BASE
            | {
                "operation_id": "op_001",
                "tool": "query_calendar",
                "purpose": "answer_query",
                "arguments": {},
            }
        )


def test_write_tool_request_requires_operation_id() -> None:
    with pytest.raises(ValidationError):
        parse(
            BASE
            | {
                "tool": "delete_calendar_event",
                "arguments": {"event_id": "event_123"},
            }
        )


def test_clarification_candidates() -> None:
    parsed = parse(
        {
            "type": "clarification",
            "request_id": "req_001",
            "conversation_id": "conv_001",
            "task_id": "task_001",
            "step_id": "step_004",
            "reason": "ambiguous_target",
            "message": "你指哪一个？",
            "expected_answer": {"type": "candidate_index"},
            "candidates": [{"event_id": "event_1"}, {"event_id": "event_2"}],
        }
    )
    assert len(parsed.candidates or []) == 2  # type: ignore[union-attr]


@pytest.mark.parametrize("status", ["success", "unknown"])
def test_final_success_and_unknown(status: str) -> None:
    parsed = parse(
        {
            "type": "final",
            "request_id": "req_001",
            "conversation_id": "conv_001",
            "task_id": "task_001",
            "status": status,
            "message": "处理完成" if status == "success" else "目前无法确认结果",
        }
    )
    assert parsed.status == status  # type: ignore[union-attr]


def test_final_failure_requires_error() -> None:
    with pytest.raises(ValidationError):
        parse(
            {
                "type": "final",
                "request_id": "req_001",
                "conversation_id": "conv_001",
                "task_id": "task_001",
                "status": "failure",
                "message": "没有完成",
            }
        )


def test_unsupported_operation_failure() -> None:
    parsed = parse(
        {
            "type": "final",
            "request_id": "req_001",
            "conversation_id": "conv_001",
            "task_id": "task_001",
            "status": "failure",
            "message": "V1 暂不支持批量删除。",
            "error": {
                "code": "unsupported_operation",
                "message": "批量删除不受支持",
                "retryable": False,
            },
        }
    )
    assert parsed.error is not None  # type: ignore[union-attr]
    assert parsed.error.code == "unsupported_operation"  # type: ignore[union-attr]
