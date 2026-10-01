import io
import threading
from pathlib import Path

from calendar_agent_protocol.mac_host import MacAgentHostAdapter
from calendar_agent_protocol.messages import ToolResult
from calendar_agent_protocol.tools import CreateCalendarEventRequest, QueryCalendarRequest


def request() -> CreateCalendarEventRequest:
    return CreateCalendarEventRequest(
        type="tool_request", execution_id="exec_001", causation_request_id="req_001", conversation_id="conv_001",
        task_id="task_001", step_id="step_001", operation_id="op_001",
        tool="create_calendar_event", arguments={
            "title": "QA", "all_day": False,
            "start": "2026-09-28T15:00:00+08:00",
            "end": "2026-09-28T16:00:00+08:00",
        },
    )


def test_host_adapter_preserves_request_and_validates_tool_result(monkeypatch):
    captured = {}

    class RecordingStdin(io.StringIO):
        def close(self):
            self.flush()

    class FakeProcess:
        returncode = None

        def __init__(self):
            self.stdin = RecordingStdin()
            self.stdout = io.StringIO(
                '{"type":"tool_result","execution_id":"exec_001","causation_request_id":"req_001",'
                '"conversation_id":"conv_001","task_id":"task_001",'
                '"step_id":"step_001","tool":"create_calendar_event",'
                '"status":"success","executed_at":"2026-09-28T07:00:00Z",'
                '"operation_id":"op_001","result":{"event_id":"real-event"}}\n'
            )
            self.stderr = io.StringIO("")
            self.terminated = False
            self.killed = False
            self.waited = False

        def terminate(self):
            self.terminated = True
            self.returncode = -15

        def kill(self):
            self.killed = True
            self.returncode = -9

        def wait(self, timeout=None):
            self.waited = True
            return self.returncode

        def poll(self):
            return self.returncode

    process = FakeProcess()

    def fake_popen(argv, **kwargs):
        captured["argv"] = argv
        captured["kwargs"] = kwargs
        return process

    monkeypatch.setattr("calendar_agent_protocol.mac_host.subprocess.Popen", fake_popen)

    result = MacAgentHostAdapter(executable="/tmp/MacAgentHost").execute(request())

    assert isinstance(result, ToolResult)
    assert result.status == "success"
    assert result.operation_id == "op_001"
    assert result.result == {"event_id": "real-event"}
    assert captured["argv"] == ["/tmp/MacAgentHost"]
    assert captured["kwargs"]["stdin"] is not None
    assert process.stdin.getvalue().startswith('{"type": "tool_request"')
    assert '"operation_id": "op_001"' in process.stdin.getvalue()
    assert '"title": "QA"' in process.stdin.getvalue()
    assert '"start": "2026-09-28T15:00:00+08:00"' in process.stdin.getvalue()
    assert '"end": "2026-09-28T16:00:00+08:00"' in process.stdin.getvalue()
    assert process.terminated
    assert process.waited


def test_host_adapter_reads_result_before_host_exit(monkeypatch):
    class FakeProcess:
        returncode = None

        def __init__(self):
            self.stdin = io.StringIO()
            self.stdout = io.StringIO(
                '{"type":"tool_result","execution_id":"exec_001","causation_request_id":"req_001",'
                '"conversation_id":"conv_001","task_id":"task_001",'
                '"step_id":"step_001","tool":"create_calendar_event",'
                '"status":"success","executed_at":"2026-09-28T07:00:00Z",'
                '"operation_id":"op_001","result":{"event_id":"real-event"}}\n'
            )
            self.stderr = io.StringIO("")
            self.terminated = False

        def terminate(self):
            self.terminated = True
            self.returncode = -15

        def kill(self):
            self.returncode = -9

        def wait(self, timeout=None):
            return self.returncode

        def poll(self):
            return self.returncode

    process = FakeProcess()
    monkeypatch.setattr(
        "calendar_agent_protocol.mac_host.subprocess.Popen",
        lambda *_args, **_kwargs: process,
    )

    result = MacAgentHostAdapter(executable="/tmp/MacAgentHost").execute(request())

    assert result.status == "success"
    assert process.terminated


def test_host_adapter_timeout_is_unknown(monkeypatch):
    class BlockingStream:
        def readline(self):
            threading.Event().wait()

    class FakeProcess:
        returncode = None

        def __init__(self):
            self.stdin = io.StringIO()
            self.stdout = BlockingStream()
            self.stderr = io.StringIO("")
            self.terminated = False
            self.killed = False

        def terminate(self):
            self.terminated = True
            self.returncode = -15

        def kill(self):
            self.killed = True
            self.returncode = -9

        def wait(self, timeout=None):
            return self.returncode

        def poll(self):
            return self.returncode

    process = FakeProcess()

    monkeypatch.setattr(
        "calendar_agent_protocol.mac_host.subprocess.Popen",
        lambda *_args, **_kwargs: process,
    )
    result = MacAgentHostAdapter(executable="/tmp/MacAgentHost", timeout=0.01).execute(request())
    assert result.status == "unknown"
    assert result.error is not None
    assert result.error.code == "mac_host_timeout"
    assert process.terminated


def test_host_adapter_reports_host_exit_before_result(monkeypatch):
    class FakeProcess:
        returncode = 1

        def __init__(self):
            self.stdin = io.StringIO()
            self.stdout = io.StringIO("")
            self.stderr = io.StringIO("host failed")

        def terminate(self):
            raise AssertionError("already exited")

        def kill(self):
            raise AssertionError("already exited")

        def wait(self, timeout=None):
            return self.returncode

        def poll(self):
            return self.returncode

    monkeypatch.setattr(
        "calendar_agent_protocol.mac_host.subprocess.Popen",
        lambda *_args, **_kwargs: FakeProcess(),
    )
    result = MacAgentHostAdapter(executable="/tmp/MacAgentHost").execute(request())
    assert result.status == "failed"
    assert result.error is not None
    assert result.error.code == "malformed_mac_host_response"


def test_host_adapter_rejects_malformed_stdout_and_cleans_up(monkeypatch):
    class FakeProcess:
        returncode = None

        def __init__(self):
            self.stdin = io.StringIO()
            self.stdout = io.StringIO("not-json\n")
            self.stderr = io.StringIO("")
            self.terminated = False

        def terminate(self):
            self.terminated = True
            self.returncode = -15

        def kill(self):
            self.returncode = -9

        def wait(self, timeout=None):
            return self.returncode

        def poll(self):
            return self.returncode

    process = FakeProcess()
    monkeypatch.setattr(
        "calendar_agent_protocol.mac_host.subprocess.Popen",
        lambda *_args, **_kwargs: process,
    )
    result = MacAgentHostAdapter(executable="/tmp/MacAgentHost").execute(request())
    assert result.status == "failed"
    assert result.error is not None
    assert result.error.code == "malformed_mac_host_response"
    assert process.terminated


def test_swift_host_declares_protocol_correlation_and_query_contract():
    source = (Path(__file__).parents[1] / "mac_gateway" / "mac_agent_host.swift").read_text()

    assert 'let execution_id: String' in source
    assert 'let causation_request_id: String' in source
    assert 'newToolResultRequestID' not in source
    assert 'let supportedTools: Set<String> = ["create_calendar_event", "query_calendar"]' in source
    assert "struct HostError: Encodable" in source
    assert "let event_id: String?" not in source


def test_host_adapter_accepts_verify_query_result_before_host_exit(monkeypatch):
    class FakeProcess:
        returncode = None

        def __init__(self):
            self.stdin = io.StringIO()
            self.stdout = io.StringIO(
                '{"type":"tool_result","execution_id":"exec_query_001","causation_request_id":"req_query_001",'
                '"conversation_id":"conv_001","task_id":"task_001",'
                '"step_id":"step_query","tool":"query_calendar",'
                '"status":"success","executed_at":"2026-09-28T07:00:00Z",'
                '"queried_range":{"start":"2026-09-28T07:00:00Z",'
                '"end":"2026-09-28T08:00:00Z"},'
                '"fetched_at":"2026-09-28T07:00:00Z",'
                '"results":[{"event_id":"real-event","title":"QA",'
                '"start":"2026-09-28T07:00:00+00:00",'
                '"end":"2026-09-28T08:00:00+00:00"}]}\n'
            )
            self.stderr = io.StringIO("")

        def terminate(self):
            self.returncode = -15

        def kill(self):
            self.returncode = -9

        def wait(self, timeout=None):
            return self.returncode

        def poll(self):
            return self.returncode

    process = FakeProcess()
    monkeypatch.setattr(
        "calendar_agent_protocol.mac_host.subprocess.Popen",
        lambda *_args, **_kwargs: process,
    )
    query = QueryCalendarRequest(
        type="tool_request", execution_id="exec_query_001", causation_request_id="req_query_001", conversation_id="conv_001",
        task_id="task_001", step_id="step_query", tool="query_calendar",
        purpose="verify_state", arguments={
            "start": "2026-09-28T07:00:00Z", "end": "2026-09-28T08:00:00Z",
            "target_id": "real-event", "candidate": {"title": "QA"},
        },
    )

    result = MacAgentHostAdapter(executable="/tmp/MacAgentHost").execute(query)

    assert result.status == "success"
    assert result.tool == "query_calendar"
    assert result.operation_id is None
    assert result.results == [{
        "event_id": "real-event", "title": "QA",
        "start": "2026-09-28T07:00:00+00:00",
        "end": "2026-09-28T08:00:00+00:00",
    }]
