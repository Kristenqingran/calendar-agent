from copy import deepcopy

import pytest
from pydantic import TypeAdapter, ValidationError

from calendar_agent_protocol.messages import AgentResponse, InboundMessage, ToolResult
from calendar_agent_protocol.tools import ToolRequest


HTTP_REQUEST_ID = "req_http_001"


def tool_request_payload(*, execution_id: str = "exec_001") -> dict[str, object]:
    return {
        "type": "tool_request",
        "execution_id": execution_id,
        "causation_request_id": HTTP_REQUEST_ID,
        "conversation_id": "conv_001",
        "task_id": "task_001",
        "step_id": "step_001",
        "operation_id": "op_001",
        "tool": "create_calendar_event",
        "arguments": {
            "title": "QA meeting",
            "all_day": False,
            "start": "2026-10-01T15:00:00+08:00",
            "end": "2026-10-01T16:00:00+08:00",
        },
    }


def test_internal_tool_request_uses_execution_identity_not_http_request_identity() -> None:
    payload = tool_request_payload()

    request = TypeAdapter(ToolRequest).validate_python(payload)

    assert request.execution_id == "exec_001"
    assert request.causation_request_id == HTTP_REQUEST_ID
    assert request.operation_id == "op_001"
    legacy_payload = deepcopy(payload)
    legacy_payload.pop("execution_id")
    legacy_payload.pop("causation_request_id")
    legacy_payload["request_id"] = "req_tool_001"
    with pytest.raises(ValidationError):
        TypeAdapter(ToolRequest).validate_python(legacy_payload)


def test_internal_tool_result_correlates_to_execution_and_logical_operation() -> None:
    request = TypeAdapter(ToolRequest).validate_python(tool_request_payload())
    result = ToolResult.model_validate(
        {
            "type": "tool_result",
            "execution_id": request.execution_id,
            "causation_request_id": request.causation_request_id,
            "conversation_id": request.conversation_id,
            "task_id": request.task_id,
            "step_id": request.step_id,
            "operation_id": request.operation_id,
            "tool": request.tool,
            "status": "success",
            "executed_at": "2026-09-30T12:00:00Z",
            "result": {"event_id": "event_001"},
        }
    )

    assert result.execution_id == "exec_001"
    assert result.causation_request_id == HTTP_REQUEST_ID
    assert result.operation_id == "op_001"
    stale = result.model_dump(mode="json") | {"execution_id": "exec_stale"}
    from calendar_agent_protocol.dispatcher import ToolDispatchError, ToolDispatcher
    with pytest.raises(ToolDispatchError, match="execution_id correlation mismatch"):
        from calendar_agent_protocol.enums import Tool

        class EchoAdapter:
            def execute(self, _request):
                return ToolResult.model_validate(stale)

        ToolDispatcher({Tool.CREATE_CALENDAR_EVENT: EchoAdapter()}).dispatch(request)


def test_tool_execution_messages_are_not_public_http_messages() -> None:
    inbound = {
        "type": "tool_result",
        "execution_id": "exec_001",
        "causation_request_id": HTTP_REQUEST_ID,
        "conversation_id": "conv_001",
        "task_id": "task_001",
        "step_id": "step_001",
        "operation_id": "op_001",
        "tool": "create_calendar_event",
        "status": "failed",
        "executed_at": "2026-09-30T12:00:00Z",
        "error": {"code": "failed", "message": "failed", "retryable": False},
    }
    response = tool_request_payload()

    with pytest.raises(ValidationError):
        TypeAdapter(InboundMessage).validate_python(inbound)
    with pytest.raises(ValidationError):
        TypeAdapter(AgentResponse).validate_python(response)


def test_operation_retry_keeps_operation_id_and_uses_new_execution_id() -> None:
    first = TypeAdapter(ToolRequest).validate_python(tool_request_payload(execution_id="exec_001"))
    retry = TypeAdapter(ToolRequest).validate_python(tool_request_payload(execution_id="exec_002"))

    assert first.operation_id == retry.operation_id == "op_001"
    assert first.execution_id != retry.execution_id
