from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

import pytest
import respx
from jsonschema import Draft202012Validator


# Contract tests for a Quality Management API client.
#
# Expected implementation surface (duck-typed):
#   - `zoompy.QualityManagementClient` with methods:
#       * list_automated_evaluations(...)
#       * get_evaluation_detail(evaluation_id: str)
#   - OR `zoompy.ZoomClient` exposing `.quality_management` with those methods.
#
# These tests validate:
#   1) The OpenAPI document has expected structure.
#   2) Representative operations exist.
#   3) A client calls the correct routes.
#   4) The returned JSON validates against the operation's 200-response schema.


SCHEMA_PATH = Path(__file__).resolve().parent / "schemas" / "build_platform" / "Quality Management.json"


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise AssertionError(f"Missing schema file: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _resolve_ref(doc: Mapping[str, Any], ref: str) -> Mapping[str, Any]:
    # Only supports local refs like '#/components/schemas/Foo'
    if not ref.startswith("#/"):
        raise AssertionError(f"Unsupported $ref (only local refs supported in tests): {ref}")
    node: Any = doc
    for part in ref[2:].split("/"):
        if not isinstance(node, Mapping) or part not in node:
            raise AssertionError(f"Broken $ref path: {ref}")
        node = node[part]
    if not isinstance(node, Mapping):
        raise AssertionError(f"$ref did not resolve to an object: {ref}")
    return node


def _json_schema_for_response(doc: Mapping[str, Any], op: Mapping[str, Any], status: str) -> Mapping[str, Any]:
    responses = op.get("responses")
    assert isinstance(responses, Mapping), "operation.responses must be an object"
    assert status in responses, f"operation must define a {status} response"
    r = responses[status]
    assert isinstance(r, Mapping), f"responses[{status}] must be an object"
    content = r.get("content")
    assert isinstance(content, Mapping), f"responses[{status}].content must be an object"
    app_json = content.get("application/json")
    assert isinstance(app_json, Mapping), f"responses[{status}].content must define application/json"
    schema = app_json.get("schema")
    assert isinstance(schema, Mapping), f"responses[{status}].content.application/json.schema must be an object"
    if "$ref" in schema:
        return _resolve_ref(doc, schema["$ref"])
    return schema


def _example_value_for_schema(doc: Mapping[str, Any], schema: Mapping[str, Any]) -> Any:
    """Generate a minimal example payload that validates against the schema."""

    if "$ref" in schema:
        return _example_value_for_schema(doc, _resolve_ref(doc, schema["$ref"]))

    if "allOf" in schema and isinstance(schema["allOf"], list) and schema["allOf"]:
        merged: Any = {}
        for part in schema["allOf"]:
            if isinstance(part, Mapping):
                val = _example_value_for_schema(doc, part)
                if isinstance(val, Mapping) and isinstance(merged, Mapping):
                    merged = {**merged, **val}
                else:
                    merged = val
        return merged

    for combiner in ("oneOf", "anyOf"):
        if combiner in schema and isinstance(schema[combiner], list) and schema[combiner]:
            first = schema[combiner][0]
            if isinstance(first, Mapping):
                return _example_value_for_schema(doc, first)

    if "example" in schema:
        return schema["example"]

    if "enum" in schema and isinstance(schema["enum"], list) and schema["enum"]:
        return schema["enum"][0]

    t = schema.get("type")

    if t == "object" or (t is None and "properties" in schema):
        props = schema.get("properties")
        required = schema.get("required", [])
        if not isinstance(props, Mapping):
            return {}
        out: dict[str, Any] = {}
        keys: list[str] = []
        if isinstance(required, list):
            keys.extend([k for k in required if isinstance(k, str) and k in props])
        for k in props.keys():
            if k not in keys:
                keys.append(k)
            if len(keys) >= max(2, len(required) if isinstance(required, list) else 0) + 2:
                break
        for k in keys:
            ps = props.get(k)
            if isinstance(ps, Mapping):
                out[k] = _example_value_for_schema(doc, ps)
        return out

    if t == "array":
        items = schema.get("items")
        if isinstance(items, Mapping):
            return [_example_value_for_schema(doc, items)]
        return []

    if t == "string":
        fmt = schema.get("format")
        if fmt == "date-time":
            return "2025-01-01T00:00:00Z"
        if fmt == "email":
            return "user@example.com"
        if fmt == "uuid":
            return "00000000-0000-0000-0000-000000000000"
        return "example"

    if t == "integer":
        return 1

    if t == "number":
        return 1.0

    if t == "boolean":
        return True

    return {}


def _find_operation_by_id(doc: Mapping[str, Any], operation_id: str) -> tuple[str, str, Mapping[str, Any]]:
    paths = doc.get("paths")
    assert isinstance(paths, Mapping), "schema.paths must be an object"

    for path, path_item in paths.items():
        if not isinstance(path, str) or not isinstance(path_item, Mapping):
            continue
        for method, op in path_item.items():
            if method.lower() not in {"get", "post", "put", "patch", "delete"}:
                continue
            if not isinstance(op, Mapping):
                continue
            if op.get("operationId") == operation_id:
                return method.lower(), path, op

    raise AssertionError(f"operationId not found in schema: {operation_id}")


def _route_for(router: respx.Router, method: str, path: str) -> respx.Route:
    if "{" in path and "}" in path:
        pattern = "^" + re.sub(r"\{[^}]+\}", r"[^/]+", path) + "$"
        return router.request(method, url__regex=pattern)
    return router.request(method, path)


@dataclass(frozen=True)
class ContractCase:
    operation_id: str
    ok_status: str
    call: str


QUALITY_MANAGEMENT_CASES: tuple[ContractCase, ...] = (
    ContractCase("ListAutomatedEvaluations", "200", "list_automated_evaluations"),
    ContractCase("EvaluationDetail", "200", "get_evaluation_detail"),
)


@pytest.fixture(scope="session")
def qm_openapi() -> dict[str, Any]:
    return _load_json(SCHEMA_PATH)


def test_quality_management_schema_has_expected_openapi_header(qm_openapi: Mapping[str, Any]) -> None:
    assert qm_openapi.get("openapi") == "3.0.0"
    info = qm_openapi.get("info")
    assert isinstance(info, Mapping)
    assert info.get("title") == "Quality Management"
    servers = qm_openapi.get("servers")
    assert isinstance(servers, list) and servers
    assert any(isinstance(s, Mapping) and s.get("url") == "https://api.zoom.us/v2" for s in servers)


def test_quality_management_paths_are_scoped(qm_openapi: Mapping[str, Any]) -> None:
    paths = qm_openapi.get("paths")
    assert isinstance(paths, Mapping)
    assert paths
    bad = [p for p in paths.keys() if isinstance(p, str) and not p.startswith("/qm/")]
    assert not bad, f"unexpected non-/qm/ paths present: {bad[:5]}"


def test_quality_management_embedded_json_schemas_are_valid(qm_openapi: Mapping[str, Any]) -> None:
    paths = qm_openapi.get("paths")
    assert isinstance(paths, Mapping)

    checked = 0
    for _path, path_item in paths.items():
        if not isinstance(path_item, Mapping):
            continue
        for method, op in path_item.items():
            if method.lower() not in {"get", "post", "put", "patch", "delete"}:
                continue
            if not isinstance(op, Mapping):
                continue
            responses = op.get("responses")
            if not isinstance(responses, Mapping):
                continue
            for _status, resp in responses.items():
                if not isinstance(resp, Mapping):
                    continue
                content = resp.get("content")
                if not isinstance(content, Mapping):
                    continue
                app_json = content.get("application/json")
                if not isinstance(app_json, Mapping):
                    continue
                schema = app_json.get("schema")
                if not isinstance(schema, Mapping):
                    continue
                Draft202012Validator.check_schema(schema)
                checked += 1

    assert checked > 0


@pytest.mark.parametrize("case", QUALITY_MANAGEMENT_CASES)
def test_quality_management_operation_ids_exist(qm_openapi: Mapping[str, Any], case: ContractCase) -> None:
    _find_operation_by_id(qm_openapi, case.operation_id)


def _import_quality_management_client() -> Any:
    try:
        from zoompy import ZoomClient  # type: ignore

        z = ZoomClient(token="TEST", base_url="https://api.zoom.us/v2")
        if hasattr(z, "quality_management"):
            return z.quality_management
    except Exception:
        pass

    from zoompy import QualityManagementClient  # type: ignore

    return QualityManagementClient(token="TEST", base_url="https://api.zoom.us/v2")


@pytest.mark.parametrize("case", QUALITY_MANAGEMENT_CASES)
def test_quality_management_client_calls_correct_route_and_validates_response(
    qm_openapi: Mapping[str, Any],
    case: ContractCase,
) -> None:
    method, path, op = _find_operation_by_id(qm_openapi, case.operation_id)
    schema = _json_schema_for_response(qm_openapi, op, case.ok_status)
    example_payload = _example_value_for_schema(qm_openapi, schema)

    base_url = "https://api.zoom.us/v2"
    with respx.mock(base_url=base_url) as router:
        route = _route_for(router, method, path)
        route.respond(200, json=example_payload)

        client = _import_quality_management_client()

        if case.call == "list_automated_evaluations":
            result = getattr(client, case.call)(status="COMPLETED", page_size=30)
        elif case.call == "get_evaluation_detail":
            result = getattr(client, case.call)(evaluation_id="aI9HM3ZsEScAa")
        else:
            raise AssertionError(f"Unknown call mapping: {case.call}")

        assert route.called, f"client did not call {method.upper()} {path}"

    Draft202012Validator(schema).validate(result)


def test_quality_management_client_raises_for_non_2xx(qm_openapi: Mapping[str, Any]) -> None:
    method, path, _op = _find_operation_by_id(qm_openapi, "EvaluationDetail")

    base_url = "https://api.zoom.us/v2"
    with respx.mock(base_url=base_url) as router:
        _route_for(router, method, path).respond(404, json={"message": "not found"})

        client = _import_quality_management_client()

        with pytest.raises(Exception):
            client.get_evaluation_detail(evaluation_id="does-not-exist")
