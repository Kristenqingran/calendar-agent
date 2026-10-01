from __future__ import annotations

import json
from contextlib import contextmanager
from http.server import ThreadingHTTPServer
from threading import Thread
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select

from calendar_agent_protocol.dispatcher import MockToolAdapter
from calendar_agent_protocol.domain import TaskEntity, TaskStatus
from calendar_agent_protocol.enums import Intent, ObjectType
from calendar_agent_protocol.persistence import Base, make_engine
from calendar_agent_protocol.persistence import StateTransitionRow, TaskRow
from calendar_agent_protocol.repository import (
    ClarificationRepository,
    InboundReceiptRepository,
    TaskRepository,
)
from calendar_agent_protocol.server import AgentRequestHandler, ServerConfig, build_runtime


class RecordingMockAdapter(MockToolAdapter):
    def __init__(self):
        super().__init__()
        self.tools = []

    def execute(self, request):
        self.tools.append(request.tool.value)
        return super().execute(request)


@contextmanager
def live_agent(tmp_path):
    engine = make_engine(f"sqlite:///{tmp_path / 'clarification-resume.db'}")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine)
    adapter = RecordingMockAdapter()

    def runtime_factory():
        # Intentionally construct a new Runtime and Session for every HTTP post.
        return build_runtime(sessions(), adapter)

    handler = type(
        "ResumeIntegrationHandler", (AgentRequestHandler,),
        {"runtime": staticmethod(runtime_factory), "server_config": ServerConfig()},
    )
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server, sessions, adapter
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        engine.dispose()


def post(server, payload):
    request = Request(
        f"http://127.0.0.1:{server.server_port}/agent",
        data=json.dumps(payload, ensure_ascii=False).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=5) as response:
            return response.status, json.loads(response.read())
    except HTTPError as response:
        return response.code, json.loads(response.read())


@pytest.mark.parametrize(
    ("initial", "answer", "expected_language"),
    [
        ("Create a calendar meeting tomorrow.", "3 PM for one hour", "The calendar event was created and verified."),
        ("明天创建一个会议", "下午3点，持续一小时", "日历事件已创建并验证。"),
    ],
)
def test_real_http_bilingual_resume_reaches_verified_final(
    tmp_path, initial, answer, expected_language
):
    with live_agent(tmp_path) as (server, sessions, adapter):
        first_status, first = post(server, {"user_request": initial})
        assert first_status == 200
        assert first["type"] == "clarification"
        assert adapter.tools == []

        second_status, second = post(server, {
            "user_request": answer,
            "conversation_id": first["conversation_id"],
        })
        with sessions() as session:
            task = TaskRepository(session).get(first["task_id"])
            clarification = ClarificationRepository(session).list_for_task(first["task_id"])[0]
            transitions = session.scalars(
                select(StateTransitionRow).where(StateTransitionRow.task_id == first["task_id"])
            ).all()
            first_receipt = InboundReceiptRepository(session).get(first["request_id"])
            second_receipt = InboundReceiptRepository(session).get(second["request_id"])

    assert second_status == 200
    assert second["type"] == "final"
    assert second["status"] == "success"
    assert second["message"] == expected_language
    assert second["task_id"] == first["task_id"]
    assert second["conversation_id"] == first["conversation_id"]
    assert second["request_id"] != first["request_id"]
    assert adapter.tools == ["create_calendar_event", "query_calendar"]
    assert len(adapter.events) == 1
    assert task.current_state == "succeeded"
    assert clarification.resolved_at is not None
    assert clarification.user_response["request_id"] == second["request_id"]
    assert first_receipt.response_payload["type"] == "clarification"
    assert second_receipt.response_payload["status"] == "success"
    assert any(
        row.from_state == "waiting_clarification"
        and row.to_state == "analyzing_clarification"
        for row in transitions
    )


def test_external_http_schema_allows_server_generated_request_id_for_followup(schema_validator):
    validator = schema_validator("agent-http-request-v2.schema.json")

    assert validator.is_valid({
        "user_request": "3 PM for one hour",
        "conversation_id": "conv_http_001",
    })
    assert validator.is_valid({"user_request": "Create a meeting tomorrow."})
    assert not validator.is_valid({
        "request_id": "req_http_001",
        "user_request": "3 PM for one hour",
    })


def test_http_multiple_clarification_rounds_keep_one_task_and_delay_write(tmp_path):
    with live_agent(tmp_path) as (server, _sessions, adapter):
        status1, first = post(server, {"user_request": "Create a meeting."})
        assert status1 == 200 and first["type"] == "clarification"
        conversation_id = first["conversation_id"]
        task_id = first["task_id"]

        status2, date_answer = post(server, {
            "user_request": "tomorrow", "conversation_id": conversation_id,
        })
        assert status2 == 200 and date_answer["type"] == "clarification"
        assert date_answer["task_id"] == task_id
        assert adapter.tools == []

        status3, time_answer = post(server, {
            "user_request": "3 PM", "conversation_id": conversation_id,
        })
        assert status3 == 200 and time_answer["type"] == "clarification"
        assert time_answer["task_id"] == task_id
        assert adapter.tools == []

        status4, final = post(server, {
            "user_request": "one hour", "conversation_id": conversation_id,
        })

    assert status4 == 200 and final["type"] == "final"
    assert final["status"] == "success"
    assert final["task_id"] == task_id
    assert len({first["task_id"], date_answer["task_id"], time_answer["task_id"], final["task_id"]}) == 1
    assert len({first["request_id"], date_answer["request_id"], time_answer["request_id"], final["request_id"]}) == 4
    assert adapter.tools == ["create_calendar_event", "query_calendar"]
    assert len(adapter.events) == 1


def test_http_response_language_follows_latest_explicit_clarification_language(tmp_path):
    with live_agent(tmp_path) as (server, _sessions, adapter):
        _, first = post(server, {"user_request": "帮我创建一个会议"})
        assert first["type"] == "clarification"
        conversation_id = first["conversation_id"]

        _, date_clarification = post(server, {
            "user_request": "tomorrow", "conversation_id": conversation_id,
        })
        _, time_clarification = post(server, {
            "user_request": "3 PM", "conversation_id": conversation_id,
        })
        _, final = post(server, {
            "user_request": "one hour", "conversation_id": conversation_id,
        })

    assert date_clarification["type"] == "clarification"
    assert date_clarification["message"].isascii()
    assert time_clarification["type"] == "clarification"
    assert time_clarification["message"].isascii()
    assert final["status"] == "success"
    assert adapter.tools == ["create_calendar_event", "query_calendar"]


def test_http_resume_uses_persisted_timezone_when_followup_omits_timezone(tmp_path):
    with live_agent(tmp_path) as (server, _sessions, adapter):
        status1, first = post(server, {
            "user_request": "Create a calendar meeting tomorrow.",
            "assistant_timezone": "America/New_York",
        })
        assert status1 == 200 and first["type"] == "clarification"
        status2, final = post(server, {
            "user_request": "3 PM for one hour",
            "conversation_id": first["conversation_id"],
        })

    assert status2 == 200 and final["status"] == "success"
    event_start = adapter.events[0]["start"]
    assert event_start.hour == 15
    assert event_start.utcoffset().total_seconds() == -4 * 60 * 60


def test_http_unknown_or_wrong_conversation_does_not_resume_or_write(tmp_path):
    with live_agent(tmp_path) as (server, _sessions, adapter):
        unknown_status, unknown = post(server, {
            "user_request": "3 PM for one hour", "conversation_id": "conv_unknown_001",
        })
        assert unknown_status == 404
        assert unknown["error"]["code"] == "unknown_conversation"

        _, first = post(server, {"user_request": "Create a meeting tomorrow."})
        wrong_status, wrong = post(server, {
            "user_request": "3 PM for one hour", "conversation_id": "conv_wrong_001",
        })

    assert wrong_status == 404
    assert wrong["error"]["code"] == "unknown_conversation"
    assert adapter.tools == []
    assert len(adapter.events) == 0
    assert first["type"] == "clarification"


def test_http_completed_conversation_rejects_followup_without_creating_task(tmp_path):
    with live_agent(tmp_path) as (server, _sessions, adapter):
        _, first = post(server, {
            "user_request": "Create a meeting tomorrow at 3 PM for one hour."
        })
        assert first["type"] == "final" and first["status"] == "success"
        status, response = post(server, {
            "user_request": "another answer", "conversation_id": first["conversation_id"],
        })
        with _sessions() as session:
            task_count = len(session.scalars(select(TaskRow)).all())

    assert status == 409
    assert response["error"]["code"] == "no_pending_clarification"
    assert task_count == 1
    assert len(adapter.events) == 1


def test_http_retry_of_same_clarification_request_replays_final_without_duplicate_write(tmp_path):
    with live_agent(tmp_path) as (server, _sessions, adapter):
        _, first = post(server, {"user_request": "Create a meeting tomorrow."})
        followup = {
            "request_id": "req_resume_retry_001",
            "conversation_id": first["conversation_id"],
            "user_request": "3 PM for one hour",
        }
        first_status, first_final = post(server, followup)
        retry_status, retry_final = post(server, followup)

    assert first_status == retry_status == 200
    assert first_final["type"] == retry_final["type"] == "final"
    assert first_final == retry_final
    assert len(adapter.events) == 1
    assert adapter.tools == ["create_calendar_event", "query_calendar"]


def test_http_clarification_answer_limit_fails_same_task_without_tool_dispatch(tmp_path):
    with live_agent(tmp_path) as (server, _sessions, adapter):
        _, first = post(server, {"user_request": "Create a meeting."})
        conversation_id = first["conversation_id"]
        task_id = first["task_id"]
        responses = []
        for _ in range(5):
            status, response = post(server, {
                "user_request": "tomorrow", "conversation_id": conversation_id,
            })
            assert status == 200
            responses.append(response)
        limit_status, limit = post(server, {
            "user_request": "tomorrow", "conversation_id": conversation_id,
        })

    assert all(response["type"] == "clarification" for response in responses)
    assert all(response["task_id"] == task_id for response in responses)
    assert limit_status == 200
    assert limit["type"] == "final" and limit["status"] == "failure"
    assert limit["task_id"] == task_id
    assert limit["error"]["code"] == "clarification_limit_reached"
    assert adapter.tools == []
    assert adapter.events == []


def test_http_multiple_waiting_tasks_fail_closed(tmp_path):
    with live_agent(tmp_path) as (server, sessions, adapter):
        _, first = post(server, {"user_request": "Create a meeting tomorrow."})
        with sessions() as session:
            task = TaskEntity(
                task_id="task_second_waiting", conversation_id=first["conversation_id"],
                original_message="another request", object=ObjectType.CALENDAR_EVENT,
                intent=Intent.CREATE, current_state=TaskStatus.WAITING_CLARIFICATION,
                current_step_id="step_second_waiting",
            )
            TaskRepository(session).create(task)
            from calendar_agent_protocol.repository import StepRepository

            StepRepository(session).create(
                step_id="step_second_waiting", task_id=task.task_id,
                step_type="clarification", status="in_progress",
            )
            ClarificationRepository(session).save(
                step_id="step_second_waiting", task_id=task.task_id,
                reason="missing_required_parameter", message="time?",
                expected_answer={"type": "datetime_range"},
                blocked_from_state="planning",
            )
            session.commit()
        status, response = post(server, {
            "user_request": "3 PM for one hour",
            "conversation_id": first["conversation_id"],
        })

    assert status == 409
    assert response["error"]["code"] == "ambiguous_pending_clarification"
    assert adapter.tools == []
    assert adapter.events == []


def test_http_multiple_pending_clarifications_for_one_task_fail_closed(tmp_path):
    with live_agent(tmp_path) as (server, sessions, adapter):
        _, first = post(server, {"user_request": "Create a meeting tomorrow."})
        with sessions() as session:
            from calendar_agent_protocol.repository import StepRepository

            StepRepository(session).create(
                step_id="step_orphan_pending", task_id=first["task_id"],
                step_type="clarification", status="in_progress",
            )
            ClarificationRepository(session).save(
                step_id="step_orphan_pending", task_id=first["task_id"],
                reason="missing_required_parameter", message="another question?",
                expected_answer={"type": "datetime_range"},
                blocked_from_state="planning",
            )
            session.commit()
        status, response = post(server, {
            "user_request": "3 PM for one hour",
            "conversation_id": first["conversation_id"],
        })

    assert status == 409
    assert response["error"]["code"] == "stale_clarification"
    assert adapter.tools == []
    assert adapter.events == []
