"""Adapter for the local MacAgentHost JSON-lines execution boundary."""

from __future__ import annotations

import json
import os
import subprocess
import threading
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from pydantic import TypeAdapter, ValidationError

from .messages import ToolResult
from .tools import ToolRequest


class MacAgentHostAdapter:
    """Execute one validated ToolRequest through the native Mac host process."""

    def __init__(self, *, executable: str | None = None, timeout: float = 60.0):
        self.executable = executable or os.getenv("MAC_AGENT_HOST_EXECUTABLE")
        self.timeout = timeout

    def execute(self, request: ToolRequest) -> ToolResult:
        if not self.executable:
            return self._failure(request, "mac_host_not_configured", "未配置 MAC_AGENT_HOST_EXECUTABLE。")
        payload = json.dumps(request.model_dump(mode="json"), ensure_ascii=False) + "\n"
        process: subprocess.Popen[str] | None = None
        try:
            process = subprocess.Popen(
                [self.executable],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )

            assert process.stdin is not None
            assert process.stdout is not None
            process.stdin.write(payload)
            process.stdin.flush()
            process.stdin.close()

            output: dict[str, str] = {}

            def read_stdout() -> None:
                assert process is not None and process.stdout is not None
                output["stdout"] = process.stdout.readline()

            reader = threading.Thread(target=read_stdout, daemon=True)
            reader.start()
            reader.join(self.timeout)
            if reader.is_alive():
                return self._failure(
                    request, "mac_host_timeout", "MacAgentHost 执行超时。", status="unknown"
                )

            line = output.get("stdout", "").strip()
            if not line:
                return self._failure(request, "malformed_mac_host_response", "MacAgentHost 没有返回结果。")
            try:
                result_payload = json.loads(line)
                return ToolResult.model_validate(result_payload)
            except (json.JSONDecodeError, ValidationError, TypeError, ValueError) as exc:
                return self._failure(request, "malformed_mac_host_response", str(exc))
        except OSError as exc:
            return self._failure(request, "mac_host_unavailable", str(exc))
        finally:
            if process is not None:
                self._cleanup_process(process)

    @staticmethod
    def _cleanup_process(process: subprocess.Popen[str]) -> None:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()

    @staticmethod
    def _failure(request: ToolRequest, code: str, message: str, *, status: str = "failed") -> ToolResult:
        return ToolResult(
            type="tool_result", execution_id=request.execution_id,
            causation_request_id=request.causation_request_id,
            conversation_id=request.conversation_id, task_id=request.task_id,
            step_id=request.step_id, tool=request.tool, status=status,
            executed_at=datetime.now(UTC),
            operation_id=request.operation_id if request.tool.is_write else None,
            error={"code": code, "message": message, "retryable": False},
        )


__all__ = ["MacAgentHostAdapter"]
