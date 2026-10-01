import json
import subprocess

from calendar_agent_protocol.mac_bridge import MacShortcutBridge, handle_json_body
from calendar_agent_protocol.messages import ToolResult
from calendar_agent_protocol.tools import CreateCalendarEventRequest


def request() -> CreateCalendarEventRequest:
    return CreateCalendarEventRequest(
        type="tool_request", execution_id="exec_001", causation_request_id="req_001", conversation_id="conv_001",
        task_id="task_001", step_id="step_001", operation_id="op_001",
        tool="create_calendar_event", arguments={
            "title": "QA Test Event", "all_day": False,
            "start": "2026-09-25T15:00:00+08:00", "end": "2026-09-25T16:00:00+08:00",
        },
    )


def test_bridge_passes_tool_request_to_shortcuts_and_returns_result():
    calls = {}

    def runner(command, **kwargs):
        calls["command"] = command
        calls["input"] = json.loads(kwargs["input"])
        return subprocess.CompletedProcess(command, 0, '{"event_id":"real_event_1"}', "")

    result = MacShortcutBridge(runner=runner).execute(request())
    assert isinstance(result, ToolResult)
    assert result.status == "success"
    assert result.operation_id == "op_001"
    assert calls["command"] == ["shortcuts", "run", "日程助手-CalendarExecutor", "--input-path", "-"]
    assert calls["input"]["arguments"]["title"] == "QA Test Event"
    assert calls["input"]["operation_id"] == "op_001"


def test_bridge_allows_explicit_shortcut_name_override():
    calls = {}

    def runner(command, **kwargs):
        calls["command"] = command
        return subprocess.CompletedProcess(command, 0, '{"event_id":"real_event_2"}', "")

    result = MacShortcutBridge(shortcut_name="QA-Calendar-Executor", runner=runner).execute(request())
    assert result.status == "success"
    assert calls["command"] == ["shortcuts", "run", "QA-Calendar-Executor", "--input-path", "-"]


def test_bridge_timeout_is_unknown_without_retry():
    calls = 0

    def runner(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        raise subprocess.TimeoutExpired("shortcuts", 1)

    result = MacShortcutBridge(runner=runner).execute(request())
    assert result.status == "unknown"
    assert result.error.code == "tool_timeout"
    assert calls == 1


def test_bridge_failure_and_malformed_output_are_explicit():
    failed = MacShortcutBridge(runner=lambda *a, **k: subprocess.CompletedProcess([], 1, "", "permission denied")).execute(request())
    assert failed.status == "failed"
    assert failed.error.code == "shortcut_execution_failed"
    assert failed.error.details == {"exit_code": 1, "stdout": "", "stderr": "permission denied"}
    malformed = MacShortcutBridge(runner=lambda *a, **k: subprocess.CompletedProcess([], 0, '{"ok":true}', "")).execute(request())
    assert malformed.status == "failed"
    assert malformed.error.code == "malformed_shortcut_response"


def test_bridge_empty_output_is_explicit():
    result = MacShortcutBridge(
        runner=lambda *a, **k: subprocess.CompletedProcess([], 0, "", "diagnostic stderr")
    ).execute(request())
    assert result.error.code == "shortcut_no_output"
    assert result.error.details["stdout"] == ""
    assert result.error.details["stderr"] == "diagnostic stderr"


def test_bridge_http_body_returns_tool_result():
    status, body = handle_json_body(
        json.dumps(request().model_dump(mode="json")).encode(),
        MacShortcutBridge(runner=lambda *a, **k: subprocess.CompletedProcess([], 0, '{"event_id":"e1"}', "")),
    )
    assert status == 200
    assert body["result"] == {"event_id": "e1"}
