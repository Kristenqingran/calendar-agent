"""Minimal local HTTP entry point for the existing AgentRuntime."""

from __future__ import annotations

import hmac
import json
import os
from dataclasses import dataclass
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Mapping
from uuid import uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import TypeAdapter, ValidationError

from .messages import AgentResponse, ClarificationResponse, UserRequest
from .repository import (
    ClarificationRepository,
    ConversationRepository,
    InboundReceiptRepository,
    TaskRepository,
)
from .tools import ToolRequest
from .types import IanaTimezone, ProtocolId

DEFAULT_ASSISTANT_TIMEZONE = "Asia/Shanghai"
DEFAULT_MAX_REQUEST_BYTES = 64 * 1024


@dataclass(frozen=True)
class ServerConfig:
    host: str = "127.0.0.1"
    port: int = 8000
    api_token: str | None = None
    max_request_bytes: int = DEFAULT_MAX_REQUEST_BYTES

    def validate(self) -> "ServerConfig":
        if not self.host.strip():
            raise ValueError("AGENT_SERVER_HOST must not be empty")
        if not 1 <= self.port <= 65535:
            raise ValueError("AGENT_SERVER_PORT must be between 1 and 65535")
        if self.api_token is not None and not self.api_token:
            raise ValueError("AGENT_API_TOKEN must not be empty")
        if self.host not in {"127.0.0.1", "localhost", "::1"} and not self.api_token:
            raise ValueError("AGENT_API_TOKEN is required for non-loopback listeners")
        if self.max_request_bytes < 1024:
            raise ValueError("AGENT_MAX_REQUEST_BYTES must be at least 1024")
        return self

    @classmethod
    def from_env(cls) -> "ServerConfig":
        host = os.getenv("AGENT_SERVER_HOST", cls.host)
        raw_port = os.getenv("AGENT_SERVER_PORT", str(cls.port))
        try:
            port = int(raw_port)
        except (TypeError, ValueError) as exc:
            raise ValueError("AGENT_SERVER_PORT must be an integer") from exc
        token = os.getenv("AGENT_API_TOKEN")

        raw_limit = os.getenv("AGENT_MAX_REQUEST_BYTES", str(cls.max_request_bytes))
        try:
            max_request_bytes = int(raw_limit)
        except (TypeError, ValueError) as exc:
            raise ValueError("AGENT_MAX_REQUEST_BYTES must be an integer") from exc
        return cls(
            host=host,
            port=port,
            api_token=token,
            max_request_bytes=max_request_bytes,
        ).validate()


def authorize_request(headers: Mapping[str, str], config: ServerConfig) -> bool:
    """Validate the optional application token without exposing its value."""
    if config.api_token is None:
        return True
    authorization = headers.get("Authorization", "")
    scheme, separator, presented = authorization.partition(" ")
    return bool(
        separator
        and scheme.lower() == "bearer"
        and hmac.compare_digest(presented.encode("utf-8"), config.api_token.encode("utf-8"))
    )


def build_runtime(session: Any, adapter: Any | None = None) -> Any:
    """Build the local QA runtime; callers may explicitly inject another adapter."""
    from .demo import DemoLLM
    from .dispatcher import MockToolAdapter, ToolDispatcher
    from .enums import Tool
    from .runtime import AgentRuntime

    from .mac_host import MacAgentHostAdapter
    if adapter is not None:
        selected = adapter
    else:
        selected = MacAgentHostAdapter()
    return AgentRuntime(
        session,
        DemoLLM(),
        ToolDispatcher({Tool.CREATE_CALENDAR_EVENT: selected, Tool.QUERY_CALENDAR: selected}),
    )


def handle_json_body(body: bytes, runtime: Any) -> tuple[int, dict[str, Any]]:
    """Translate one HTTP JSON body into a UserRequest and call the runtime."""
    try:
        payload = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return 400, {"error": {"code": "malformed_json", "message": "请求必须是合法 JSON。"}}
    if not isinstance(payload, dict):
        return 400, {"error": {"code": "invalid_request", "message": "请求必须是 JSON object。"}}
    allowed_fields = {
        "user_request", "request_id", "conversation_id",
        "assistant_timezone", "device_timezone",
    }
    if set(payload) - allowed_fields:
        return 400, {
            "error": {
                "code": "unsupported_request_fields",
                "message": "请求包含不支持的字段；Task/step/operation ID 由服务端管理。",
            }
        }
    user_request = payload.get("user_request")
    if user_request is None:
        return 400, {"error": {"code": "missing_user_request", "message": "缺少 user_request。"}}
    if not isinstance(user_request, str):
        return 400, {"error": {"code": "invalid_user_request", "message": "user_request 必须是字符串。"}}
    if not user_request:
        return 400, {"error": {"code": "invalid_user_request", "message": "user_request 不能为空。"}}

    has_request_id = payload.get("request_id") is not None
    has_conversation_id = payload.get("conversation_id") is not None
    if has_request_id and not has_conversation_id:
        return 400, {
            "error": {
                "code": "invalid_request_correlation",
                "message": "提供 request_id 时必须同时提供 conversation_id。",
            }
        }

    conversation_id = payload.get("conversation_id")
    if conversation_id is None:
        conversation_id = f"conv_http_{uuid4().hex}"
    else:
        try:
            conversation_id = TypeAdapter(ProtocolId).validate_python(conversation_id)
        except ValidationError:
            return 400, {
                "error": {
                    "code": "invalid_conversation_id",
                    "message": "conversation_id 必须符合 Protocol ID 格式。",
                }
            }

    supplied_timezone = payload.get("assistant_timezone")
    if supplied_timezone is not None:
        if not isinstance(supplied_timezone, str) or not supplied_timezone.strip():
            return 400, {
                "error": {
                    "code": "invalid_assistant_timezone",
                    "message": "assistant_timezone 必须是有效的 IANA timezone。",
                }
            }
        try:
            ZoneInfo(supplied_timezone)
        except (ZoneInfoNotFoundError, ValueError):
            return 400, {
                "error": {
                    "code": "invalid_assistant_timezone",
                    "message": "assistant_timezone 必须是有效的 IANA timezone。",
                }
            }

    device_timezone = payload.get("device_timezone")
    if device_timezone is not None:
        try:
            device_timezone = TypeAdapter(IanaTimezone).validate_python(device_timezone)
        except ValidationError:
            return 400, {
                "error": {
                    "code": "invalid_device_timezone",
                    "message": "device_timezone 必须是有效的 IANA timezone。",
                }
            }

    request_id = payload.get("request_id")
    if request_id is None:
        # Transitional compatibility for the existing Shortcut's shorthand
        # {"user_request": "..."} body. Canonical V2 callers provide request_id.
        request_id = f"req_http_{uuid4().hex}"
    else:
        try:
            request_id = TypeAdapter(ProtocolId).validate_python(request_id)
        except ValidationError:
            return 400, {
                "error": {
                    "code": "invalid_request_id",
                    "message": "request_id 必须符合 Protocol ID 格式。",
                }
            }

    try:
        session = getattr(runtime, "session", None)
        if has_conversation_id and session is not None:
            conversation = ConversationRepository(session).get(conversation_id)
            if conversation is None:
                return 404, {
                    "error": {"code": "unknown_conversation", "message": "conversation_id 不存在。"}
                }
            prior_receipt = InboundReceiptRepository(session).get(request_id)
            if prior_receipt is not None:
                if (prior_receipt.conversation_id != conversation_id
                        or prior_receipt.message_type != "clarification_response"):
                    return 409, {
                        "error": {"code": "request_id_conflict", "message": "request_id 已用于其他请求。"}
                    }
                answered = next(
                    (row for row in ClarificationRepository(session).list_for_task(prior_receipt.task_id)
                     if isinstance(row.user_response, dict)
                     and row.user_response.get("request_id") == request_id),
                    None,
                )
                if answered is None:
                    return 409, {
                        "error": {"code": "stale_clarification", "message": "原澄清回答无法恢复。"}
                    }
                request = ClarificationResponse(
                    type="clarification_response", request_id=request_id,
                    conversation_id=conversation_id, task_id=prior_receipt.task_id,
                    reply_to_step_id=answered.step_id, message=user_request,
                )
            else:
                waiting = TaskRepository(session).waiting_clarification_for_conversation(conversation_id)
                if not waiting:
                    return 409, {
                        "error": {"code": "no_pending_clarification", "message": "该对话没有待续接的澄清任务。"}
                    }
                if len(waiting) != 1:
                    return 409, {
                        "error": {"code": "ambiguous_pending_clarification", "message": "该对话存在多个待续接任务，未执行任何操作。"}
                    }
                task = waiting[0]
                pending_rows = ClarificationRepository(session).pending_for_task(task.task_id)
                if len(pending_rows) != 1 or task.current_step_id != pending_rows[0].step_id:
                    return 409, {
                        "error": {"code": "stale_clarification", "message": "待澄清状态不一致，未执行任何操作。"}
                    }
                pending = pending_rows[0]
                request = ClarificationResponse(
                    type="clarification_response", request_id=request_id,
                    conversation_id=conversation_id, task_id=task.task_id,
                    reply_to_step_id=pending.step_id, message=user_request,
                )
            if hasattr(runtime, "handle_clarification_response"):
                response = runtime.handle_clarification_response(
                    request, assistant_timezone=supplied_timezone
                )
            else:
                response = runtime.handle(request)
        else:
            assistant_timezone = supplied_timezone or DEFAULT_ASSISTANT_TIMEZONE
            request = UserRequest(
                type="user_request", request_id=request_id,
                conversation_id=conversation_id, message=user_request,
                current_time=datetime.now(ZoneInfo(assistant_timezone)),
                assistant_timezone=assistant_timezone, source="local-http",
                device_timezone=device_timezone,
            )
            response = runtime.handle(request)
    except Exception as exc:
        from .runtime import ClarificationResumeError

        if isinstance(exc, ClarificationResumeError):
            return exc.status_code, {"error": {"code": exc.code, "message": exc.message}}
        return 500, {"error": {"code": "runtime_error", "message": "Runtime 执行失败。"}}
    if getattr(response, "type", None) == "tool_request":
        return 500, {
            "error": {
                "code": "internal_execution_boundary",
                "message": "Runtime 返回了内部 ToolRequest，未生成公开 AgentResponse。",
            }
        }
    try:
        public_response = TypeAdapter(AgentResponse).validate_python(
            response.model_dump(mode="json")
        )
    except (AttributeError, ValidationError):
        return 500, {"error": {"code": "invalid_agent_response", "message": "Runtime 未返回合法 AgentResponse。"}}
    if (public_response.request_id != request.request_id
            or public_response.conversation_id != request.conversation_id):
        return 500, {
            "error": {
                "code": "response_correlation_mismatch",
                "message": "AgentResponse 与当前 HTTP 请求 correlation 不一致。",
            }
        }
    return 200, public_response.model_dump(mode="json")


class AgentRequestHandler(BaseHTTPRequestHandler):
    runtime: Any = None
    server_config = ServerConfig()

    def do_GET(self) -> None:  # noqa: N802
        self._send(405, {"error": {"code": "method_not_allowed", "message": "仅支持 POST /agent。"}})

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/agent":
            self._send(404, {"error": {"code": "not_found", "message": "路径不存在。"}})
            return
        if not authorize_request(self.headers, self.server_config):
            self._send(401, {"error": {"code": "unauthorized", "message": "需要有效的访问凭证。"}})
            return
        length = self.headers.get("Content-Length")
        if length is None:
            self._send(400, {"error": {"code": "missing_body", "message": "请求体不能为空。"}})
            return
        try:
            content_length = int(length)
            if content_length > self.server_config.max_request_bytes:
                self._send(413, {"error": {"code": "request_too_large", "message": "请求体过大。"}})
                return
            body = self.rfile.read(content_length)
        except (ValueError, OSError):
            self._send(400, {"error": {"code": "invalid_body", "message": "无法读取请求体。"}})
            return
        runtime = self.runtime() if callable(self.runtime) else self.runtime
        try:
            status, response = handle_json_body(body, runtime)
            self._send(status, response)
        finally:
            session = getattr(runtime, "session", None)
            if session is not None:
                session.close()

    def _send(self, status: int, payload: dict[str, Any]) -> None:
        encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        if status == 401:
            self.send_header("WWW-Authenticate", "Bearer")
        if status == 405:
            self.send_header("Allow", "POST")
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, _format: str, *_args: Any) -> None:
        return


def serve(
    runtime: Any,
    host: str | None = None,
    port: int | None = None,
    *,
    config: ServerConfig | None = None,
) -> None:
    if config is not None:
        selected_config = config.validate()
    elif host is None and port is None:
        selected_config = ServerConfig.from_env()
    else:
        selected_config = ServerConfig(
            host=host if host is not None else ServerConfig.host,
            port=port if port is not None else ServerConfig.port,
            api_token=os.getenv("AGENT_API_TOKEN"),
        ).validate()
    handler = type(
        "BoundAgentRequestHandler",
        (AgentRequestHandler,),
        {"runtime": staticmethod(runtime) if callable(runtime) else runtime},
    )
    handler.server_config = selected_config
    server = ThreadingHTTPServer((selected_config.host, selected_config.port), handler)
    print(f"Agent HTTP API listening on http://{selected_config.host}:{selected_config.port}/agent")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def main() -> None:
    from sqlalchemy.orm import sessionmaker

    from .persistence import Base, make_engine

    engine = make_engine("sqlite:///calendar-agent.db")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    config = ServerConfig.from_env()
    serve(lambda: build_runtime(session_factory()), config=config)


if __name__ == "__main__":
    main()
