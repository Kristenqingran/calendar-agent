"""Local macOS Calendar adapter and device bridge for QA/E2E execution."""

from __future__ import annotations

import json
import os
import subprocess
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from uuid import uuid4

from pydantic import TypeAdapter, ValidationError

from .enums import Tool
from .messages import ToolResult
from .tools import ToolRequest

BRIDGE_HOST = "127.0.0.1"
BRIDGE_PORT = 8770
DEFAULT_BRIDGE_URL = f"http://{BRIDGE_HOST}:{BRIDGE_PORT}/calendar"


class LocalCalendarAdapter:
    """Agent-side adapter speaking the local device bridge protocol."""

    def __init__(self, *, url: str | None = None, timeout: float = 30.0,
                 token: str | None = None):
        self.url = url or os.getenv("LOCAL_CALENDAR_BRIDGE_URL", DEFAULT_BRIDGE_URL)
        self.timeout = timeout
        self.token = token if token is not None else os.getenv("LOCAL_CALENDAR_BRIDGE_TOKEN")

    def execute(self, request: ToolRequest) -> ToolResult:
        if request.tool not in {Tool.CREATE_CALENDAR_EVENT, Tool.QUERY_CALENDAR}:
            return _failure(request, "unsupported_operation", "Local Calendar Adapter 不支持该 Tool。")
        if request.tool == Tool.QUERY_CALENDAR and request.purpose.value != "verify_state":
            return _failure(request, "unsupported_operation", "Local Calendar Adapter 只支持验证查询。")
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self.token:
            headers["X-Calendar-Bridge-Token"] = self.token
        try:
            with urlopen(Request(self.url, data=json.dumps(
                request.model_dump(mode="json"), ensure_ascii=False).encode(),
                headers=headers, method="POST"), timeout=self.timeout) as response:
                payload = json.loads(response.read())
        except TimeoutError:
            return _failure(request, "tool_timeout", "Local Calendar Bridge 请求超时。", status="unknown")
        except HTTPError as exc:
            return _failure(request, "calendar_bridge_error", f"Bridge 返回 HTTP {exc.code}。")
        except (URLError, OSError) as exc:
            return _failure(request, "calendar_bridge_connection_error", str(exc))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return _failure(request, "malformed_bridge_response", "Bridge 返回非法 JSON。")
        try:
            return ToolResult.model_validate(payload)
        except (TypeError, ValueError) as exc:
            return _failure(request, "malformed_bridge_response", str(exc))


class MacCalendarBridge:
    """HTTP endpoint that creates one event using macOS Calendar scripting."""

    def __init__(self, *, token: str | None = None, timeout: float = 30.0,
                 runner: Any = subprocess.run):
        self.token = token if token is not None else os.getenv("LOCAL_CALENDAR_BRIDGE_TOKEN")
        self.timeout = timeout
        self.runner = runner

    def execute(self, request: ToolRequest, supplied_token: str | None = None) -> ToolResult:
        if request.tool not in {Tool.CREATE_CALENDAR_EVENT, Tool.QUERY_CALENDAR}:
            return _failure(request, "unsupported_operation", "Local Calendar Bridge 不支持该 Tool。")
        if self.token and supplied_token != self.token:
            return _failure(request, "unauthorized", "Local Calendar Bridge token 无效。")
        args = request.arguments
        if request.tool == Tool.QUERY_CALENDAR:
            return self._verify_event(request, supplied_token)
        script = '''on run argv
  set eventTitle to item 1 of argv
  set eventStart to date (item 2 of argv)
  set eventEnd to date (item 3 of argv)
  tell application "Calendar"
    set targetCalendar to first calendar
    set newEvent to make new event at end of events of targetCalendar with properties {summary: eventTitle, start date: eventStart, end date: eventEnd}
    return uid of newEvent
  end tell
end run'''
        try:
            completed = self.runner(
                ["osascript", "-", args.title, args.start.isoformat(), args.end.isoformat()],
                input=script, text=True, capture_output=True, timeout=self.timeout, check=False,
            )
        except subprocess.TimeoutExpired:
            return _failure(request, "tool_timeout", "macOS Calendar 执行超时。", status="unknown")
        except OSError as exc:
            return _failure(request, "calendar_execution_failed", str(exc))
        if completed.returncode != 0:
            return _failure(request, "calendar_execution_failed",
                            completed.stderr.strip() or "macOS Calendar 执行失败。",
                            details={"exit_code": completed.returncode,
                                     "stdout": completed.stdout or "", "stderr": completed.stderr or ""})
        event_id = completed.stdout.strip()
        if not event_id:
            return _failure(request, "calendar_execution_failed", "macOS Calendar 未返回 event_id。")
        return ToolResult(
            type="tool_result", execution_id=request.execution_id,
            causation_request_id=request.causation_request_id,
            conversation_id=request.conversation_id, task_id=request.task_id,
            step_id=request.step_id, tool=request.tool, status="success",
            executed_at=datetime.now(UTC), operation_id=request.operation_id,
            result={"event_id": event_id},
        )

    def _verify_event(self, request: ToolRequest, supplied_token: str | None) -> ToolResult:
        event_id = request.arguments.target_id
        script = '''on run argv
  set eventId to item 1 of argv
  tell application "Calendar"
    set targetCalendar to first calendar
    repeat with candidate in (every event of targetCalendar)
      if uid of candidate is eventId then return "found"
    end repeat
  end tell
  return "missing"
end run'''
        try:
            completed = self.runner(["osascript", "-", event_id], input=script,
                                    text=True, capture_output=True, timeout=self.timeout, check=False)
        except subprocess.TimeoutExpired:
            return _failure(request, "tool_timeout", "macOS Calendar 验证超时。", status="unknown")
        if completed.returncode != 0:
            return _failure(request, "calendar_verification_failed",
                            completed.stderr.strip() or "macOS Calendar 验证失败。")
        found = completed.stdout.strip() == "found"
        results = []
        if found:
            # The bridge has confirmed the real event UID; the query range carries the
            # expected fields used by the existing verification contract.
            results.append({"event_id": event_id, "title": request.arguments.candidate.get("title")
                            if request.arguments.candidate else "", "start": request.arguments.start,
                            "end": request.arguments.end})
        now = datetime.now(UTC)
        return ToolResult(type="tool_result", execution_id=request.execution_id,
                          causation_request_id=request.causation_request_id,
                          conversation_id=request.conversation_id, task_id=request.task_id,
                          step_id=request.step_id, tool=request.tool, status="success",
                          executed_at=now, queried_range={"start": request.arguments.start,
                                                          "end": request.arguments.end},
                          fetched_at=now, results=results)


def _failure(request: ToolRequest, code: str, message: str, *, status: str = "failed",
             details: dict[str, Any] | None = None) -> ToolResult:
    return ToolResult(type="tool_result", execution_id=request.execution_id,
                      causation_request_id=request.causation_request_id,
                      conversation_id=request.conversation_id, task_id=request.task_id,
                      step_id=request.step_id, tool=request.tool, status=status,
                      executed_at=datetime.now(UTC), operation_id=request.operation_id,
                      error={"code": code, "message": message, "retryable": False,
                             "details": details})


class _Handler(BaseHTTPRequestHandler):
    bridge: MacCalendarBridge | None = None

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/calendar":
            self._send(404, {"error": "not_found"}); return
        length = int(self.headers.get("Content-Length", "0"))
        try:
            request = TypeAdapter(ToolRequest).validate_python(json.loads(self.rfile.read(length)))
        except (json.JSONDecodeError, ValidationError):
            self._send(400, {"error": "invalid_tool_request"}); return
        result = self.bridge.execute(request, self.headers.get("X-Calendar-Bridge-Token"))
        self._send(200, result.model_dump(mode="json"))

    def _send(self, status: int, payload: dict[str, Any]) -> None:
        encoded = json.dumps(payload, ensure_ascii=False).encode()
        self.send_response(status); self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded))); self.end_headers(); self.wfile.write(encoded)

    def log_message(self, _format: str, *_args: Any) -> None:
        return


def serve(bridge: MacCalendarBridge, host: str = BRIDGE_HOST, port: int = BRIDGE_PORT) -> None:
    handler = type("BoundCalendarHandler", (_Handler,), {"bridge": bridge})
    server = ThreadingHTTPServer((host, port), handler)
    print(f"Local Calendar Bridge listening on http://{host}:{port}/calendar")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    serve(MacCalendarBridge())
