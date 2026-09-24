from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from calendar_agent_protocol.messages import AgentResponse, InboundMessage, ToolResult, UserRequest
from calendar_agent_protocol.runtime_contract import (
    AgentCore,
    LLMAdapter,
    ToolAdapter,
)
from calendar_agent_protocol.tools import ToolRequest


class FakeAgentCore:
    def handle(self, message: InboundMessage) -> AgentResponse:
        raise NotImplementedError


class FakeLLMAdapter:
    def analyze(
        self, request: UserRequest, context: Mapping[str, Any] | None = None
    ) -> Mapping[str, Any]:
        raise NotImplementedError


class FakeToolAdapter:
    def execute(self, request: ToolRequest) -> ToolResult:
        raise NotImplementedError


def test_agent_core_contract_uses_existing_message_unions() -> None:
    assert isinstance(FakeAgentCore(), AgentCore)


def test_llm_adapter_contract_accepts_user_request_and_context() -> None:
    assert isinstance(FakeLLMAdapter(), LLMAdapter)


def test_tool_adapter_contract_uses_existing_tool_request_and_result_models() -> None:
    assert isinstance(FakeToolAdapter(), ToolAdapter)
