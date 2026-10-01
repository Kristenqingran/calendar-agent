from jsonschema import Draft202012Validator
from referencing import Registry, Resource


def test_v1_schemas_remain_present_and_all_schemas_are_valid_draft_2020_12(
    schemas: dict[str, dict[str, object]],
) -> None:
    assert len([name for name in schemas if name.endswith("-v1.schema.json")]) == 8
    assert len([name for name in schemas if name.endswith("-v2.schema.json")]) == 9
    for schema in schemas.values():
        assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
        Draft202012Validator.check_schema(schema)


def test_all_local_refs_resolve(schemas: dict[str, dict[str, object]]) -> None:
    registry = Registry().with_resources(
        [(str(schema["$id"]), Resource.from_contents(schema)) for schema in schemas.values()]
    )
    for schema in schemas.values():
        resolver = registry.resolver(str(schema["$id"]))
        pending: list[object] = [schema]
        while pending:
            node = pending.pop()
            if isinstance(node, dict):
                reference = node.get("$ref")
                if isinstance(reference, str):
                    resolver.lookup(reference)
                pending.extend(node.values())
            elif isinstance(node, list):
                pending.extend(node)
