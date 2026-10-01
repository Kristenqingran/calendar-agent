"""Local macOS bridge from Agent ToolRequest to the Shortcuts CLI."""

from __future__ import annotations

import json
import subprocess
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from uuid import uuid4

from pydantic import TypeAdapter, ValidationError

from .enums import Tool
from .messages import ToolResult
from .tools import ToolRequest

SHORTCUT_NAME = "日程助手-CalendarExecutor"
BRIDGE_HOST = "127.0.0.1"
BRIDGE_PORT = 8765


class MacShortcutBridge:
    def __init__(self, *, shortcut_name: str = SHORTCUT_NAME, timeout: float = 30.0,
                 runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run):
        self.shortcut_name = shortcut_name
        self.timeout = timeout
        self.runner = runner

    def execute(self, request: ToolRequest) -> ToolResult:
        try:
            request = TypeAdapter(ToolRequest).validate_python(request)
        except ValidationError as exc:
            raise ValueError("invalid ToolRequest") from exc
        if request.tool != Tool.CREATE_CALENDAR_EVENT:
            return _failure(request, "unsupported_operation", "Mac Bridge 只支持日历创建。")
        payload = json.dumps(request.model_dump(mode="json"), ensure_ascii=False)
        try:
            completed = self.runner(
                ["shortcuts", "run", self.shortcut_name, "--input-path", "-"],
                input=payload,
                capture_output=True,
                text=True,
                timeout=self.timeout,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return _failure(request, "tool_timeout", "Apple Shortcut 执行超时。", status="unknown",
                            details={"timeout_seconds": self.timeout})
        except OSError as exc:
            return _failure(request, "shortcut_execution_failed", str(exc) or "无法启动 shortcuts。",
                            details={"stdout": "", "stderr": str(exc) or ""})
        if completed.returncode != 0:
            return _failure(
                request, "shortcut_execution_failed",
                completed.stderr.strip() or "Shortcut 执行失败。",
                details=_process_details(completed),
            )
        if not completed.stdout:
            return _failure(
                request, "shortcut_no_output", "Shortcut 执行成功但没有输出。",
                details=_process_details(completed),
            )
        try:
            result = json.loads(completed.stdout)
        except json.JSONDecodeError:
            return _failure(
                request, "malformed_shortcut_response", "Shortcut 输出不是合法 JSON。",
                details=_process_details(completed),
            )
        if not isinstance(result, Mapping) or not isinstance(result.get("event_id"), str) or not result["event_id"]:
            return _failure(
                request, "malformed_shortcut_response", "Shortcut 输出缺少 event_id。",
                details=_process_details(completed),
            )
        return ToolResult(
            type="tool_result", execution_id=request.execution_id,
            causation_request_id=request.causation_request_id,
            conversation_id=request.conversation_id, task_id=request.task_id,
            step_id=request.step_id, tool=request.tool, status="success",
            executed_at=datetime.now(UTC), operation_id=request.operation_id,
            result={"event_id": result["event_id"]},
        )


def handle_json_body(body: bytes, bridge: MacShortcutBridge) -> tuple[int, dict[str, Any]]:
    try:
        payload = json.loads(body)
        request = TypeAdapter(ToolRequest).validate_python(payload)
    except (UnicodeDecodeError, json.JSONDecodeError, ValidationError):
        return 400, {"error": {"code": "invalid_tool_request", "message": "请求不是合法 ToolRequest。"}}
    try:
        result = bridge.execute(request)
    except Exception as exc:
        return 500, {"error": {"code": "bridge_error", "message": str(exc) or "Bridge 执行失败。"}}
    return 200, result.model_dump(mode="json")


def _process_details(completed: subprocess.CompletedProcess[str]) -> dict[str, Any]:
    return {
        "exit_code": completed.returncode,
        "stdout": completed.stdout or "",
        "stderr": completed.stderr or "",
    }


def _failure(request: ToolRequest, code: str, message: str, *, status: str = "failed",
             details: dict[str, Any] | None = None) -> ToolResult:
    return ToolResult(
        type="tool_result", execution_id=request.execution_id,
        causation_request_id=request.causation_request_id,
        conversation_id=request.conversation_id, task_id=request.task_id,
        step_id=request.step_id, tool=request.tool, status=status,
        executed_at=datetime.now(UTC), operation_id=request.operation_id,
        error={"code": code, "message": message, "retryable": False, "details": details},
    )


class BridgeHandler(BaseHTTPRequestHandler):
    bridge: MacShortcutBridge | None = None

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/shortcut":
            self._send(404, {"error": {"code": "not_found", "message": "路径不存在。"}})
            return
        length = self.headers.get("Content-Length")
        if length is None:
            self._send(400, {"error": {"code": "missing_body", "message": "请求体不能为空。"}})
            return
        body = self.rfile.read(int(length))
        if self.bridge is None:
            self._send(500, {"error": {"code": "bridge_not_configured", "message": "Bridge 未配置。"}})
            return
        status, response = handle_json_body(body, self.bridge)
        self._send(status, response)

    def _send(self, status: int, payload: dict[str, Any]) -> None:
        encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, _format: str, *_args: Any) -> None:
        return


def serve(bridge: MacShortcutBridge, host: str = BRIDGE_HOST, port: int = BRIDGE_PORT) -> None:
    handler = type("BoundBridgeHandler", (BridgeHandler,), {"bridge": bridge})
    server = ThreadingHTTPServer((host, port), handler)
    print(f"Mac Shortcut Bridge listening on http://{host}:{port}/shortcut")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def main() -> None:
    serve(MacShortcutBridge())


if __name__ == "__main__":
    main()
