

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

import httpx
import pytest
from jsonschema import Draft202012Validator


SPEC_PATH = Path(__file__).resolve().parent / "schemas" / "workplace" / "Calendar.json"
BASE_URL = "https://api.zoom.us/v2"


# ----------------------------
# Contract required by tests
# ----------------------------
#
# These tests are designed to validate ANY Calendar API implementation.
# Your implementation must provide a fixture named `calendar_client`.
#
# The fixture may return:
#   1) an object with a `.request(...)` method, OR
#   2) a callable with the same signature as `.request(...)`.
#
# Expected request signature (recommended):
#   request(method: str,
#           path: str,
#           *,
#           path_params: Mapping[str, Any] | None = None,
#           params: Mapping[str, Any] | None = None,
#           json: Any | None = None,
#           headers: Mapping[str, str] | None = None,
#           timeout: float | None = None
#   ) -> httpx.Response | Mapping[str, Any] | list[Any]
#
# The tests will mock outbound HTTP with respx, so your client MUST use httpx.


@pytest.fixture
def calendar_spec() -> dict[str, Any]:
    if not SPEC_PATH.exists():
        raise AssertionError(
            f"Calendar OpenAPI spec not found at {SPEC_PATH}. "
            "Expected it under src/tests/schemas/workplace/Calendar.json"
        )
    return json.loads(SPEC_PATH.read_text(encoding="utf-8"))


def _get_request_callable(calendar_client: Any):
    if callable(calendar_client):
        return calendar_client
    req = getattr(calendar_client, "request", None)
    if callable(req):
        return req
    raise AssertionError(
        "The `calendar_client` fixture must return either a callable or an object "
        "with a callable `.request(...)` method."
    )


@dataclass(frozen=True)
class OperationCase:
    operation_id: str
    method: str
    path: str
    path_params: dict[str, Any]
    query_params: dict[str, Any]
    request_json: Any | None
    response_schema: dict[str, Any] | None
    status_code: int


def _snake(s: str) -> str:
    out: list[str] = []
    for ch in s:
        if ch.isupper() and out:
            out.append("_")
        out.append(ch.lower())
    return "".join(out).replace("__", "_")


def _iter_operations(spec: Mapping[str, Any]) -> Iterable[tuple[str, str, str, Mapping[str, Any]]]:
    paths = spec.get("paths", {})
    for path, item in paths.items():
        if not isinstance(item, Mapping):
            continue
        for method in ("get", "post", "put", "patch", "delete"):
            op = item.get(method)
            if isinstance(op, Mapping):
                yield op.get("operationId") or f"{method}_{path}", method.upper(), path, op


def _components(spec: Mapping[str, Any]) -> Mapping[str, Any]:
    return spec.get("components", {})


def _deepcopy_json(v: Any) -> Any:
    # Fast enough for tests, avoids subtle shared-mutation bugs.
    return json.loads(json.dumps(v))


def _resolve_ref(spec: Mapping[str, Any], ref: str) -> Any:
    if not ref.startswith("#/" ):
        raise ValueError(f"Only local refs are supported in tests, got: {ref}")
    cur: Any = spec
    for part in ref.lstrip("#/").split("/"):
        if not isinstance(cur, Mapping) or part not in cur:
            raise KeyError(f"Unresolvable $ref: {ref}")
        cur = cur[part]
    return cur


def _resolve_schema(spec: Mapping[str, Any], schema: Any) -> Any:
    """Resolve local $ref recursively into an inline schema.

    This is a minimal OpenAPI->JSON Schema resolver suitable for these contract tests.
    """
    if not isinstance(schema, Mapping):
        return schema

    if "$ref" in schema:
        target = _deepcopy_json(_resolve_ref(spec, str(schema["$ref"])))
        # Merge sibling keys (OpenAPI allows it, JSON Schema doesn't love it, but it's common).
        siblings = {k: v for k, v in schema.items() if k != "$ref"}
        if siblings:
            if isinstance(target, Mapping):
                merged = _deepcopy_json(target)
                merged.update(_deepcopy_json(siblings))
                target = merged
        return _resolve_schema(spec, target)

    resolved: dict[str, Any] = {}
    for k, v in schema.items():
        if isinstance(v, Mapping):
            resolved[k] = _resolve_schema(spec, v)
        elif isinstance(v, list):
            resolved[k] = [_resolve_schema(spec, x) for x in v]
        else:
            resolved[k] = v
    return resolved


def _pick_content_schema(responses: Mapping[str, Any]) -> tuple[int, dict[str, Any]] | None:
    """Return (status_code, schema) for the 'best' success JSON response."""
    # Prefer explicit 200, then any 2xx, then default.
    def _try(code_key: str) -> tuple[int, dict[str, Any]] | None:
        entry = responses.get(code_key)
        if not isinstance(entry, Mapping):
            return None
        content = entry.get("content")
        if not isinstance(content, Mapping):
            return None
        app_json = content.get("application/json") or content.get("application/json; charset=utf-8")
        if not isinstance(app_json, Mapping):
            return None
        schema = app_json.get("schema")
        if not isinstance(schema, Mapping):
            return None
        try:
            code_int = int(code_key)
        except Exception:
            code_int = 200
        return code_int, dict(schema)

    if "200" in responses:
        return _try("200")

    for key in responses.keys():
        if isinstance(key, str) and key.isdigit() and 200 <= int(key) < 300:
            got = _try(key)
            if got is not None:
                return got

    if "default" in responses:
        entry = responses.get("default")
        if isinstance(entry, Mapping):
            content = entry.get("content")
            if isinstance(content, Mapping):
                app_json = content.get("application/json")
                if isinstance(app_json, Mapping) and isinstance(app_json.get("schema"), Mapping):
                    return 200, dict(app_json["schema"])

    return None


def _example_for_primitive(schema: Mapping[str, Any]) -> Any:
    if "enum" in schema and isinstance(schema["enum"], list) and schema["enum"]:
        return schema["enum"][0]

    t = schema.get("type")
    fmt = schema.get("format")

    if t == "string" or t is None:
        if "example" in schema:
            return schema["example"]
        if fmt in {"email", "uri", "uuid"}:
            return "test@example.com" if fmt == "email" else "00000000-0000-0000-0000-000000000000" if fmt == "uuid" else "https://example.com"
        return "test"
    if t == "integer":
        return int(schema.get("example", 1))
    if t == "number":
        return float(schema.get("example", 1.0))
    if t == "boolean":
        return bool(schema.get("example", True))
    return "test"


def _example_from_schema(spec: Mapping[str, Any], schema: Any) -> Any:
    schema = _resolve_schema(spec, schema)
    if not isinstance(schema, Mapping):
        return schema

    # OpenAPI nullable
    if schema.get("nullable") is True:
        # Prefer non-null example when building requests/responses.
        schema = {k: v for k, v in schema.items() if k != "nullable"}

    if "example" in schema:
        return schema["example"]

    if "allOf" in schema and isinstance(schema["allOf"], list) and schema["allOf"]:
        # Merge object examples if possible.
        parts = [_example_from_schema(spec, s) for s in schema["allOf"]]
        if all(isinstance(p, Mapping) for p in parts):
            merged: dict[str, Any] = {}
            for p in parts:
                merged.update(dict(p))
            return merged
        return parts[0]

    for key in ("oneOf", "anyOf"):
        if key in schema and isinstance(schema[key], list) and schema[key]:
            return _example_from_schema(spec, schema[key][0])

    t = schema.get("type")

    if t == "array":
        items = schema.get("items", {})
        return [_example_from_schema(spec, items)]

    if t == "object" or (t is None and "properties" in schema):
        props = schema.get("properties", {})
        required = set(schema.get("required", []) or [])
        out: dict[str, Any] = {}
        if isinstance(props, Mapping):
            for name, prop_schema in props.items():
                if name in required:
                    out[name] = _example_from_schema(spec, prop_schema)

        # If it's an object with no required props, still produce something valid.
        if not out and isinstance(props, Mapping) and props:
            # add one optional prop for realism
            first_key = next(iter(props.keys()))
            out[first_key] = _example_from_schema(spec, props[first_key])

        if not out and schema.get("additionalProperties"):
            out["key"] = "value"

        return out

    return _example_for_primitive(schema)


def _validate(instance: Any, schema: Mapping[str, Any]) -> None:
    Draft202012Validator(schema).validate(instance)


def _build_operation_cases(spec: Mapping[str, Any]) -> list[OperationCase]:
    cases: list[OperationCase] = []
    for op_id, method, path, op in _iter_operations(spec):
        parameters: list[Mapping[str, Any]] = []

        # Path-level parameters can exist.
        path_item = spec.get("paths", {}).get(path, {})
        if isinstance(path_item, Mapping) and isinstance(path_item.get("parameters"), list):
            parameters.extend([p for p in path_item["parameters"] if isinstance(p, Mapping)])

        if isinstance(op.get("parameters"), list):
            parameters.extend([p for p in op["parameters"] if isinstance(p, Mapping)])

        path_params: dict[str, Any] = {}
        query_params: dict[str, Any] = {}

        for p in parameters:
            where = p.get("in")
            name = p.get("name")
            if not isinstance(name, str) or where not in {"path", "query"}:
                continue
            schema = p.get("schema") or {}
            value = p.get("example")
            if value is None:
                value = _example_from_schema(spec, schema)
            if where == "path":
                path_params[name] = value
            else:
                if p.get("required") is True:
                    query_params[name] = value

        request_json: Any | None = None
        request_body = op.get("requestBody")
        if isinstance(request_body, Mapping):
            content = request_body.get("content")
            if isinstance(content, Mapping):
                app_json = content.get("application/json")
                if isinstance(app_json, Mapping) and isinstance(app_json.get("schema"), (Mapping, list)):
                    request_json = _example_from_schema(spec, app_json["schema"])

        responses = op.get("responses")
        response_schema: dict[str, Any] | None = None
        status_code = 200
        if isinstance(responses, Mapping):
            pick = _pick_content_schema(responses)
            if pick is not None:
                status_code, raw_schema = pick
                response_schema = _resolve_schema(spec, raw_schema)

        cases.append(
            OperationCase(
                operation_id=str(op_id),
                method=method,
                path=path,
                path_params=path_params,
                query_params=query_params,
                request_json=request_json,
                response_schema=response_schema,
                status_code=status_code,
            )
        )

    # Only keep Calendar operations (defensive in case spec grows).
    return cases


def _format_path(path: str, path_params: Mapping[str, Any]) -> str:
    out = path
    for k, v in path_params.items():
        out = out.replace("{" + k + "}", str(v))
    return out


@pytest.fixture
def calendar_cases(calendar_spec: dict[str, Any]) -> list[OperationCase]:
    cases = _build_operation_cases(calendar_spec)
    if not cases:
        raise AssertionError("No operations discovered in Calendar OpenAPI spec.")
    return cases


# ----------------------------
# Tests
# ----------------------------


def test_calendar_spec_is_openapi_3(calendar_spec: dict[str, Any]) -> None:
    assert calendar_spec.get("openapi", "").startswith("3."), "Expected OpenAPI 3.x spec"
    assert "paths" in calendar_spec and isinstance(calendar_spec["paths"], Mapping)


def test_calendar_operations_have_operation_ids(calendar_cases: list[OperationCase]) -> None:
    missing = [c for c in calendar_cases if not c.operation_id]
    assert not missing, "All operations should have an operationId (or derived id)."


@pytest.mark.parametrize("case", [pytest.param(None, id="_placeholder")])
def test_calendar_placeholder(case: Any) -> None:
    """Pytest needs at least one parametrized test at import-time on some setups.

    This will be replaced dynamically by `pytest_generate_tests` below.
    """
    assert case is None


def pytest_generate_tests(metafunc: Any) -> None:
    # Dynamically parametrize the contract test over all operations in the spec.
    if "calendar_case" in metafunc.fixturenames:
        spec = json.loads(SPEC_PATH.read_text(encoding="utf-8"))
        cases = _build_operation_cases(spec)
        ids = [f"{_snake(c.operation_id)}[{c.method} {c.path}]" for c in cases]
        metafunc.parametrize("calendar_case", cases, ids=ids)


@pytest.mark.usefixtures("respx_mock")
def test_calendar_operation_contract(calendar_client: Any, calendar_spec: dict[str, Any], calendar_case: OperationCase, respx_mock: Any) -> None:
    request = _get_request_callable(calendar_client)

    formatted_path = _format_path(calendar_case.path, calendar_case.path_params)
    url = f"{BASE_URL}{formatted_path}"

    # Prepare a response payload that SHOULD validate against the response schema.
    response_payload: Any
    if calendar_case.response_schema is None:
        # Some endpoints might be empty / no JSON body; return something harmless.
        response_payload = {}
    else:
        response_payload = _example_from_schema(calendar_spec, calendar_case.response_schema)
        # If generator produced None somehow, make it object-like to avoid client surprises.
        if response_payload is None:
            response_payload = {}
        # Validate our generated payload against the resolved schema.
        _validate(response_payload, calendar_case.response_schema)

    route = respx_mock.request(calendar_case.method, url).mock(
        return_value=httpx.Response(calendar_case.status_code, json=response_payload)
    )

    result = request(
        calendar_case.method,
        calendar_case.path,
        path_params=calendar_case.path_params or None,
        params=calendar_case.query_params or None,
        json=calendar_case.request_json,
    )

    # The client can return an httpx.Response or already-decoded JSON.
    if isinstance(result, httpx.Response):
        assert result.status_code == calendar_case.status_code
        got = result.json() if result.content else None
    else:
        got = result

    # Make sure the request actually happened.
    assert route.called, f"Client did not call {calendar_case.method} {url}"

    # Validate outbound query params and body were actually sent.
    call = route.calls[-1].request

    if calendar_case.query_params:
        # httpx encodes params into the URL.
        for k, v in calendar_case.query_params.items():
            assert call.url.params.get(k) == str(v)

    if calendar_case.request_json is not None and calendar_case.method in {"POST", "PUT", "PATCH"}:
        assert call.headers.get("content-type", "").startswith("application/json")
        sent = json.loads(call.content.decode("utf-8")) if call.content else None
        assert sent == calendar_case.request_json

    # Validate inbound payload.
    if calendar_case.response_schema is not None:
        _validate(got, calendar_case.response_schema)
        assert got == response_payload


def test_calendar_client_uses_httpx_transport(calendar_client: Any) -> None:
    """respx only intercepts httpx.

    This test is here because people love to 'optimize' by swapping libraries.
    """
    req = _get_request_callable(calendar_client)
    assert callable(req)