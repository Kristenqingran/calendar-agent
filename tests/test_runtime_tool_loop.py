from pathlib import Path
from typing import Any
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError
from pydantic import TypeAdapter
from sqlalchemy.orm import Session

from calendar_agent_protocol.dispatcher import MockToolAdapter, ToolDispatcher
from calendar_agent_protocol.enums import Tool, TaskStatus
from calendar_agent_protocol.messages import Final, ToolResult, UserRequest
from calendar_agent_protocol.persistence import Base, make_engine
from calendar_agent_protocol.repository import TaskRepository
from calendar_agent_protocol.runtime import AgentRuntime
from calendar_agent_protocol.tools import ToolRequest


class FakeLLM:
    def __init__(self, analysis: dict[str, Any]):
        self.analysis = analysis

    def analyze(self, request: UserRequest, context: Any = None) -> dict[str, Any]:
        return self.analysis


@pytest.fixture
def session(tmp_path: Path):
    engine = make_engine(f"sqlite:///{tmp_path / 'runtime-loop.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as value:
        yield value


def request() -> UserRequest:
    return UserRequest(
        type="user_request", request_id="req_001", conversation_id="conv_001",
        message="安排会议", current_time="2026-09-24T10:00:00+08:00",
        assistant_timezone="Asia/Shanghai", source="test",
    )


def analysis(tool: str = "create_calendar_event") -> dict[str, Any]:
    if tool == "query_calendar":
        parameters = {
            "start": {"value": "2026-09-25T15:00:00+08:00", "source": "test", "status": "valid", "evidence": "explicit"},
            "end": {"value": "2026-09-25T16:00:00+08:00", "source": "test", "status": "valid", "evidence": "explicit"},
        }
        intent = "query"
    else:
        parameters = {
            "title": {"value": "会议", "source": "test", "status": "valid", "evidence": "explicit"},
            "start": {"value": "2026-09-25T15:00:00+08:00", "source": "test", "status": "valid", "evidence": "explicit"},
            "end": {"value": "2026-09-25T16:00:00+08:00", "source": "test", "status": "valid", "evidence": "explicit"},
        }
        intent = "create"
    return {
        "actionable": True,
        "tasks": [{"sequence": 1, "object": "calendar_event", "intent": intent,
                    "batch_write": False, "parameters": parameters}],
        "background": [], "constraints": [], "needs_clarification": False,
        "clarification": None,
    }


def test_calendar_create_runs_tool_loop_and_persists_success(session: Session):
    adapter = MockToolAdapter()
    dispatcher = ToolDispatcher({Tool.CREATE_CALENDAR_EVENT: adapter, Tool.QUERY_CALENDAR: adapter})
    result = AgentRuntime(session, FakeLLM(analysis()), dispatcher).handle(request())

    assert isinstance(result, Final)
    assert result.status == "success"
    snapshot = TaskRepository(session).snapshot(result.task_id)
    assert snapshot.task.current_state == TaskStatus.SUCCEEDED
    assert len(snapshot.tool_exchanges) == 2
    assert snapshot.tool_exchanges[0]["result_payload"]["status"] == "success"
    assert snapshot.tool_exchanges[1]["purpose"] == "verify_state"
    assert snapshot.operations[0]["status"] == "verified_success"
    create_request = TypeAdapter(ToolRequest).validate_python(
        snapshot.tool_exchanges[0]["request_payload"]
    )
    verify_request = TypeAdapter(ToolRequest).validate_python(
        snapshot.tool_exchanges[1]["request_payload"]
    )
    assert create_request.operation_id == snapshot.operations[0]["operation_id"]
    assert "operation_id" not in snapshot.tool_exchanges[1]["request_payload"]
    assert create_request.execution_id != verify_request.execution_id
    assert create_request.causation_request_id == verify_request.causation_request_id == "req_001"


def test_query_tool_loop_has_no_operation(session: Session):
    dispatcher = ToolDispatcher({Tool.QUERY_CALENDAR: MockToolAdapter()})
    result = AgentRuntime(session, FakeLLM(analysis("query_calendar")), dispatcher).handle(request())

    assert isinstance(result, Final)
    assert result.status == "success"
    snapshot = TaskRepository(session).snapshot(result.task_id)
    assert snapshot.task.current_state == TaskStatus.SUCCEEDED
    assert snapshot.operations == []


def test_failed_tool_result_enters_failed_state(session: Session):
    dispatcher = ToolDispatcher({
        Tool.CREATE_CALENDAR_EVENT: MockToolAdapter(fail_tools={Tool.CREATE_CALENDAR_EVENT})
    })
    result = AgentRuntime(session, FakeLLM(analysis()), dispatcher).handle(request())

    assert isinstance(result, Final)
    assert result.status == "failure"
    snapshot = TaskRepository(session).snapshot(result.task_id)
    assert snapshot.task.current_state == TaskStatus.FAILED
    assert snapshot.operations[0]["status"] == "failed"


def test_verification_query_failure_returns_unknown(session: Session):
    adapter = MockToolAdapter(fail_tools={Tool.QUERY_CALENDAR})
    dispatcher = ToolDispatcher({Tool.CREATE_CALENDAR_EVENT: adapter, Tool.QUERY_CALENDAR: adapter})
    result = AgentRuntime(session, FakeLLM(analysis()), dispatcher).handle(request())

    assert isinstance(result, Final)
    assert result.status == "unknown"
    snapshot = TaskRepository(session).snapshot(result.task_id)
    assert snapshot.task.current_state == TaskStatus.UNKNOWN
    assert snapshot.operations[0]["status"] == "unknown"


def test_verification_rejects_mismatched_real_event(session: Session):
    class MismatchedCalendarAdapter:
        def execute(self, tool_request):
            now = datetime.now(UTC)
            if tool_request.tool == Tool.CREATE_CALENDAR_EVENT:
                return ToolResult(
                    type="tool_result", execution_id=tool_request.execution_id,
                    causation_request_id=tool_request.causation_request_id,
                    conversation_id=tool_request.conversation_id,
                    task_id=tool_request.task_id, step_id=tool_request.step_id, tool=tool_request.tool,
                    status="success", executed_at=now, operation_id=tool_request.operation_id,
                    result={"event_id": "event-real-1"},
                )
            return ToolResult(
                type="tool_result", execution_id=tool_request.execution_id,
                causation_request_id=tool_request.causation_request_id,
                conversation_id=tool_request.conversation_id,
                task_id=tool_request.task_id, step_id=tool_request.step_id, tool=tool_request.tool,
                status="success", executed_at=now, queried_range={
                    "start": tool_request.arguments.start, "end": tool_request.arguments.end,
                }, fetched_at=now, results=[{
                    "event_id": "event-real-1", "title": "不同标题",
                    "start": tool_request.arguments.start.isoformat(),
                    "end": tool_request.arguments.end.isoformat(),
                }],
            )

    adapter = MismatchedCalendarAdapter()
    dispatcher = ToolDispatcher({Tool.CREATE_CALENDAR_EVENT: adapter, Tool.QUERY_CALENDAR: adapter})
    result = AgentRuntime(session, FakeLLM(analysis()), dispatcher).handle(request())

    assert isinstance(result, Final)
    assert result.status == "failure"
    assert result.error.code == "verification_failed"


def test_invalid_tool_result_does_not_enter_runtime(session: Session):
    invalid = ToolResult.model_construct(
        type="tool_result", execution_id="exec_001", causation_request_id="req_001",
        conversation_id="conv_001",
        task_id="task_001", step_id="step_001", tool="query_calendar",
        status="success", executed_at="not-a-datetime",
    )
    with pytest.raises(ValidationError):
        AgentRuntime(session, FakeLLM(analysis())).handle(invalid)
