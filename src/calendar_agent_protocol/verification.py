"""Final-state verification for the supported Calendar create flow."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import uuid4

from pydantic import TypeAdapter

from .enums import Purpose, Tool
from .messages import ToolResult
from .tools import QueryCalendarRequest, ToolRequest


@dataclass(frozen=True)
class VerificationDecision:
    status: str
    message: str


class VerificationService:
    """Build and evaluate verification requests without executing tools."""

    def build_calendar_create_query(
        self, create_request: ToolRequest, create_result: ToolResult, step_id: str
    ) -> QueryCalendarRequest:
        arguments = create_request.arguments
        payload: dict[str, Any] = {
            "start": arguments.start, "end": arguments.end,
            "candidate": {"title": arguments.title},
        }
        event_id = (create_result.result or {}).get("event_id")
        if event_id:
            payload["target_id"] = event_id
        return TypeAdapter(ToolRequest).validate_python({
            "type": "tool_request", "execution_id": f"exec_{uuid4().hex}",
            "causation_request_id": create_request.causation_request_id,
            "conversation_id": create_request.conversation_id,
            "task_id": create_request.task_id, "step_id": step_id,
            "tool": Tool.QUERY_CALENDAR, "purpose": Purpose.VERIFY_STATE,
            "arguments": payload,
        })

    def evaluate_calendar_create(
        self, create_request: ToolRequest, create_result: ToolResult, query_result: ToolResult
    ) -> VerificationDecision:
        if query_result.status.value != "success":
            return VerificationDecision("unknown", "无法通过 Calendar 查询确认事件状态。")
        events = query_result.results or []
        expected = create_request.arguments
        event_id = (create_result.result or {}).get("event_id")
        for event in events:
            if event_id and event.get("event_id") != event_id:
                continue
            if (event.get("title") == expected.title
                    and _same_datetime(event.get("start"), expected.start)
                    and _same_datetime(event.get("end"), expected.end)):
                return VerificationDecision("success", "Calendar 事件已确认存在且字段一致。")
        return VerificationDecision("failure", "未能确认 Calendar 中存在字段匹配的事件。")


def _same_datetime(value: Any, expected: datetime) -> bool:
    if isinstance(value, datetime):
        return value == expected
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")) == expected
        except ValueError:
            return False
    return False


__all__ = ["VerificationDecision", "VerificationService"]
