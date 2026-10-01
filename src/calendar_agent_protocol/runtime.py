"""Minimal Agent runtime slice for semantic analysis and Task persistence."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any
from uuid import uuid4
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError
from sqlalchemy.orm import Session

from .dispatcher import ToolDispatcher
from .domain import StepStatus, StepType, TaskEntity
from .enums import Intent, ObjectType, OperationStatus, Purpose, TaskStatus, Tool
from .messages import (
    AgentResponse,
    Clarification,
    ClarificationResponse,
    Final,
    InboundMessage,
    RuntimeDecision,
    RuntimeMessage,
    ToolResult,
    UserRequest,
)
from .planning import Planner, PlanningError
from .repository import (
    ClarificationRepository,
    ConcurrencyError,
    ConversationRepository,
    CorrelationError,
    IdempotencyConflict,
    InboundReceiptRepository,
    OperationRepository,
    StepRepository,
    TaskParameterRepository,
    TaskRepository,
    ToolExchangeRepository,
    UnitOfWork,
    digest,
)
from .response_language import ResponseLanguage, final_copy, resolve_response_language
from .runtime_contract import LLMAdapter
from .tools import ToolRequest
from .verification import VerificationService


class LLMParameter(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: Any
    source: str | None
    status: str
    evidence: str | None
    alternatives: list[Any] | None = None


class LLMTask(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sequence: int = Field(ge=1)
    object: ObjectType
    intent: Intent
    batch_write: bool
    parameters: dict[str, LLMParameter]


class LLMClarification(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str
    message: str = Field(min_length=1)
    fields: list[str]
    expected_answer_type: str = Field(min_length=1)


class LLMAnalysis(BaseModel):
    model_config = ConfigDict(extra="forbid")

    actionable: bool
    tasks: list[LLMTask]
    background: list[str]
    constraints: list[str]
    needs_clarification: bool
    clarification: LLMClarification | None


class MalformedLLMAnalysis(ValueError):
    """Raised when an adapter returns data outside the semantic contract."""


class ClarificationResumeError(RuntimeError):
    """A clarification cannot be safely correlated or claimed."""

    def __init__(self, code: str, message: str, *, status_code: int = 409):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


class AgentRuntime:
    """Small runtime slice that persists semantic analysis for a user request."""

    def __init__(self, session: Session, llm: LLMAdapter, dispatcher: ToolDispatcher | None = None):
        self.session = session
        self.llm = llm
        self.dispatcher = dispatcher
        self.verification = VerificationService()

    def handle(self, message: RuntimeMessage) -> RuntimeDecision | ToolResult:
        if isinstance(message, ToolResult):
            return self._handle_tool_result(message)
        if isinstance(message, ClarificationResponse):
            return self.handle_clarification_response(message)
        if not isinstance(message, UserRequest):
            return self._unsupported_message(message)

        replay = self._replay_inbound_request(message)
        if replay is not None:
            return replay

        tasks_for_conversation = TaskRepository(self.session)
        if tasks_for_conversation.waiting_clarification_for_conversation(message.conversation_id):
            raise ClarificationResumeError(
                "pending_clarification_exists",
                "The conversation already has a pending clarification.",
            )
        previous = tasks_for_conversation.latest_for_conversation(message.conversation_id)
        response_language = resolve_response_language(
            message.message, [previous.original_message if previous is not None else None]
        )

        raw = self.llm.analyze(message)
        analysis = self._parse_analysis(raw)
        if len(analysis.tasks) != 1:
            raise PlanningError("当前仅支持单个语义任务。")

        task_analysis = analysis.tasks[0]
        task_id = self._new_id("task")
        step_id = self._new_id("step")
        task = TaskEntity(
            task_id=task_id,
            conversation_id=message.conversation_id,
            original_message=message.message,
            object=task_analysis.object,
            intent=task_analysis.intent,
        )

        dispatch_request: ToolRequest | None = None
        with UnitOfWork(self.session):
            if tasks_for_conversation.waiting_clarification_for_conversation(
                message.conversation_id
            ):
                raise ClarificationResumeError(
                    "pending_clarification_exists",
                    "The conversation already has a pending clarification.",
                )
            conversations = ConversationRepository(self.session)
            if conversations.get(message.conversation_id) is None:
                conversations.create(message.conversation_id, message.assistant_timezone)
            tasks = TaskRepository(self.session)
            tasks.create(task)
            receipt, created = InboundReceiptRepository(self.session).accept(
                request_id=message.request_id,
                conversation_id=message.conversation_id,
                task_id=task_id,
                message_type=message.type,
                payload_hash=self._inbound_payload_hash(message),
                response_payload=None,
            )
            if not created:
                raise IdempotencyConflict(message.request_id)
            tasks.transition(task_id, TaskStatus.VALIDATING_INPUT, "user_request_received", 1)
            tasks.transition(task_id, TaskStatus.ANALYZING, "semantic_analysis_completed", 2)
            parameters = TaskParameterRepository(self.session)
            for name, parameter in task_analysis.parameters.items():
                parameters.upsert(
                    task_id,
                    name,
                    value=parameter.value,
                    source=parameter.source,
                    status=parameter.status,
                    evidence=parameter.evidence,
                )

            tasks.transition(task_id, TaskStatus.PLANNING, "planning_started", 3)
            response = Planner().plan(
                request_id=message.request_id,
                conversation_id=message.conversation_id,
                task_id=task_id,
                step_id=step_id,
                analysis=analysis,
                response_language=response_language,
            )
            if response.type == "clarification":
                self._persist_clarification(tasks, response)
                current = tasks.get(task_id)
                tasks.transition(task_id, TaskStatus.WAITING_CLARIFICATION,
                                 "planning_clarification", current.version)
                current = tasks.get(task_id)
                tasks.update_with_version(
                    task_id, expected_version=current.version, current_step_id=response.step_id
                )
            elif response.type == "tool_request":
                self._persist_tool_request(tasks, response)
                current = tasks.get(task_id)
                tasks.transition(task_id, TaskStatus.PRE_EXECUTION_CHECK,
                                 "planning_approved_tool_request", current.version)
                current = tasks.get(task_id)
                tasks.transition(task_id, TaskStatus.WAITING_TOOL_RESULT,
                                 "tool_request_dispatched", current.version)
                if self.dispatcher is not None:
                    dispatch_request = response
            if getattr(response, "type", None) != "tool_request":
                InboundReceiptRepository(self.session).save_response(
                    message.request_id, response.model_dump(mode="json")
                )
        if dispatch_request is not None and self.dispatcher is not None:
            result = self.dispatcher.dispatch(dispatch_request)
            response = self._handle_tool_result(result)
            if isinstance(response, (Clarification, Final)):
                with UnitOfWork(self.session):
                    InboundReceiptRepository(self.session).save_response(
                        message.request_id, response.model_dump(mode="json")
                    )
            return response
        return response

    def handle_clarification_response(
        self,
        message: ClarificationResponse,
        *,
        assistant_timezone: str | None = None,
    ) -> AgentResponse | ToolResult:
        """Claim a persisted clarification and continue the original Task."""
        replay = self._replay_inbound_request(message)
        if replay is not None:
            return replay

        tasks = TaskRepository(self.session)
        task = tasks.get(message.task_id)
        if task is None or task.conversation_id != message.conversation_id:
            raise ClarificationResumeError("clarification_task_mismatch", "Task correlation mismatch.")
        waiting = tasks.waiting_clarification_for_conversation(message.conversation_id)
        if len(waiting) != 1:
            code = "ambiguous_pending_clarification" if waiting else "no_pending_clarification"
            raise ClarificationResumeError(code, "The conversation has no unique pending clarification.")

        clarifications = ClarificationRepository(self.session)
        pending_rows = clarifications.pending_for_task(message.task_id)
        pending = pending_rows[0] if len(pending_rows) == 1 else None
        if (
            task.current_state != TaskStatus.WAITING_CLARIFICATION.value
            or pending is None
            or task.current_step_id != message.reply_to_step_id
            or pending.step_id != message.reply_to_step_id
        ):
            raise ClarificationResumeError("stale_clarification", "The clarification is no longer pending.")

        history = clarifications.list_for_task(message.task_id)
        accepted_count = sum(row.user_response is not None for row in history)
        prior_texts = [
            row.user_response["message"]
            for row in reversed(history)
            if isinstance(row.user_response, dict) and row.user_response.get("message")
        ] + [task.original_message]
        language = resolve_response_language(message.message, prior_texts)
        conversation = ConversationRepository(self.session).get(message.conversation_id)
        if conversation is None:
            raise ClarificationResumeError("unknown_conversation", "Conversation not found.", status_code=404)
        timezone = assistant_timezone or conversation.assistant_timezone
        try:
            ZoneInfo(timezone)
        except (TypeError, ValueError) as exc:
            raise ClarificationResumeError(
                "invalid_assistant_timezone", "assistant_timezone must be a valid IANA timezone.",
                status_code=400,
            ) from exc

        # Claim and answer persistence are atomic. The versioned transition is
        # the single-consumer gate for concurrent/replayed follow-up requests.
        try:
            with UnitOfWork(self.session):
                _, created = InboundReceiptRepository(self.session).accept(
                    request_id=message.request_id,
                    conversation_id=message.conversation_id,
                    task_id=message.task_id,
                    message_type=message.type,
                    payload_hash=self._inbound_payload_hash(message),
                    response_payload=None,
                )
                if not created:
                    raise IdempotencyConflict(message.request_id)
                current = tasks.get(message.task_id)
                if (
                    current is None
                    or current.current_state != TaskStatus.WAITING_CLARIFICATION.value
                    or current.current_step_id != message.reply_to_step_id
                ):
                    raise ConcurrencyError("clarification was already claimed")
                tasks.transition(
                    message.task_id, TaskStatus.ANALYZING_CLARIFICATION,
                    "clarification_answer_received", current.version,
                )
                clarifications.resolve(
                    message.task_id,
                    message.reply_to_step_id,
                    {"request_id": message.request_id, "message": message.message},
                )
                StepRepository(self.session).complete(
                    message.reply_to_step_id,
                    output_summary={"request_id": message.request_id, "answer": message.message},
                )
                if assistant_timezone is not None:
                    ConversationRepository(self.session).update_timezone(
                        message.conversation_id, assistant_timezone
                    )
                if accepted_count >= 5:
                    current = tasks.get(message.task_id)
                    tasks.transition(
                        message.task_id, TaskStatus.FAILED,
                        "clarification_answer_limit_reached", current.version,
                    )
                    response = Final(
                        type="final", request_id=message.request_id,
                        conversation_id=message.conversation_id, task_id=message.task_id,
                        status="failure", message=final_copy(language, "failure"),
                        error={"code": "clarification_limit_reached",
                               "message": "Maximum clarification answers reached.",
                               "retryable": False},
                    )
                    InboundReceiptRepository(self.session).save_response(
                        message.request_id, response.model_dump(mode="json")
                    )
                    return response
        except ClarificationResumeError:
            raise
        except (ConcurrencyError, CorrelationError, IdempotencyConflict) as exc:
            raise ClarificationResumeError(
                "clarification_claim_conflict", "The clarification was already claimed or is stale."
            ) from exc

        conversation = ConversationRepository(self.session).get(message.conversation_id)
        timezone = conversation.assistant_timezone if conversation is not None else timezone
        analysis_request = UserRequest(
            type="user_request", request_id=message.request_id,
            conversation_id=message.conversation_id, message=message.message,
            current_time=datetime.now(ZoneInfo(timezone)), assistant_timezone=timezone,
            source="clarification-resume",
        )
        saved_rows = TaskParameterRepository(self.session).list(message.task_id)
        saved_parameters = {
            row.name: {"value": row.value, "source": row.source,
                       "status": row.status, "evidence": row.evidence}
            for row in saved_rows
        }
        turns = clarifications.list_for_task(message.task_id)
        context = {
            "original_message": task.original_message,
            "prior_parameters": saved_parameters,
            "clarification_turns": [
                {"question": row.message, "answer": row.user_response.get("message")}
                for row in turns if isinstance(row.user_response, dict)
            ],
            "assistant_timezone": timezone,
        }

        try:
            analysis = self._parse_analysis(self.llm.analyze(analysis_request, context=context))
            if len(analysis.tasks) != 1:
                raise PlanningError("当前仅支持单个语义任务。")
            task_analysis = analysis.tasks[0]
            if task_analysis.object.value != task.object or task_analysis.intent.value != task.intent:
                raise PlanningError("Clarification cannot change the original task intent.")
            self._merge_saved_parameters(task_analysis, saved_parameters)
            response = Planner().plan(
                request_id=message.request_id,
                conversation_id=message.conversation_id,
                task_id=message.task_id,
                step_id=self._new_id("step"),
                analysis=analysis,
                response_language=language,
            )
        except Exception:
            return self._fail_clarification_processing(message, language)

        dispatch_request: ToolRequest | None = None
        try:
            with UnitOfWork(self.session):
                current = tasks.get(message.task_id)
                if current is None or current.current_state != TaskStatus.ANALYZING_CLARIFICATION.value:
                    raise ClarificationResumeError(
                        "clarification_claim_conflict", "The Task is no longer being resumed."
                    )
                tasks.transition(
                    message.task_id, TaskStatus.PLANNING,
                    "clarification_analysis_completed", current.version,
                )
                for name, parameter in task_analysis.parameters.items():
                    TaskParameterRepository(self.session).upsert(
                        message.task_id, name, value=parameter.value,
                        source=parameter.source, status=parameter.status,
                        evidence=parameter.evidence,
                    )
                current = tasks.get(message.task_id)
                if response.type == "clarification":
                    self._persist_clarification(tasks, response)
                    current = tasks.get(message.task_id)
                    tasks.transition(
                        message.task_id, TaskStatus.WAITING_CLARIFICATION,
                        "planning_clarification", current.version,
                    )
                    current = tasks.get(message.task_id)
                    tasks.update_with_version(
                        message.task_id, expected_version=current.version,
                        current_step_id=response.step_id,
                    )
                elif response.type == "tool_request":
                    self._persist_tool_request(tasks, response)
                    current = tasks.get(message.task_id)
                    tasks.transition(
                        message.task_id, TaskStatus.PRE_EXECUTION_CHECK,
                        "planning_approved_tool_request", current.version,
                    )
                    current = tasks.get(message.task_id)
                    tasks.transition(
                        message.task_id, TaskStatus.WAITING_TOOL_RESULT,
                        "tool_request_dispatched", current.version,
                    )
                    if self.dispatcher is not None:
                        dispatch_request = response
                if dispatch_request is None:
                    InboundReceiptRepository(self.session).save_response(
                        message.request_id, response.model_dump(mode="json")
                    )
        except ClarificationResumeError:
            raise
        except Exception:
            return self._fail_clarification_processing(message, language)

        if dispatch_request is not None and self.dispatcher is not None:
            result = self.dispatcher.dispatch(dispatch_request)
            public_response = self._handle_tool_result(result)
            if isinstance(public_response, (Clarification, Final)):
                with UnitOfWork(self.session):
                    InboundReceiptRepository(self.session).save_response(
                        message.request_id, public_response.model_dump(mode="json")
                    )
            return public_response
        return response

    def _fail_clarification_processing(
        self, message: ClarificationResponse, language: ResponseLanguage
    ) -> Final:
        with UnitOfWork(self.session):
            task = TaskRepository(self.session).get(message.task_id)
            if task is not None and task.current_state == TaskStatus.ANALYZING_CLARIFICATION.value:
                TaskRepository(self.session).transition(
                    message.task_id, TaskStatus.FAILED,
                    "clarification_processing_failed", task.version,
                )
            response = Final(
                type="final", request_id=message.request_id,
                conversation_id=message.conversation_id, task_id=message.task_id,
                status="failure", message=final_copy(language, "failure"),
                error={"code": "clarification_processing_failed",
                       "message": "Unable to safely process clarification.",
                       "retryable": False},
            )
            if InboundReceiptRepository(self.session).get(message.request_id) is not None:
                InboundReceiptRepository(self.session).save_response(
                    message.request_id, response.model_dump(mode="json")
                )
        return response

    @staticmethod
    def _merge_saved_parameters(task_analysis: LLMTask, saved: Mapping[str, Any]) -> None:
        for name, previous in saved.items():
            if previous.get("status") != "valid" or previous.get("value") is None:
                continue
            current = task_analysis.parameters.get(name)
            if current is None or current.status != "valid" or current.value is None:
                task_analysis.parameters[name] = LLMParameter.model_validate(previous)

    def _persist_clarification(self, tasks: TaskRepository, response: Clarification) -> None:
        StepRepository(self.session).create(
            step_id=response.step_id, task_id=response.task_id,
            step_type=StepType.CLARIFICATION.value, status=StepStatus.IN_PROGRESS.value,
            input_summary=response.model_dump(mode="json"),
        )
        ClarificationRepository(self.session).save(
            step_id=response.step_id, task_id=response.task_id,
            reason=response.reason.value, message=response.message,
            expected_answer=response.expected_answer,
            missing_fields=response.missing_fields,
            ambiguous_fields=response.ambiguous_fields,
            blocked_from_state=TaskStatus.PLANNING.value,
        )

    def _replay_inbound_request(self, message: InboundMessage) -> AgentResponse | None:
        receipt = InboundReceiptRepository(self.session).get(message.request_id)
        if receipt is None:
            return None
        if receipt.payload_hash != self._inbound_payload_hash(message):
            return Final(
                type="final", request_id=message.request_id,
                conversation_id=message.conversation_id, task_id=receipt.task_id,
                status="failure", message="request_id 已用于不同的请求内容。",
                error={"code": "idempotency_conflict", "message": "request_id payload mismatch", "retryable": False},
            )
        if receipt.response_payload is not None:
            return TypeAdapter(AgentResponse).validate_python(receipt.response_payload)
        return Final(
            type="final", request_id=message.request_id,
            conversation_id=message.conversation_id, task_id=receipt.task_id,
            status="unknown", message="相同请求仍在处理，未重复执行写入操作。",
            error={"code": "request_in_progress", "message": "已有相同 request_id 的执行尚未完成。", "retryable": False},
        )

    @staticmethod
    def _inbound_payload_hash(message: InboundMessage) -> str:
        # `current_time` and `source` may be transport-generated and change on
        # retries. The stable user intent and explicit conversation context
        # define whether a reused request_id is the same logical HTTP request.
        common = {
            "type": message.type,
            "conversation_id": message.conversation_id,
            "message": message.message,
        }
        if isinstance(message, ClarificationResponse):
            common.update({
                "task_id": message.task_id,
                "reply_to_step_id": message.reply_to_step_id,
            })
            return digest(common)
        common.update({
            "assistant_timezone": message.assistant_timezone,
            "device_timezone": message.device_timezone,
            "default_calendar": (message.default_calendar.model_dump(mode="json")
                                 if message.default_calendar else None),
        })
        return digest(common)

    def _persist_tool_request(self, tasks: TaskRepository, request: Any) -> None:
        steps = StepRepository(self.session)
        steps.create(
            step_id=request.step_id,
            task_id=request.task_id,
            step_type=StepType.TOOL_WRITE.value if request.tool.is_write else StepType.TOOL_QUERY.value,
            status=StepStatus.IN_PROGRESS.value,
            input_summary=request.model_dump(mode="json"),
        )
        ToolExchangeRepository(self.session).save_request(
            step_id=request.step_id,
            task_id=request.task_id,
            tool=request.tool.value,
            purpose=getattr(request, "purpose", None),
            request_payload=request.model_dump(mode="json"),
        )
        if request.tool.is_write:
            operations = OperationRepository(self.session)
            operation, created = operations.create_or_replay(
                request.operation_id, request.task_id, request.tool, request.arguments.model_dump(mode="json")
            )
            if not created:
                raise IdempotencyConflict(request.operation_id)
            operations.mark_dispatched(operation.operation_id)

    def _handle_tool_result(self, message: ToolResult) -> AgentResponse | ToolResult:
        validated = ToolResult.model_validate(message.model_dump(mode="json"))
        next_request: ToolRequest | None = None
        with UnitOfWork(self.session):
            exchanges = ToolExchangeRepository(self.session)
            exchange = exchanges.get(validated.step_id)
            if exchange is None:
                raise ValueError("unknown tool result step")
            dispatched_request = TypeAdapter(ToolRequest).validate_python(exchange.request_payload)
            expected_operation_id = getattr(dispatched_request, "operation_id", None)
            if any(
                getattr(validated, field) != getattr(dispatched_request, field)
                for field in (
                    "execution_id", "causation_request_id", "conversation_id",
                    "task_id", "step_id", "tool",
                )
            ) or validated.operation_id != expected_operation_id:
                raise ValueError("ToolResult correlation does not match persisted ToolRequest")
            task_id = exchange.task_id
            tasks = TaskRepository(self.session)
            task = tasks.get(task_id)
            if task is None:
                raise ValueError("unknown tool result task")
            tasks.transition(task_id, TaskStatus.VALIDATING_TOOL_RESULT,
                             "tool_result_received", task.version)
            exchanges.save_result(validated.step_id, validated.model_dump(mode="json"))
            if validated.operation_id is not None:
                OperationRepository(self.session).record_result(
                    validated.operation_id,
                    status={"success": OperationStatus.SUCCESS,
                            "failed": OperationStatus.FAILED,
                            "unknown": OperationStatus.UNKNOWN}[validated.status.value],
                    result_payload=validated.model_dump(mode="json"),
                )
            StepRepository(self.session).complete(
                validated.step_id, output_summary=validated.model_dump(mode="json")
            )
            current = TaskRepository(self.session).get(task_id)
            if current is None:
                raise ValueError("tool result task disappeared")
            response_language = resolve_response_language(current.original_message)

            if exchange.purpose == Purpose.VERIFY_STATE.value:
                original = self._calendar_create_exchange(exchanges, task_id)
                tasks.transition(task_id, TaskStatus.VERIFYING_FINAL_STATE,
                                 "verification_result_validated", current.version)
                current = TaskRepository(self.session).get(task_id)
                if current is None:
                    raise ValueError("verification task disappeared")
                if validated.status.value != "success":
                    if original is not None and original.request_payload.get("operation_id"):
                        OperationRepository(self.session).record_verification(
                            original.request_payload["operation_id"],
                            status=OperationStatus.UNKNOWN,
                        )
                    return self._complete_final(task_id, validated, "unknown",
                                                "无法通过 Calendar 查询确认事件状态。", current.version,
                                                error_code="verification_unknown",
                                                response_language=response_language)
                if original is None or original.result_payload is None:
                    return self._complete_final(task_id, validated, "unknown",
                                                "无法确定验证上下文。", current.version,
                                                error_code="verification_unknown",
                                                response_language=response_language)
                original_request = TypeAdapter(ToolRequest).validate_python(original.request_payload)
                original_result = ToolResult.model_validate(original.result_payload)
                decision = self.verification.evaluate_calendar_create(
                    original_request, original_result, validated
                )
                OperationRepository(self.session).record_verification(
                    original_result.operation_id,
                    status={"success": OperationStatus.VERIFIED_SUCCESS,
                            "failure": OperationStatus.VERIFIED_FAILURE,
                            "unknown": OperationStatus.UNKNOWN}[decision.status],
                )
                return self._complete_final(task_id, validated, decision.status,
                                            decision.message, current.version,
                                            error_code=("verification_failed"
                                                        if decision.status == "failure"
                                                        else None),
                                            response_language=response_language,
                                            response_tool=original_request.tool.value)

            if validated.status.value == "success":
                tasks.transition(task_id, TaskStatus.VERIFYING_FINAL_STATE,
                                 "tool_result_validated", current.version)
                if exchange.tool == Tool.QUERY_CALENDAR.value:
                    current = TaskRepository(self.session).get(task_id)
                    if current is None:
                        raise ValueError("query task disappeared")
                    return self._complete_final(task_id, validated, "success",
                                                "Calendar 查询已完成。", current.version,
                                                response_language=response_language,
                                                response_tool=exchange.tool)
                if (exchange.tool == Tool.CREATE_CALENDAR_EVENT.value and self.dispatcher is not None):
                    original_request = TypeAdapter(ToolRequest).validate_python(exchange.request_payload)
                    next_request = self.verification.build_calendar_create_query(
                        original_request, validated, self._new_id("step")
                    )
                    StepRepository(self.session).create(
                        step_id=next_request.step_id, task_id=task_id,
                        step_type=StepType.TOOL_QUERY.value,
                        status=StepStatus.IN_PROGRESS.value,
                        input_summary=next_request.model_dump(mode="json"),
                    )
                    exchanges.save_request(
                        step_id=next_request.step_id, task_id=task_id,
                        tool=next_request.tool.value, purpose=next_request.purpose.value,
                        request_payload=next_request.model_dump(mode="json"),
                    )
                    current = TaskRepository(self.session).get(task_id)
                    tasks.transition(task_id, TaskStatus.WAITING_TOOL_RESULT,
                                     "verification_query_dispatched", current.version)
            elif validated.status.value == "failed":
                return self._complete_final(task_id, validated, "failure",
                                            "Tool 执行失败，任务未完成。", current.version,
                                            response_language=response_language)
            else:
                return self._complete_final(task_id, validated, "unknown",
                                            "Tool 执行结果无法确认。", current.version,
                                            response_language=response_language)
        if next_request is not None and self.dispatcher is not None:
            return self._handle_tool_result(self.dispatcher.dispatch(next_request))
        return validated

    @staticmethod
    def _calendar_create_exchange(exchanges: ToolExchangeRepository, task_id: str):
        """Find the one Calendar Create exchange in this single-operation task."""
        candidates = [
            exchange for exchange in exchanges.list_for_task(task_id)
            if exchange.tool == Tool.CREATE_CALENDAR_EVENT.value
        ]
        return candidates[0] if len(candidates) == 1 else None

    def _complete_final(self, task_id: str, message: ToolResult, status: str,
                        detail: str, version: int, *, error_code: str | None = None,
                        response_language: ResponseLanguage = ResponseLanguage.CHINESE,
                        response_tool: str | None = None) -> Final:
        target = {"success": TaskStatus.SUCCEEDED,
                  "failure": TaskStatus.FAILED,
                  "unknown": TaskStatus.UNKNOWN}[status]
        TaskRepository(self.session).transition(task_id, target, "final_state_completed", version)
        user_message = final_copy(
            response_language, status,
            error_code=error_code or (message.error.code if message.error is not None else None),
            tool=response_tool or message.tool.value,
        )
        error = None
        if status != "success":
            source_error = message.error
            error = {
                "code": source_error.code if source_error is not None else (
                    error_code or ("verification_unknown" if status == "unknown"
                                   else "tool_execution_failed")
                ),
                "message": final_copy(
                    response_language, status,
                    error_code=(source_error.code if source_error is not None else error_code),
                    tool=message.tool.value,
                ),
                "retryable": source_error.retryable if source_error is not None else False,
                "details": source_error.details if source_error is not None else None,
            }
        return Final(
            type="final", request_id=message.causation_request_id,
            conversation_id=message.conversation_id, task_id=task_id,
            status=status, message=user_message,
            result_summary={"tool": message.tool.value, "operation_id": message.operation_id}
            if status == "success" else None,
            error=error,
        )

    @staticmethod
    def _parse_analysis(raw: Mapping[str, Any]) -> LLMAnalysis:
        try:
            return LLMAnalysis.model_validate(raw)
        except ValidationError as exc:
            raise MalformedLLMAnalysis("LLM analysis does not match its contract") from exc

    @staticmethod
    def _new_id(prefix: str) -> str:
        return f"{prefix}_{uuid4().hex}"

    def _unsupported_message(self, message: InboundMessage) -> Final:
        previous_text: str | None = None
        tasks = TaskRepository(self.session)
        if isinstance(message, ClarificationResponse):
            previous = tasks.get(message.task_id)
            previous_text = previous.original_message if previous is not None else None
        else:
            previous = tasks.latest_for_conversation(message.conversation_id)
            previous_text = previous.original_message if previous is not None else None
        language = resolve_response_language(message.message, [previous_text])
        detail = final_copy(language, "failure", error_code="runtime_path_not_implemented")
        return self._final_without_task(message, "runtime_path_not_implemented", detail)

    @staticmethod
    def _final_without_task(message: InboundMessage, code: str, detail: str) -> Final:
        return Final(
            type="final",
            request_id=message.request_id,
            conversation_id=message.conversation_id,
            task_id=getattr(message, "task_id", "task_unassigned"),
            status="failure",
            message=detail,
            error={"code": code, "message": detail, "retryable": False},
        )


__all__ = ["AgentRuntime", "LLMAnalysis", "MalformedLLMAnalysis", "PlanningError"]
