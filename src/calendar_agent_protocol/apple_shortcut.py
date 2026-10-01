"""HTTP adapter for an external Apple Shortcut endpoint."""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from uuid import uuid4

from .enums import Tool
from .messages import ToolResult
from .tools import ToolRequest

DEFAULT_BRIDGE_URL = "http://127.0.0.1:8765/shortcut"


class AppleShortcutToolAdapter:
    """Execute the supported write Tool through a configured HTTP endpoint."""

    def __init__(self, *, url: str | None = None, timeout: float = 30.0):
        self.url = url if url is not None else os.getenv("APPLE_SHORTCUT_URL", DEFAULT_BRIDGE_URL)
        self.timeout = timeout

    def execute(self, request: ToolRequest) -> ToolResult:
        if request.tool != Tool.CREATE_CALENDAR_EVENT:
            return _failure(request, "unsupported_operation", "Apple Shortcut Adapter 只支持日历创建。")
        if not self.url:
            return _failure(request, "shortcut_url_not_configured", "APPLE_SHORTCUT_URL 未配置。")

        payload = request.model_dump(mode="json")
        http_request = Request(
            self.url,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            method="POST",
        )
        try:
            with urlopen(http_request, timeout=self.timeout) as response:
                status = getattr(response, "status", None)
                if status is None:
                    status = response.getcode()
                body = response.read()
        except TimeoutError:
            return _failure(request, "tool_timeout", "Apple Shortcut 请求超时。", status="unknown")
        except HTTPError as exc:
            return _failure(request, "shortcut_http_error", f"Apple Shortcut 返回 HTTP {exc.code}。")
        except URLError as exc:
            return _failure(request, "shortcut_connection_error", str(exc.reason))
        except OSError as exc:
            return _failure(request, "shortcut_connection_error", str(exc))

        if status < 200 or status >= 300:
            return _failure(request, "shortcut_http_error", f"Apple Shortcut 返回 HTTP {status}。")
        try:
            response_payload = json.loads(body)
        except (UnicodeDecodeError, json.JSONDecodeError):
            return _failure(request, "malformed_shortcut_response", "Apple Shortcut 返回了非法 JSON。")
        if not isinstance(response_payload, Mapping):
            return _failure(request, "malformed_shortcut_response", "Shortcut response 必须是 JSON object。")
        if response_payload.get("type") == "tool_result":
            try:
                return ToolResult.model_validate(response_payload)
            except (TypeError, ValueError) as exc:
                return _failure(request, "malformed_shortcut_response",
                                f"Bridge 返回的 ToolResult 无效：{exc}")
        event_id = response_payload.get("event_id")
        if not isinstance(event_id, str) or not event_id:
            return _failure(request, "malformed_shortcut_response", "Shortcut response 缺少 event_id。")
        return ToolResult(
            type="tool_result", execution_id=request.execution_id,
            causation_request_id=request.causation_request_id,
            conversation_id=request.conversation_id, task_id=request.task_id,
            step_id=request.step_id, tool=request.tool, status="success",
            executed_at=datetime.now(UTC), operation_id=request.operation_id,
            result={"event_id": event_id},
        )


def _failure(request: ToolRequest, code: str, message: str, *, status: str = "failed") -> ToolResult:
    return ToolResult(
        type="tool_result", execution_id=request.execution_id,
        causation_request_id=request.causation_request_id,
        conversation_id=request.conversation_id, task_id=request.task_id,
        step_id=request.step_id, tool=request.tool, status=status,
        executed_at=datetime.now(UTC), operation_id=request.operation_id,
        error={"code": code, "message": message, "retryable": False},
    )


__all__ = ["AppleShortcutToolAdapter"]
