"""Calendar-specific planning for the V1 Agent."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any
from uuid import uuid4

from pydantic import TypeAdapter, ValidationError

from .enums import Purpose, Tool
from .messages import Clarification, Final
from .response_language import ResponseLanguage, final_copy
from .tools import ToolRequest


class CalendarWorkflow:
    """Build Calendar ToolRequests without executing external tools."""

    def plan(self, *, request_id: str, conversation_id: str, task_id: str,
              step_id: str, task: Any,
              response_language: ResponseLanguage = ResponseLanguage.CHINESE
              ) -> ToolRequest | Clarification | Final:
        intent = getattr(task.intent, "value", task.intent)
        if intent == "create":
            return self._create(request_id, conversation_id, task_id, step_id, task)
        if intent == "query":
            return self._query(request_id, conversation_id, task_id, step_id, task)
        return self._failure(
            request_id, conversation_id, task_id,
            "unsupported_operation", response_language,
        )

    @staticmethod
    def _parameter(task: Any, name: str, *, required: bool = True) -> Any:
        parameter = task.parameters.get(name)
        if parameter is None or parameter.status in {"missing", "ambiguous", "invalid"}:
            if required:
                raise ValueError(f"parameter {name!r} is not valid for Calendar planning")
            return None
        return parameter.value

    def _create(self, request_id: str, conversation_id: str, task_id: str,
                step_id: str, task: Any) -> ToolRequest:
        title = self._parameter(task, "title")
        all_day = self._parameter(task, "all_day", required=False)
        payload: dict[str, Any] = {
            "title": title,
            "all_day": bool(all_day) if all_day is not None else False,
        }
        if payload["all_day"]:
            payload["start_date"] = self._parameter(task, "start_date")
            payload["end_date"] = self._parameter(task, "end_date")
        else:
            payload["start"] = self._parameter(task, "start")
            end = self._parameter(task, "end", required=False)
            if end is None:
                duration = self._parameter(task, "duration", required=False)
                if duration is None:
                    raise ValueError("timed Calendar event requires end or duration")
                try:
                    end = _as_datetime(payload["start"]) + timedelta(minutes=int(duration))
                except (TypeError, ValueError, OverflowError) as exc:
                    raise ValueError("Calendar event duration cannot determine end") from exc
            payload["end"] = end
        self._optional(payload, task, "calendar_id", "calendar_name", "location", "notes")
        try:
            return TypeAdapter(ToolRequest).validate_python({
                "type": "tool_request", "execution_id": _execution_id(),
                "causation_request_id": request_id,
                "conversation_id": conversation_id, "task_id": task_id, "step_id": step_id,
                "tool": Tool.CREATE_CALENDAR_EVENT, "operation_id": _operation_id(),
                "arguments": payload,
            })
        except ValidationError as exc:
            raise ValueError("Calendar workflow produced an invalid ToolRequest") from exc

    def _query(self, request_id: str, conversation_id: str, task_id: str,
               step_id: str, task: Any) -> ToolRequest:
        payload: dict[str, Any] = {}
        self._optional(payload, task, "start", "end", "required_duration_minutes", "target_id")
        if ("start" in payload) != ("end" in payload):
            raise ValueError("Calendar query requires start and end together")
        try:
            return TypeAdapter(ToolRequest).validate_python({
                "type": "tool_request", "execution_id": _execution_id(),
                "causation_request_id": request_id,
                "conversation_id": conversation_id, "task_id": task_id, "step_id": step_id,
                "tool": Tool.QUERY_CALENDAR, "purpose": Purpose.ANSWER_QUERY,
                "arguments": payload,
            })
        except ValidationError as exc:
            raise ValueError("Calendar workflow produced an invalid ToolRequest") from exc

    @staticmethod
    def _optional(payload: dict[str, Any], task: Any, *names: str) -> None:
        for name in names:
            parameter = task.parameters.get(name)
            if parameter is not None and parameter.status == "valid" and parameter.value is not None:
                payload[name] = parameter.value

    @staticmethod
    def _failure(request_id: str, conversation_id: str, task_id: str,
                 code: str, response_language: ResponseLanguage) -> Final:
        message = final_copy(response_language, "failure", error_code=code)
        return Final(type="final", request_id=request_id, conversation_id=conversation_id,
                     task_id=task_id, status="failure", message=message,
                     error={"code": code, "message": message, "retryable": False})


def _operation_id() -> str:
    return f"op_{uuid4().hex}"


def _execution_id() -> str:
    return f"exec_{uuid4().hex}"


def _as_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    raise TypeError("start is not a datetime")


__all__ = ["CalendarWorkflow"]
