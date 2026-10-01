from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy.orm import Session

from calendar_agent_protocol.dispatcher import MockToolAdapter, ToolDispatcher
from calendar_agent_protocol.domain import TaskStatus
from calendar_agent_protocol.enums import Tool
from calendar_agent_protocol.messages import Clarification, ClarificationResponse, ToolResult, UserRequest
from calendar_agent_protocol.persistence import Base, make_engine
from calendar_agent_protocol.planning import PlanningError
from calendar_agent_protocol.repository import ClarificationRepository, TaskRepository
from calendar_agent_protocol.runtime import AgentRuntime, ClarificationResumeError, MalformedLLMAnalysis
from calendar_agent_protocol.tools import CreateCalendarEventRequest


class FakeLLM:
    def __init__(self, result: dict[str, Any]):
        self.result = result

    def analyze(self, request: UserRequest, context: Any = None) -> dict[str, Any]:
        return self.result


@pytest.fixture
def session(tmp_path: Path):
    engine = make_engine(f"sqlite:///{tmp_path / 'runtime.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as value:
        yield value


def user_request() -> UserRequest:
    return UserRequest(
        type="user_request",
        request_id="req_001",
        conversation_id="conv_001",
        message="明天下午三点开会",
        current_time="2026-09-24T10:00:00+08:00",
        assistant_timezone="Asia/Shanghai",
        source="test",
    )


def request_with_message(
    message: str, *, conversation_id: str = "conv_001", request_id: str = "req_002"
) -> UserRequest:
    return UserRequest(
        type="user_request", request_id=request_id, conversation_id=conversation_id,
        message=message, current_time="2026-09-24T10:00:00+08:00",
        assistant_timezone="Asia/Shanghai", source="test",
    )


def analysis(*, needs_clarification: bool) -> dict[str, Any]:
    return {
        "actionable": True,
        "tasks": [{
            "sequence": 1,
            "object": "calendar_event",
            "intent": "create",
            "batch_write": False,
            "parameters": {
                "title": {
                    "value": "会议",
                    "source": "explicit",
                    "status": "valid",
                    "evidence": "开会",
                }
            },
        }],
        "background": [],
        "constraints": [],
        "needs_clarification": needs_clarification,
        "clarification": ({
            "reason": "missing_required_parameter",
            "message": "请提供会议时长。",
            "fields": ["duration"],
            "expected_answer_type": "duration",
        } if needs_clarification else None),
    }


def missing_time_analysis() -> dict[str, Any]:
    value = analysis(needs_clarification=True)
    value["clarification"]["fields"] = ["start", "end"]
    value["clarification"]["message"] = "请提供会议的具体开始时间和时长。"
    return value


def test_runtime_persists_semantic_task_and_returns_clarification(session: Session) -> None:
    response = AgentRuntime(session, FakeLLM(analysis(needs_clarification=True))).handle(user_request())

    assert isinstance(response, Clarification)
    snapshot = TaskRepository(session).snapshot(response.task_id)
    assert snapshot.task.current_state == TaskStatus.WAITING_CLARIFICATION
    assert snapshot.task.current_step_id == response.step_id
    assert snapshot.pending_clarification["step_id"] == response.step_id
    assert snapshot.pending_clarification["expected_answer"] == {"type": "duration"}
    assert snapshot.parameters[0]["name"] == "title"
    assert any(step["step_id"] == response.step_id and step["step_type"] == "clarification"
               for step in snapshot.steps)
    assert snapshot.tool_exchanges == []
    assert snapshot.operations == []


def test_runtime_rejects_clarification_with_wrong_conversation_id(session: Session) -> None:
    clarification = AgentRuntime(
        session, FakeLLM(missing_time_analysis())
    ).handle(user_request())
    assert isinstance(clarification, Clarification)
    answer = ClarificationResponse(
        type="clarification_response", request_id="req_answer_001",
        conversation_id="conv_wrong_001", task_id=clarification.task_id,
        reply_to_step_id=clarification.step_id, message="3 PM for one hour",
    )

    with pytest.raises(ClarificationResumeError, match="Task correlation mismatch"):
        AgentRuntime(session, FakeLLM(analysis(needs_clarification=False))).handle(answer)

    assert TaskRepository(session).snapshot(clarification.task_id).task.current_state == TaskStatus.WAITING_CLARIFICATION
    assert ClarificationRepository(session).get_pending(clarification.task_id) is not None


def test_runtime_fails_closed_when_new_request_targets_conversation_with_pending_clarification(
    session: Session, monkeypatch,
) -> None:
    first = AgentRuntime(session, FakeLLM(missing_time_analysis())).handle(user_request())
    assert isinstance(first, Clarification)

    # Simulate a competing request creating the pending Task after the initial
    # preflight query but before this request enters its persistence transaction.
    original_query = TaskRepository.waiting_clarification_for_conversation
    calls = 0

    def race_query(repository, conversation_id):
        nonlocal calls
        calls += 1
        if calls == 1:
            return []
        return original_query(repository, conversation_id)

    monkeypatch.setattr(TaskRepository, "waiting_clarification_for_conversation", race_query)

    with pytest.raises(ClarificationResumeError, match="already has a pending"):
        AgentRuntime(session, FakeLLM(analysis(needs_clarification=False))).handle(
            request_with_message("Create another meeting", request_id="req_new_task_001")
        )
    assert calls == 2

    from calendar_agent_protocol.persistence import TaskRow
    from sqlalchemy import select

    tasks = session.scalars(
        select(TaskRow).where(TaskRow.conversation_id == first.conversation_id)
    ).all()
    assert len(tasks) == 1
    assert tasks[0].current_state == TaskStatus.WAITING_CLARIFICATION.value


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("Create a meeting tomorrow.", "What time should the meeting start, and how long should it last?"),
        ("帮我创建明天的会议", "请提供会议的具体开始时间和时长。"),
    ],
)
def test_runtime_clarification_follows_user_language(session: Session, message: str, expected: str) -> None:
    response = AgentRuntime(session, FakeLLM(missing_time_analysis())).handle(
        request_with_message(message)
    )

    assert isinstance(response, Clarification)
    assert response.message == expected
    assert response.request_id == "req_002"
    assert response.conversation_id == "conv_001"
    assert TaskRepository(session).snapshot(response.task_id).task.current_state == TaskStatus.WAITING_CLARIFICATION


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("Create a meeting tomorrow at 3 pm for one hour", "The calendar event was created and verified."),
        ("帮我创建明天下午三点的会议", "日历事件已创建并验证。"),
    ],
)
def test_runtime_success_final_follows_user_language_and_preserves_operation(
    session: Session, message: str, expected: str
) -> None:
    value = analysis(needs_clarification=False)
    value["tasks"][0]["parameters"].update({
        "start": {"value": "2026-09-25T15:00:00+08:00", "source": "explicit", "status": "valid", "evidence": "3 pm"},
        "end": {"value": "2026-09-25T16:00:00+08:00", "source": "explicit", "status": "valid", "evidence": "one hour"},
    })
    adapter = MockToolAdapter()
    dispatcher = ToolDispatcher({Tool.CREATE_CALENDAR_EVENT: adapter, Tool.QUERY_CALENDAR: adapter})

    response = AgentRuntime(session, FakeLLM(value), dispatcher).handle(request_with_message(message))

    assert response.status == "success"
    assert response.message == expected
    assert response.request_id == "req_002"
    snapshot = TaskRepository(session).snapshot(response.task_id)
    assert snapshot.task.current_state == TaskStatus.SUCCEEDED
    assert snapshot.operations[0]["operation_id"].startswith("op_")
    assert snapshot.operations[0]["status"] == "verified_success"
    assert [row["status"] for row in snapshot.tool_exchanges] == ["success", "success"]
    create_request = snapshot.tool_exchanges[0]["request_payload"]
    assert create_request["conversation_id"] == "conv_001"
    assert create_request["task_id"] == response.task_id
    assert create_request["step_id"] == snapshot.tool_exchanges[0]["step_id"]
    assert create_request["operation_id"] == snapshot.operations[0]["operation_id"]


def test_same_http_request_id_replays_final_without_repeating_calendar_write(session: Session) -> None:
    value = analysis(needs_clarification=False)
    value["tasks"][0]["parameters"].update({
        "start": {"value": "2026-09-25T15:00:00+08:00", "source": "explicit", "status": "valid", "evidence": "time"},
        "end": {"value": "2026-09-25T16:00:00+08:00", "source": "explicit", "status": "valid", "evidence": "duration"},
    })
    adapter = MockToolAdapter()
    runtime = AgentRuntime(
        session, FakeLLM(value),
        ToolDispatcher({Tool.CREATE_CALENDAR_EVENT: adapter, Tool.QUERY_CALENDAR: adapter}),
    )

    first = runtime.handle(user_request())
    replay = runtime.handle(user_request())

    assert first.status == replay.status == "success"
    assert first.model_dump(mode="json") == replay.model_dump(mode="json")
    assert len(adapter.events) == 1


def test_reused_request_id_with_different_user_text_is_rejected(session: Session) -> None:
    clarification = AgentRuntime(session, FakeLLM(missing_time_analysis())).handle(user_request())
    changed = user_request().model_copy(update={"message": "Delete every event"})

    response = AgentRuntime(session, FakeLLM(missing_time_analysis())).handle(changed)

    assert isinstance(clarification, Clarification)
    assert response.status == "failure"
    assert response.error.code == "idempotency_conflict"


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("Create a meeting tomorrow at 3 pm for one hour", "The requested operation could not be completed."),
        ("帮我创建明天下午三点的会议", "请求的操作未能完成。"),
    ],
)
def test_runtime_failure_final_follows_user_language(session: Session, message: str, expected: str) -> None:
    value = analysis(needs_clarification=False)
    value["tasks"][0]["parameters"].update({
        "start": {"value": "2026-09-25T15:00:00+08:00", "source": "explicit", "status": "valid", "evidence": "time"},
        "end": {"value": "2026-09-25T16:00:00+08:00", "source": "explicit", "status": "valid", "evidence": "duration"},
    })
    dispatcher = ToolDispatcher({Tool.CREATE_CALENDAR_EVENT: MockToolAdapter(fail_tools={Tool.CREATE_CALENDAR_EVENT})})

    response = AgentRuntime(session, FakeLLM(value), dispatcher).handle(request_with_message(message))

    assert response.status == "failure"
    assert response.message == expected
    assert response.error.message == expected
    assert TaskRepository(session).snapshot(response.task_id).task.current_state == TaskStatus.FAILED


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("Create a meeting tomorrow at 3 pm for one hour", "I couldn't confirm whether the operation completed."),
        ("帮我创建明天下午三点的会议", "无法确认操作是否完成。"),
    ],
)
def test_runtime_unknown_final_follows_user_language(session: Session, message: str, expected: str) -> None:
    class UnknownAdapter:
        def execute(self, request):
            return ToolResult(
                type="tool_result", execution_id=request.execution_id,
                causation_request_id=request.causation_request_id,
                conversation_id=request.conversation_id, task_id=request.task_id,
                step_id=request.step_id, tool=request.tool, status="unknown",
                executed_at=datetime.now(UTC), operation_id=request.operation_id,
                error={"code": "execution_unknown", "message": "不确定", "retryable": False},
            )

    value = analysis(needs_clarification=False)
    value["tasks"][0]["parameters"].update({
        "start": {"value": "2026-09-25T15:00:00+08:00", "source": "explicit", "status": "valid", "evidence": "time"},
        "end": {"value": "2026-09-25T16:00:00+08:00", "source": "explicit", "status": "valid", "evidence": "duration"},
    })
    dispatcher = ToolDispatcher({Tool.CREATE_CALENDAR_EVENT: UnknownAdapter()})

    response = AgentRuntime(session, FakeLLM(value), dispatcher).handle(request_with_message(message))

    assert response.status == "unknown"
    assert response.message == expected
    assert response.error.message == expected
    snapshot = TaskRepository(session).snapshot(response.task_id)
    assert snapshot.task.current_state == TaskStatus.UNKNOWN
    assert snapshot.operations[0]["status"] == "unknown"


def test_runtime_inherits_language_for_short_followup_in_same_conversation(session: Session) -> None:
    complete = analysis(needs_clarification=False)
    complete["tasks"][0]["parameters"].update({
        "start": {"value": "2026-09-25T15:00:00+08:00", "source": "explicit", "status": "valid", "evidence": "3pm"},
        "end": {"value": "2026-09-25T16:00:00+08:00", "source": "explicit", "status": "valid", "evidence": "one hour"},
    })
    adapter = MockToolAdapter()
    dispatcher = ToolDispatcher({Tool.CREATE_CALENDAR_EVENT: adapter, Tool.QUERY_CALENDAR: adapter})
    first = AgentRuntime(session, FakeLLM(complete), dispatcher).handle(
        request_with_message("Create a meeting tomorrow at 3 pm for one hour")
    )
    assert first.status == "success"

    followup = AgentRuntime(session, FakeLLM(missing_time_analysis())).handle(
        request_with_message("9?", conversation_id="conv_001", request_id="req_003")
    )

    assert isinstance(followup, Clarification)
    assert followup.message == "What time should the meeting start, and how long should it last?"


def test_runtime_rejects_malformed_llm_analysis(session: Session) -> None:
    with pytest.raises(MalformedLLMAnalysis):
        AgentRuntime(session, FakeLLM({"actionable": True})).handle(user_request())


def test_runtime_refuses_incomplete_calendar_create(session: Session) -> None:
    with pytest.raises(PlanningError):
        AgentRuntime(session, FakeLLM(analysis(needs_clarification=False))).handle(user_request())


def test_runtime_plans_valid_calendar_create(session: Session) -> None:
    value = analysis(needs_clarification=False)
    value["tasks"][0]["parameters"].update({
        "start": {"value": "2026-09-25T15:00:00+08:00", "source": "explicit", "status": "valid", "evidence": "三点"},
        "end": {"value": "2026-09-25T16:00:00+08:00", "source": "explicit", "status": "valid", "evidence": "一小时"},
    })
    response = AgentRuntime(session, FakeLLM(value)).handle(user_request())
    assert isinstance(response, CreateCalendarEventRequest)
    assert response.tool == "create_calendar_event"
    assert response.operation_id.startswith("op_")
