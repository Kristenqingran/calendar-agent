from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from pydantic import TypeAdapter, ValidationError

from calendar_agent_protocol.messages import AgentResponse, InboundMessage, ToolResult
from calendar_agent_protocol.tools import ToolRequest

FIXTURES = Path(__file__).parent / "fixtures"
VALID_FIXTURES = sorted((FIXTURES / "valid").glob("*.json"))
INVALID_FIXTURES = sorted((FIXTURES / "invalid").glob("*.json"))


def load(path: Path) -> dict[str, object]:
    return json.loads(path.read_text())


def contracts(path: Path) -> tuple[str, TypeAdapter[object]]:
    payload = load(path)
    if payload.get("type") == "tool_result":
        return "tool-result-v2.schema.json", TypeAdapter(ToolResult)
    if payload.get("type") == "tool_request":
        return "tool-request-v2.schema.json", TypeAdapter(ToolRequest)
    if path.name.startswith("inbound-"):
        return "inbound-v2.schema.json", TypeAdapter(InboundMessage)
    return "agent-response-v2.schema.json", TypeAdapter(AgentResponse)


@pytest.mark.parametrize("path", VALID_FIXTURES, ids=lambda path: path.stem)
def test_valid_fixture_is_accepted_by_schema_and_pydantic(
    path: Path, schema_validator: Callable[[str], Draft202012Validator]
) -> None:
    schema_name, adapter = contracts(path)
    payload = load(path)
    schema_validator(schema_name).validate(payload)
    adapter.validate_python(payload)


@pytest.mark.parametrize("path", INVALID_FIXTURES, ids=lambda path: path.stem)
def test_invalid_fixture_is_rejected_by_schema_and_pydantic(
    path: Path, schema_validator: Callable[[str], Draft202012Validator]
) -> None:
    schema_name, adapter = contracts(path)
    payload = load(path)
    assert list(schema_validator(schema_name).iter_errors(payload))
    with pytest.raises(ValidationError):
        adapter.validate_python(payload)
