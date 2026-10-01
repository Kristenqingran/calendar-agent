"""Pure decision/planning boundary for the minimal Agent runtime."""

from __future__ import annotations

from typing import Any, Mapping
from uuid import uuid4

from pydantic import TypeAdapter, ValidationError

from .calendar_workflow import CalendarWorkflow
from .enums import ClarificationReason, Intent, ObjectType, Purpose, Tool
from .messages import Clarification, Final
from .response_language import (
    ResponseLanguage,
    clarification_copy,
    final_copy,
)
from .tools import ToolRequest


class PlanningError(ValueError):
    """The semantic result cannot be safely mapped to a V1 response."""


class Planner:
    """Convert one validated semantic task into one protocol response."""

    def plan(
        self,
        *,
        request_id: str,
        conversation_id: str,
        task_id: str,
        step_id: str,
        analysis: Any,
        context: Mapping[str, Any] | None = None,
        response_language: ResponseLanguage = ResponseLanguage.CHINESE,
    ) -> ToolRequest | Clarification | Final:
        if analysis.needs_clarification:
            return self._clarification(
                request_id, conversation_id, task_id, step_id, analysis, response_language
            )
        if len(analysis.tasks) != 1:
            return self._failure(
                request_id, conversation_id, task_id,
                "unsupported_operation", response_language,
            )

        task = analysis.tasks[0]
        blocked = [
            name for name, parameter in task.parameters.items()
            if parameter.status in {"missing", "ambiguous", "invalid"}
        ]
        if blocked:
            return self._parameter_clarification(
                request_id, conversation_id, task_id, step_id, blocked, response_language,
            )
        if task.batch_write:
            return self._failure(
                request_id, conversation_id, task_id,
                "unsupported_operation", response_language,
            )
        if task.object == ObjectType.CALENDAR_EVENT and task.intent == Intent.CREATE:
            try:
                return CalendarWorkflow().plan(
                    request_id=request_id, conversation_id=conversation_id,
                    task_id=task_id, step_id=step_id, task=task,
                    response_language=response_language,
                )
            except ValueError as exc:
                raise PlanningError(str(exc)) from exc
        if task.object == ObjectType.REMINDER and task.intent == Intent.CREATE:
            return self._reminder_create(
                request_id, conversation_id, task_id, step_id, task, context or {}
            )
        if task.object == ObjectType.CALENDAR_EVENT and task.intent == Intent.QUERY:
            try:
                return CalendarWorkflow().plan(
                    request_id=request_id, conversation_id=conversation_id,
                    task_id=task_id, step_id=step_id, task=task,
                    response_language=response_language,
                )
            except ValueError as exc:
                raise PlanningError(str(exc)) from exc
        return self._failure(
            request_id, conversation_id, task_id,
            "unsupported_operation", response_language,
        )

    @staticmethod
    def _parameter(task: Any, name: str, *, required: bool = True) -> Any:
        parameter = task.parameters.get(name)
        if parameter is None or parameter.status in {"missing", "ambiguous", "invalid"}:
            if required:
                raise PlanningError(f"parameter {name!r} is not valid for planning")
            return None
        return parameter.value

    def _reminder_create(self, request_id: str, conversation_id: str, task_id: str,
                         step_id: str, task: Any, context: Mapping[str, Any]) -> ToolRequest:
        if context.get("calendar_reasonableness_verified") is not True:
            raise PlanningError("reminder create requires a verified calendar reasonableness check")
        payload = {"title": self._parameter(task, "title"),
                   "reminder_time": self._parameter(task, "reminder_time")}
        self._optional(payload, task, "list_id", "notes")
        return self._validate_request({
            "type": "tool_request", "execution_id": f"exec_{uuid4().hex}",
            "causation_request_id": request_id,
            "conversation_id": conversation_id, "task_id": task_id, "step_id": step_id,
            "tool": Tool.CREATE_REMINDER, "operation_id": _operation_id(),
            "arguments": payload,
        })

    @staticmethod
    def _optional(payload: dict[str, Any], task: Any, *names: str) -> None:
        for name in names:
            parameter = task.parameters.get(name)
            if parameter is not None and parameter.status == "valid" and parameter.value is not None:
                payload[name] = parameter.value

    @staticmethod
    def _clarification(request_id: str, conversation_id: str, task_id: str,
                       step_id: str, analysis: Any,
                       response_language: ResponseLanguage = ResponseLanguage.CHINESE) -> Clarification:
        details = analysis.clarification
        if details is None:
            raise PlanningError("needs_clarification requires clarification details")
        try:
            reason = ClarificationReason(details.reason)
        except ValueError as exc:
            raise PlanningError("unknown clarification reason") from exc
        return Clarification(
            type="clarification", request_id=request_id, conversation_id=conversation_id,
            task_id=task_id, step_id=step_id, reason=reason,
            message=clarification_copy(
                response_language, reason.value, details.fields, details.message
            ),
            expected_answer={"type": details.expected_answer_type},
            ambiguous_fields=details.fields,
        )

    @staticmethod
    def _parameter_clarification(request_id: str, conversation_id: str, task_id: str,
                                 step_id: str, fields: list[str],
                                 response_language: ResponseLanguage = ResponseLanguage.CHINESE) -> Clarification:
        return Clarification(
            type="clarification", request_id=request_id, conversation_id=conversation_id,
            task_id=task_id, step_id=step_id,
            reason=ClarificationReason.MISSING_REQUIRED_PARAMETER,
            message=clarification_copy(response_language, "missing_required_parameter", fields),
            expected_answer={"fields": fields}, missing_fields=fields,
        )

    @staticmethod
    def _validate_request(payload: dict[str, Any]) -> ToolRequest:
        try:
            return TypeAdapter(ToolRequest).validate_python(payload)
        except ValidationError as exc:
            raise PlanningError("planner produced an invalid ToolRequest") from exc

    @staticmethod
    def _failure(request_id: str, conversation_id: str, task_id: str,
                 code: str, response_language: ResponseLanguage = ResponseLanguage.CHINESE) -> Final:
        message = final_copy(response_language, "failure", error_code=code)
        return Final(type="final", request_id=request_id, conversation_id=conversation_id,
                     task_id=task_id, status="failure", message=message,
                     error={"code": code, "message": message, "retryable": False})


def _operation_id() -> str:
    return f"op_{uuid4().hex}"


__all__ = ["Planner", "PlanningError"]
