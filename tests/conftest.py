from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import pytest
from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

ROOT = Path(__file__).parents[1]
SCHEMA_DIR = ROOT / "schemas"


@pytest.fixture(scope="session")
def schemas() -> dict[str, dict[str, object]]:
    return {path.name: json.loads(path.read_text()) for path in SCHEMA_DIR.glob("*.json")}


@pytest.fixture(scope="session")
def format_checker() -> FormatChecker:
    checker = FormatChecker()

    @checker.checks("iana-timezone", raises=(ZoneInfoNotFoundError, ValueError))
    def is_iana_timezone(value: object) -> bool:
        if not isinstance(value, str):
            return True
        ZoneInfo(value)
        return True

    return checker


@pytest.fixture(scope="session")
def schema_validator(
    schemas: dict[str, dict[str, object]], format_checker: FormatChecker
) -> Callable[[str], Draft202012Validator]:
    resources = [
        (str(schema["$id"]), Resource.from_contents(schema)) for schema in schemas.values()
    ]
    registry = Registry().with_resources(resources)

    def build(name: str) -> Draft202012Validator:
        return Draft202012Validator(schemas[name], registry=registry, format_checker=format_checker)

    return build
