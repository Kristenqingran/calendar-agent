"""Mac-first V2 runtime and adapter boundaries."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol, runtime_checkable

from .messages import AgentResponse, InboundMessage, RuntimeDecision, RuntimeMessage
from .tools import ToolRequest


@runtime_checkable
class AgentCore(Protocol):
    """Public user-turn boundary; internal Tool commands are never HTTP responses."""

    def handle(self, message: InboundMessage) -> AgentResponse:
        """Handle a public inbound user message and return Clarification or Final."""


@runtime_checkable
class RuntimeExecutionPort(Protocol):
    """Internal orchestration boundary, including Tool execution callbacks."""

    def handle(self, message: RuntimeMessage) -> RuntimeDecision | ToolResult:
        """Handle one user turn or internal ToolResult."""


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
    """Boundary from an internal ToolRequest to one execution capability."""

    def execute(self, request: ToolRequest) -> ToolResult:
        """Execute one request externally and return its validated result."""


__all__ = ["AgentCore", "LLMAdapter", "ToolAdapter"]
