import json
from datetime import datetime
from http.server import ThreadingHTTPServer
from threading import Thread
from typing import Any
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

import pytest

from calendar_agent_protocol.messages import Clarification, Final, ToolRequest
from calendar_agent_protocol.server import (
    AgentRequestHandler,
    ServerConfig,
    authorize_request,
    build_runtime,
    handle_json_body,
)
from calendar_agent_protocol.apple_shortcut import AppleShortcutToolAdapter
from calendar_agent_protocol.dispatcher import MockToolAdapter
from calendar_agent_protocol.enums import Purpose, Tool
from calendar_agent_protocol.local_calendar import LocalCalendarAdapter
from calendar_agent_protocol.persistence import Base, make_engine
from sqlalchemy.orm import Session, sessionmaker


class FakeRuntime:
    def __init__(self, response: Any = None, error: Exception | None = None):
        self.response = response
        self.error = error
        self.request = None

    def handle(self, request):
        self.request = request
        if self.error:
            raise self.error
        return self.response


def test_server_config_defaults(monkeypatch):
    monkeypatch.delenv("AGENT_SERVER_HOST", raising=False)
    monkeypatch.delenv("AGENT_SERVER_PORT", raising=False)

    config = ServerConfig.from_env()

    assert config.host == "127.0.0.1"
    assert config.port == 8000


def test_server_config_supports_explicit_lan_host_and_port(monkeypatch):
    monkeypatch.setenv("AGENT_SERVER_HOST", "0.0.0.0")
    monkeypatch.setenv("AGENT_SERVER_PORT", "18000")
    monkeypatch.setenv("AGENT_API_TOKEN", "lan-test-token")

    config = ServerConfig.from_env()

    assert config.host == "0.0.0.0"
    assert config.port == 18000
    assert config.api_token == "lan-test-token"


def test_non_loopback_listener_requires_api_token(monkeypatch):
    monkeypatch.setenv("AGENT_SERVER_HOST", "0.0.0.0")
    monkeypatch.delenv("AGENT_API_TOKEN", raising=False)

    with pytest.raises(ValueError, match="AGENT_API_TOKEN"):
        ServerConfig.from_env()


def test_api_token_is_not_required_for_default_loopback(monkeypatch):
    monkeypatch.delenv("AGENT_SERVER_HOST", raising=False)
    monkeypatch.delenv("AGENT_API_TOKEN", raising=False)

    assert ServerConfig.from_env().api_token is None


def test_auth_boundary_accepts_only_valid_bearer_token():
    config = ServerConfig(host="0.0.0.0", port=8000, api_token="secret-token")

    assert authorize_request({"Authorization": "Bearer secret-token"}, config)
    assert not authorize_request({}, config)
    assert not authorize_request({"Authorization": "Bearer wrong"}, config)
    assert not authorize_request({"Authorization": "Basic secret-token"}, config)


def test_auth_boundary_is_disabled_for_loopback_without_token():
    config = ServerConfig()

    assert authorize_request({}, config)


def test_auth_boundary_does_not_invoke_runtime_when_unauthorized():
    runtime = FakeRuntime(tool_request())
    config = ServerConfig(host="0.0.0.0", port=8000, api_token="secret-token")

    assert not authorize_request({}, config)
    assert runtime.request is None


def test_serve_uses_environment_listener_configuration(monkeypatch):
    captured = {}

    class FakeServer:
        def __init__(self, address, handler):
            captured["address"] = address

        def serve_forever(self):
            captured["served"] = True

        def server_close(self):
            captured["closed"] = True

    monkeypatch.setenv("AGENT_SERVER_HOST", "0.0.0.0")
    monkeypatch.setenv("AGENT_SERVER_PORT", "18001")
    monkeypatch.setenv("AGENT_API_TOKEN", "lan-test-token")
    monkeypatch.setattr("calendar_agent_protocol.server.ThreadingHTTPServer", FakeServer)

    from calendar_agent_protocol.server import serve

    serve(object())

    assert captured == {"address": ("0.0.0.0", 18001), "served": True, "closed": True}


def test_serve_preserves_validated_config(monkeypatch):
    captured = {}

    class FakeServer:
        def __init__(self, address, handler):
            captured["address"] = address
            captured["config"] = handler.server_config

        def serve_forever(self):
            pass

        def server_close(self):
            pass

    monkeypatch.setattr("calendar_agent_protocol.server.ThreadingHTTPServer", FakeServer)
    config = ServerConfig(
        host="0.0.0.0", port=18002, api_token="token", max_request_bytes=4096
    )

    from calendar_agent_protocol.server import serve

    serve(object(), config=config)

    assert captured["address"] == ("0.0.0.0", 18002)
    assert captured["config"] == config


@pytest.mark.parametrize("value", ["0", "65536", "not-a-port", ""])
def test_server_config_rejects_invalid_port(monkeypatch, value):
    monkeypatch.setenv("AGENT_SERVER_PORT", value)

    with pytest.raises(ValueError, match="AGENT_SERVER_PORT"):
        ServerConfig.from_env()


def test_server_config_rejects_invalid_request_limit(monkeypatch):
    monkeypatch.setenv("AGENT_MAX_REQUEST_BYTES", "512")

    with pytest.raises(ValueError, match="AGENT_MAX_REQUEST_BYTES"):
        ServerConfig.from_env()


def tool_request() -> ToolRequest:
    from calendar_agent_protocol.tools import CreateCalendarEventRequest

    return CreateCalendarEventRequest(
        type="tool_request", execution_id="exec_001", causation_request_id="req_001", conversation_id="conv_001",
        task_id="task_001", step_id="step_001", operation_id="op_001",
        tool="create_calendar_event", arguments={
            "title": "会议", "all_day": False,
            "start": "2026-09-25T15:00:00+08:00",
            "end": "2026-09-25T16:00:00+08:00",
        },
    )


def final_response(conversation_id: str = "conv_001") -> Final:
    return Final(
        type="final", request_id="req_001", conversation_id=conversation_id,
        task_id="task_001", status="success", message="完成",
    )


def test_valid_request_becomes_existing_user_request():
    runtime = FakeRuntime(final_response())
    status, response = handle_json_body(
        '{"request_id":"req_001","conversation_id":"conv_001",'
        '"user_request":"明天下午3点开会"}'.encode(), runtime
    )
    assert status == 200
    assert response["type"] == "final"
    assert runtime.request.message == "明天下午3点开会"
    assert runtime.request.source == "local-http"
    assert runtime.request.current_time.tzinfo is not None
    assert runtime.request.current_time.utcoffset().total_seconds() == 8 * 3600


def test_http_boundary_preserves_optional_client_conversation_id():
    runtime = FakeRuntime(final_response("conv_client_001"))
    status, _ = handle_json_body(
        json.dumps({
            "request_id": "req_001",
            "user_request": "Create a meeting tomorrow.",
            "conversation_id": "conv_client_001",
        }).encode(),
        runtime,
    )

    assert status == 200
    assert runtime.request.conversation_id == "conv_client_001"


def test_http_boundary_rejects_client_managed_internal_ids():
    runtime = FakeRuntime(final_response("conv_client_001"))
    status, response = handle_json_body(
        json.dumps({
            "user_request": "3 PM for one hour",
            "conversation_id": "conv_client_001",
            "task_id": "task_client_001",
            "reply_to_step_id": "step_client_001",
            "operation_id": "op_client_001",
            "execution_id": "exec_client_001",
        }).encode(),
        runtime,
    )

    assert status == 400
    assert response["error"]["code"] == "unsupported_request_fields"
    assert runtime.request is None


def test_http_boundary_rejects_invalid_client_conversation_id():
    runtime = FakeRuntime(final_response())
    status, response = handle_json_body(
        json.dumps({
            "user_request": "安排会议", "request_id": "req_001", "conversation_id": "bad id"
        }).encode(),
        runtime,
    )

    assert status == 400
    assert response["error"]["code"] == "invalid_conversation_id"
    assert runtime.request is None


@pytest.mark.parametrize(
    "payload",
    [
        {"user_request": "安排会议", "request_id": "req_001"},
    ],
)
def test_http_boundary_rejects_partial_request_correlation(payload):
    runtime = FakeRuntime(final_response())
    status, response = handle_json_body(json.dumps(payload).encode(), runtime)

    assert status == 400
    assert response["error"]["code"] == "invalid_request_correlation"
    assert runtime.request is None


def test_http_boundary_preserves_device_timezone():
    runtime = FakeRuntime(final_response("conv_001"))
    status, _ = handle_json_body(
        json.dumps({
            "request_id": "req_001",
            "conversation_id": "conv_001",
            "user_request": "Create a meeting tomorrow.",
            "assistant_timezone": "Asia/Shanghai",
            "device_timezone": "America/Los_Angeles",
        }).encode(),
        runtime,
    )

    assert status == 200
    assert runtime.request.device_timezone == "America/Los_Angeles"


def test_http_timezone_boundary_controls_current_time_offset():
    runtime = FakeRuntime(final_response())
    status, _ = handle_json_body(
        '{"request_id":"req_001","conversation_id":"conv_001",'
        '"user_request":"明天早上9点开会",'
        '"assistant_timezone":"America/Los_Angeles"}'.encode(),
        runtime,
    )

    assert status == 200
    assert str(runtime.request.current_time.tzinfo) == "America/Los_Angeles"
    assert runtime.request.assistant_timezone == "America/Los_Angeles"


def test_invalid_http_timezone_fails_at_boundary():
    status, response = handle_json_body(
        '{"user_request":"安排会议","assistant_timezone":"Mars/Olympus"}'.encode(),
        FakeRuntime(tool_request()),
    )

    assert status == 400
    assert response["error"]["code"] == "invalid_assistant_timezone"


def test_malformed_json():
    status, response = handle_json_body(b"not-json", FakeRuntime(tool_request()))
    assert status == 400
    assert response["error"]["code"] == "malformed_json"


def test_missing_user_request():
    status, response = handle_json_body(b"{}", FakeRuntime(tool_request()))
    assert status == 400
    assert response["error"]["code"] == "missing_user_request"


def test_invalid_user_request_type():
    status, response = handle_json_body(b'{"user_request":123}', FakeRuntime(tool_request()))
    assert status == 400
    assert response["error"]["code"] == "invalid_user_request"


def test_clarification_response_is_returned_unchanged():
    response = Clarification(
        type="clarification", request_id="req_001", conversation_id="conv_001",
        task_id="task_001", step_id="step_001", reason="missing_required_parameter",
        message="请提供时间。", expected_answer={"type": "datetime"},
    )
    status, body = handle_json_body(
        '{"request_id":"req_001","conversation_id":"conv_001",'
        '"user_request":"安排会议"}'.encode(), FakeRuntime(response)
    )
    assert status == 200
    assert body == response.model_dump(mode="json")


def test_final_response_is_returned_unchanged():
    response = Final(
        type="final", request_id="req_001", conversation_id="conv_001", task_id="task_001",
        status="failure", message="不支持", error={
            "code": "unsupported_operation", "message": "不支持", "retryable": False,
        },
    )
    status, body = handle_json_body(
        '{"request_id":"req_001","conversation_id":"conv_001",'
        '"user_request":"删除所有事件"}'.encode(), FakeRuntime(response)
    )
    assert status == 200
    assert body == response.model_dump(mode="json")


def test_internal_tool_request_is_never_exposed_as_public_response():
    status, body = handle_json_body(
        '{"user_request":"安排会议"}'.encode(), FakeRuntime(tool_request())
    )
    assert status == 500
    assert body["error"]["code"] == "internal_execution_boundary"


def test_runtime_exception_is_http_500():
    status, response = handle_json_body('{"user_request":"安排会议"}'.encode(), FakeRuntime(error=RuntimeError("boom")))
    assert status == 500
    assert response["error"]["code"] == "runtime_error"


def test_default_runtime_uses_mock_and_completes_verification(tmp_path):
    engine = make_engine(f"sqlite:///{tmp_path / 'server.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        runtime = build_runtime(session, MockToolAdapter())
        assert isinstance(runtime.dispatcher.adapters[Tool.CREATE_CALENDAR_EVENT], MockToolAdapter)
        status, response = handle_json_body(
            '{"user_request":"明天9点定一个小时的会议"}'.encode(), runtime
        )
        assert status == 200
        assert response["type"] == "final"
        assert response["status"] == "success"


@pytest.mark.parametrize(
    ("user_request", "expected_message"),
    [
        (
            "Create a meeting tomorrow.",
            "What time should the meeting start, and how long should it last?",
        ),
        ("帮我创建明天的会议", "请提供会议的具体开始时间和时长。"),
    ],
)
def test_http_default_runtime_clarification_matches_input_language(
    tmp_path, user_request: str, expected_message: str
):
    engine = make_engine(f"sqlite:///{tmp_path / 'language-server.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        runtime = build_runtime(session)
        status, response = handle_json_body(
            json.dumps({"user_request": user_request}).encode(), runtime
        )

    assert status == 200
    assert response["type"] == "clarification"
    assert response["message"] == expected_message


def test_live_http_server_returns_clarification_in_request_language(tmp_path):
    """Exercise socket HTTP → auth → handler → Runtime → JSON response."""
    engine = make_engine(f"sqlite:///{tmp_path / 'live-language-server.db'}")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    config = ServerConfig(api_token="test-only-token")

    def runtime_factory():
        return build_runtime(session_factory(), MockToolAdapter())

    handler = type(
        "LanguageTestHandler",
        (AgentRequestHandler,),
        {
            "runtime": staticmethod(runtime_factory),
            "server_config": config,
        },
    )
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    cases = [
        (
            "Create a meeting tomorrow.",
            "What time should the meeting start, and how long should it last?",
        ),
        ("明天创建一个会议", "请提供会议的具体开始时间和时长。"),
    ]
    try:
        for user_request, expected_message in cases:
            request = Request(
                f"http://127.0.0.1:{server.server_port}/agent",
                data=json.dumps({"user_request": user_request}, ensure_ascii=False).encode(),
                headers={
                    "Content-Type": "application/json",
                    "Authorization": "Bearer test-only-token",
                },
                method="POST",
            )
            with urlopen(request, timeout=5) as response:
                payload = json.loads(response.read())
            assert response.status == 200
            assert payload["type"] == "clarification"
            assert payload["message"] == expected_message
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_live_http_clarification_followup_resumes_same_task_after_runtime_rebuild(tmp_path):
    """Two real HTTP posts share SQLite state while the Runtime is rebuilt between turns."""
    engine = make_engine(f"sqlite:///{tmp_path / 'clarification-resume-http.db'}")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine)
    adapter = MockToolAdapter()

    def runtime_factory():
        return build_runtime(sessions(), adapter)

    handler = type(
        "ClarificationResumeHandler",
        (AgentRequestHandler,),
        {"runtime": staticmethod(runtime_factory), "server_config": ServerConfig()},
    )
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{server.server_port}/agent"

    def post(payload):
        request = Request(
            url,
            data=json.dumps(payload, ensure_ascii=False).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request, timeout=5) as response:
            return response.status, json.loads(response.read())

    try:
        status1, first = post({"user_request": "Create a calendar meeting tomorrow."})
        assert status1 == 200
        assert first["type"] == "clarification"

        status2, second = post({
            "user_request": "3 PM for one hour",
            "conversation_id": first["conversation_id"],
        })
        assert status2 == 200
        assert second["type"] == "final"
        assert second["status"] == "success"
        assert second["task_id"] == first["task_id"]
        assert second["conversation_id"] == first["conversation_id"]
        assert second["request_id"] != first["request_id"]
        assert len(adapter.events) == 1
        assert adapter.events[0]["title"] == "Meeting"
        assert adapter.events[0]["start"].hour == 15
        assert adapter.events[0]["end"].hour == 16
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


@pytest.mark.parametrize(
    ("user_request", "expected_title", "expected_start"),
    [
        (
            "Create a meeting called Test Meeting on September 30 at 3 PM for one hour.",
            "Test Meeting",
            "2026-09-30T15:00:00+08:00",
        ),
        (
            "Create a meeting tomorrow at 3 PM for one hour.",
            "Meeting",
            "2026-09-25T15:00:00+08:00",
        ),
        (
            "Schedule a one-hour meeting with Bob tomorrow at 3 PM.",
            "Meeting with Bob",
            "2026-09-25T15:00:00+08:00",
        ),
        (
            "明天下午3点和 Bob 开一个小时的会",
            "和 Bob 开会",
            "2026-09-25T15:00:00+08:00",
        ),
        (
            "Schedule a meeting with Bob 明天下午3点 for one hour.",
            "Meeting with Bob",
            "2026-09-25T15:00:00+08:00",
        ),
        (
            "明天和 Bob 开会 at 3 PM for one hour.",
            "和 Bob 开会",
            "2026-09-25T15:00:00+08:00",
        ),
    ],
)
def test_live_http_server_creates_and_verifies_complete_calendar_request(
    tmp_path, monkeypatch, user_request: str, expected_title: str, expected_start: str
):
    class FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            value = cls(2026, 9, 24, 10, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
            return value if tz is None else value.astimezone(tz)

    monkeypatch.setattr("calendar_agent_protocol.server.datetime", FrozenDateTime)
    engine = make_engine(f"sqlite:///{tmp_path / 'live-english-create.db'}")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    adapters = []

    def runtime_factory():
        class RecordingMockAdapter(MockToolAdapter):
            def __init__(self):
                super().__init__()
                self.requests = []

            def execute(self, tool_request):
                self.requests.append(tool_request)
                return super().execute(tool_request)

        adapter = RecordingMockAdapter()
        adapters.append(adapter)
        return build_runtime(session_factory(), adapter)

    config = ServerConfig(api_token="test-only-token")
    handler = type(
        "EnglishCreateTestHandler",
        (AgentRequestHandler,),
        {"runtime": staticmethod(runtime_factory), "server_config": config},
    )
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    request = Request(
        f"http://127.0.0.1:{server.server_port}/agent",
        data=json.dumps({"user_request": user_request}).encode(),
        headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer test-only-token",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=5) as response:
            payload = json.loads(response.read())
        assert response.status == 200
        assert payload["type"] == "final"
        assert payload["status"] == "success"
        assert adapters[0].events[0]["title"] == expected_title
        assert adapters[0].events[0]["start"].isoformat() == expected_start
        assert adapters[0].events[0]["end"].isoformat() == (
            expected_start[:11]
            + f"{int(expected_start[11:13]) + 1:02d}"
            + expected_start[13:]
        )
        assert [call.tool for call in adapters[0].requests] == [
            Tool.CREATE_CALENDAR_EVENT,
            Tool.QUERY_CALENDAR,
        ]
        assert adapters[0].requests[1].purpose == Purpose.VERIFY_STATE
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_http_short_followup_inherits_conversation_language(tmp_path):
    engine = make_engine(f"sqlite:///{tmp_path / 'language-followup.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        runtime = build_runtime(session, MockToolAdapter())
        first_status, first = handle_json_body(
            json.dumps({
                "user_request": "Create a meeting tomorrow.",
            }).encode(),
            runtime,
        )
        followup_status, followup = handle_json_body(
            json.dumps({
                "user_request": "9?",
                "conversation_id": first["conversation_id"],
            }).encode(),
            runtime,
        )

    assert first_status == followup_status == 200
    assert first["message"] == followup["message"]
    assert followup["message"] == (
        "What time should the meeting start, and how long should it last?"
    )


def test_server_can_build_local_calendar_runtime(tmp_path):
    engine = make_engine(f"sqlite:///{tmp_path / 'server-local.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        runtime = build_runtime(session, LocalCalendarAdapter(url="http://127.0.0.1:8770/calendar"))
        assert isinstance(runtime.dispatcher.adapters[Tool.CREATE_CALENDAR_EVENT], LocalCalendarAdapter)


def test_server_defaults_to_mac_agent_host_adapter(tmp_path, monkeypatch):
    from calendar_agent_protocol.mac_host import MacAgentHostAdapter

    monkeypatch.delenv("MAC_AGENT_HOST_EXECUTABLE", raising=False)
    engine = make_engine(f"sqlite:///{tmp_path / 'server-default-host.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        runtime = build_runtime(session)
        adapter = runtime.dispatcher.adapters[Tool.CREATE_CALENDAR_EVENT]
        assert isinstance(adapter, MacAgentHostAdapter)
        assert adapter.executable is None


def test_server_selects_mac_agent_host_when_executable_is_configured(tmp_path, monkeypatch):
    from calendar_agent_protocol.mac_host import MacAgentHostAdapter

    executable = str(tmp_path / "MacAgentHost")
    monkeypatch.setenv("MAC_AGENT_HOST_EXECUTABLE", executable)
    engine = make_engine(f"sqlite:///{tmp_path / 'server-host.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        runtime = build_runtime(session)
        adapter = runtime.dispatcher.adapters[Tool.CREATE_CALENDAR_EVENT]
        assert isinstance(adapter, MacAgentHostAdapter)
        assert adapter.executable == executable


def test_runtime_allows_explicit_apple_shortcut_adapter(tmp_path):
    engine = make_engine(f"sqlite:///{tmp_path / 'server-explicit.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        runtime = build_runtime(session, AppleShortcutToolAdapter(url="http://127.0.0.1:8765/shortcut"))
        assert isinstance(runtime.dispatcher.adapters[Tool.CREATE_CALENDAR_EVENT], AppleShortcutToolAdapter)
