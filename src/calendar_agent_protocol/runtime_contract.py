"""Phase 1 runtime boundaries for the future Agent implementation.

This module defines interfaces only. It does not implement an Agent, an HTTP
server, an LLM client, a Tool executor, orchestration, or final response
generation.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol, runtime_checkable

from .messages import AgentResponse, InboundMessage, ToolResult, UserRequest
from .tools import ToolRequest


@runtime_checkable
class AgentCore(Protocol):
    """Boundary from validated inbound messages to one Agent response."""

    def handle(self, message: InboundMessage) -> AgentResponse:
        """Handle one validated inbound message and return one response."""


@runtime_checkable
class LLMAdapter(Protocol):
    """Boundary for semantic analysis of a user request.

    The returned mapping is intentionally not promoted to a new Python model:
    the formal status of ``llm-analysis-v1.schema.json`` as a runtime contract
    is not settled by the current repository.
    """

    def analyze(
        self, request: UserRequest, context: Mapping[str, Any] | None = None
    ) -> Mapping[str, Any]:
        """Return a schema-candidate semantic analysis for one user request."""


@runtime_checkable
class ToolAdapter(Protocol):
    """Boundary to the external Shortcut/Tool Executor."""

    def execute(self, request: ToolRequest) -> ToolResult:
        """Execute one request externally and return its validated result."""


__all__ = ["AgentCore", "LLMAdapter", "ToolAdapter"]
