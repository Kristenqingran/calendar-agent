import json
from typing import Any

from calendar_agent_protocol.apple_shortcut import AppleShortcutToolAdapter
from calendar_agent_protocol.messages import ToolResult
from calendar_agent_protocol.tools import CreateCalendarEventRequest


def request() -> CreateCalendarEventRequest:
    return CreateCalendarEventRequest(
        type="tool_request", execution_id="exec_001", causation_request_id="req_001", conversation_id="conv_001",
        task_id="task_001", step_id="step_001", operation_id="op_001",
        tool="create_calendar_event", arguments={
            "title": "会议", "all_day": False,
            "start": "2026-09-25T15:00:00+08:00",
            "end": "2026-09-25T16:00:00+08:00",
        },
    )


class Response:
    def __init__(self, status: int, body: bytes):
        self.status = status
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self) -> bytes:
        return self.body


def test_success_payload_and_result(monkeypatch):
    captured: dict[str, Any] = {}

    def fake_urlopen(http_request, timeout):
        captured["url"] = http_request.full_url
        captured["timeout"] = timeout
        captured["payload"] = json.loads(http_request.data)
        return Response(200, b'{"event_id":"event_123"}')

    monkeypatch.setattr("calendar_agent_protocol.apple_shortcut.urlopen", fake_urlopen)
    result = AppleShortcutToolAdapter(url="https://shortcut.example/run").execute(request())

    assert isinstance(result, ToolResult)
    assert result.status == "success"
    assert result.operation_id == "op_001"
    assert result.conversation_id == "conv_001"
    assert result.task_id == "task_001"
    assert result.step_id == "step_001"
    assert result.result == {"event_id": "event_123"}
    assert captured["url"] == "https://shortcut.example/run"
    assert captured["payload"]["type"] == "tool_request"
    assert captured["payload"]["operation_id"] == "op_001"
    assert captured["payload"]["arguments"] == request().arguments.model_dump(mode="json")


def test_arguments_are_not_modified(monkeypatch):
    original = request().arguments.model_dump(mode="json")
    monkeypatch.setattr(
        "calendar_agent_protocol.apple_shortcut.urlopen",
        lambda *_args, **_kwargs: Response(200, b'{"event_id":"event_123"}'),
    )
    value = request()
    AppleShortcutToolAdapter(url="https://shortcut.example/run").execute(value)
    assert value.arguments.model_dump(mode="json") == original


def test_default_url_is_local_bridge(monkeypatch):
    monkeypatch.delenv("APPLE_SHORTCUT_URL", raising=False)
    captured = {}

    def fake_urlopen(http_request, timeout):
        captured["url"] = http_request.full_url
        return Response(200, b'{"event_id":"event_123"}')

    monkeypatch.setattr("calendar_agent_protocol.apple_shortcut.urlopen", fake_urlopen)
    result = AppleShortcutToolAdapter().execute(request())
    assert result.status == "success"
    assert captured["url"] == "http://127.0.0.1:8765/shortcut"


def test_environment_url_overrides_local_bridge(monkeypatch):
    monkeypatch.setenv("APPLE_SHORTCUT_URL", "http://example.test/custom")
    captured = {}

    def fake_urlopen(http_request, timeout):
        captured["url"] = http_request.full_url
        return Response(200, b'{"event_id":"event_123"}')

    monkeypatch.setattr("calendar_agent_protocol.apple_shortcut.urlopen", fake_urlopen)
    result = AppleShortcutToolAdapter().execute(request())
    assert result.status == "success"
    assert captured["url"] == "http://example.test/custom"


def test_non_2xx_is_failed(monkeypatch):
    monkeypatch.setattr(
        "calendar_agent_protocol.apple_shortcut.urlopen",
        lambda *_args, **_kwargs: Response(500, b"server error"),
    )
    result = AppleShortcutToolAdapter(url="https://shortcut.example/run").execute(request())
    assert result.status == "failed"
    assert result.error.code == "shortcut_http_error"
    assert result.operation_id == "op_001"


def test_timeout_is_unknown_without_retry(monkeypatch):
    calls = 0

    def timeout(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        raise TimeoutError()

    monkeypatch.setattr("calendar_agent_protocol.apple_shortcut.urlopen", timeout)
    result = AppleShortcutToolAdapter(url="https://shortcut.example/run").execute(request())
    assert result.status == "unknown"
    assert result.error.code == "tool_timeout"
    assert calls == 1


def test_malformed_json_is_failed(monkeypatch):
    monkeypatch.setattr(
        "calendar_agent_protocol.apple_shortcut.urlopen",
        lambda *_args, **_kwargs: Response(200, b"not-json"),
    )
    result = AppleShortcutToolAdapter(url="https://shortcut.example/run").execute(request())
    assert result.status == "failed"
    assert result.error.code == "malformed_shortcut_response"


def test_malformed_response_is_failed(monkeypatch):
    monkeypatch.setattr(
        "calendar_agent_protocol.apple_shortcut.urlopen",
        lambda *_args, **_kwargs: Response(200, b'{"ok":true}'),
    )
    result = AppleShortcutToolAdapter(url="https://shortcut.example/run").execute(request())
    assert result.status == "failed"
    assert result.error.code == "malformed_shortcut_response"


def test_bridge_tool_result_failure_is_preserved(monkeypatch):
    bridge_result = {
        "type": "tool_result", "execution_id": "exec_001",
        "causation_request_id": "req_001",
        "conversation_id": "conv_001", "task_id": "task_001", "step_id": "step_001",
        "tool": "create_calendar_event", "status": "failed",
        "executed_at": "2026-09-26T10:00:00Z", "operation_id": "op_001",
        "error": {"code": "shortcut_no_output", "message": "Shortcut 执行成功但没有输出。", "retryable": False},
    }
    monkeypatch.setattr(
        "calendar_agent_protocol.apple_shortcut.urlopen",
        lambda *_args, **_kwargs: Response(200, json.dumps(bridge_result).encode()),
    )
    result = AppleShortcutToolAdapter(url="http://127.0.0.1:8765/shortcut").execute(request())
    assert result.status == "failed"
    assert result.error.code == "shortcut_no_output"


def test_non_calendar_tool_is_not_sent():
    result = AppleShortcutToolAdapter(url="https://shortcut.example/run").execute(
        request().model_copy(update={"tool": "query_calendar"})
    )
    assert result.status == "failed"
    assert result.error.code == "unsupported_operation"
