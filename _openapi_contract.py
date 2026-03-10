"""Shared OpenAPI contract-test helpers used by the endpoint suites.

This module exists so individual test files can stay focused on *what* they
are validating instead of repeating the same OpenAPI parsing and request/response
assertion code dozens of times.

The general flow is:

1. Load one OpenAPI schema file from `src/tests/schemas/...`.
2. Discover each HTTP operation in that schema.
3. Build a minimal example request and response payload from the schema itself.
4. Mock the outbound HTTP call with `respx`.
5. Ask the implementation under test to make the request.
6. Verify that the request shape matches the schema and that the returned payload
   validates against the documented response schema.

The goal is not to perfectly re-implement all of OpenAPI. The goal is to provide
enough schema awareness to make these tests useful, readable, and easy to keep
consistent across many endpoint families.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

import httpx
from jsonschema import Draft202012Validator


@dataclass(frozen=True)
class OperationCase:
    """A fully prepared test case for one OpenAPI operation.

    Each instance contains everything a parametrized pytest test needs in order
    to exercise one endpoint:

    - the HTTP method and path
    - example path/query/body input data
    - the expected success status code
    - the response schema to validate against
    """

    operation_id: str
    method: str
    path: str
    path_params: dict[str, Any]
    query_params: dict[str, Any]
    request_json: Any | None
    response_schema: dict[str, Any] | None
    status_code: int


def load_openapi_spec(path: Path, expected_title: str | None = None) -> dict[str, Any]:
    """Load a schema file and optionally verify the document title.

    We fail early here so individual test files do not need to repeat the same
    “did the file move / did we point at the wrong schema?” checks.
    """

    if not path.exists():
        raise AssertionError(f"OpenAPI spec not found at {path}")
    spec = json.loads(path.read_text(encoding="utf-8"))
    if expected_title is not None:
        actual = spec.get("info", {}).get("title")
        if actual != expected_title:
            raise AssertionError(f"Expected OpenAPI title {expected_title!r}, got {actual!r}")
    return spec


def get_request_callable(client: Any, fixture_name: str):
    """Normalize the fixture contract to one simple callable shape.

    Every endpoint suite expects its pytest fixture to return a callable that
    behaves like:

        request(method, path, **kwargs)

    Keeping that rule uniform makes the tests much easier to reason about than
    supporting a mix of service objects, client instances, adapters, and custom
    hook methods.
    """

    if callable(client):
        return client
    raise AssertionError(
        f"The `{fixture_name}` fixture must return a callable "
        "with the contract request(method, path, **kwargs)."
    )


def snake_case(name: str) -> str:
    """Convert an operationId-like name into a stable pytest id fragment."""

    out: list[str] = []
    for ch in name:
        if ch.isupper() and out:
            out.append("_")
        out.append(ch.lower())
    return "".join(out).replace("__", "_")


def spec_base_url(spec: Mapping[str, Any], fallback: str = "https://api.zoom.us/v2") -> str:
    """Pick the first declared server URL, or fall back to Zoom's v2 base URL.

    Most schema files include a `servers` block, but not all of them do it
    consistently. The fallback keeps the tests deterministic.
    """

    servers = spec.get("servers")
    if isinstance(servers, list):
        for server in servers:
            if isinstance(server, Mapping):
                url = server.get("url")
                if isinstance(url, str) and url:
                    return url.rstrip("/")
    return fallback


def pick_json_media_type(content: Mapping[str, Any]) -> tuple[str, Mapping[str, Any]] | None:
    """Select the best JSON-ish media type from an OpenAPI content map.

    Zoom schemas are not perfectly uniform. Some use `application/json`, some
    use variants like `application/scim+json`, and others may include charset
    suffixes. This helper centralizes the selection logic so the test files do
    not need endpoint-specific special cases.
    """

    preferred = (
        "application/json",
        "application/json; charset=utf-8",
        "application/scim+json",
    )
    for media_type in preferred:
        candidate = content.get(media_type)
        if isinstance(candidate, Mapping):
            return media_type, candidate

    for media_type, candidate in content.items():
        if isinstance(media_type, str) and "json" in media_type and isinstance(candidate, Mapping):
            return media_type, candidate

    return None


def iter_operations(spec: Mapping[str, Any]) -> Iterable[tuple[str, str, str, Mapping[str, Any]]]:
    """Yield every HTTP operation declared in the schema.

    Only standard CRUD-like verbs are considered because those are the ones
    the current endpoint suites are designed to exercise.
    """

    paths = spec.get("paths", {})
    for path, item in paths.items():
        if not isinstance(item, Mapping):
            continue
        for method in ("get", "post", "put", "patch", "delete"):
            op = item.get(method)
            if isinstance(op, Mapping):
                yield op.get("operationId") or f"{method}_{path}", method.upper(), path, op


def deepcopy_json(value: Any) -> Any:
    """Clone plain JSON-compatible data using JSON round-tripping.

    This is intentionally simple. The schemas and examples in these tests are
    JSON data structures, so the tradeoff is acceptable and keeps the helper
    implementation small.
    """

    return json.loads(json.dumps(value))


def resolve_ref(spec: Mapping[str, Any], ref: str) -> Any:
    """Resolve a local `$ref` like `#/components/schemas/Foo`.

    These tests are intentionally offline and repository-local, so only local
    references are supported. If a schema starts depending on remote references,
    that should be handled deliberately rather than silently guessed at here.
    """

    if not ref.startswith("#/"):
        raise ValueError(f"Only local refs are supported in tests, got: {ref}")
    cur: Any = spec
    for part in ref.lstrip("#/").split("/"):
        if not isinstance(cur, Mapping) or part not in cur:
            raise KeyError(f"Unresolvable $ref: {ref}")
        cur = cur[part]
    return cur


def resolve_schema(spec: Mapping[str, Any], schema: Any) -> Any:
    """Recursively inline local `$ref` values inside a schema fragment.

    This gives later helpers a resolved, easy-to-walk schema tree for example
    generation and validation.
    """

    if not isinstance(schema, Mapping):
        return schema

    if "$ref" in schema:
        target = deepcopy_json(resolve_ref(spec, str(schema["$ref"])))
        siblings = {k: v for k, v in schema.items() if k != "$ref"}
        if siblings and isinstance(target, Mapping):
            merged = deepcopy_json(target)
            merged.update(deepcopy_json(siblings))
            target = merged
        return resolve_schema(spec, target)

    resolved: dict[str, Any] = {}
    for key, value in schema.items():
        if isinstance(value, Mapping):
            resolved[key] = resolve_schema(spec, value)
        elif isinstance(value, list):
            resolved[key] = [resolve_schema(spec, item) for item in value]
        else:
            resolved[key] = value
    return resolved


def pick_success_response(responses: Mapping[str, Any]) -> tuple[int, dict[str, Any] | None] | None:
    """Choose the response shape the tests should treat as “successful”.

    We prefer 200 responses, then any documented 2xx response, and finally
    `default` if that is all the schema provides.
    """

    def _try(code_key: str) -> tuple[int, dict[str, Any] | None] | None:
        entry = responses.get(code_key)
        if not isinstance(entry, Mapping):
            return None
        try:
            code_int = int(code_key)
        except Exception:
            code_int = 200

        content = entry.get("content")
        if not isinstance(content, Mapping):
            return code_int, None

        picked = pick_json_media_type(content)
        if picked is None:
            return code_int, None
        _, app_json = picked

        schema = app_json.get("schema")
        if not isinstance(schema, Mapping):
            return code_int, None
        return code_int, dict(schema)

    if "200" in responses:
        return _try("200")

    for key in responses.keys():
        if isinstance(key, str) and key.isdigit() and 200 <= int(key) < 300:
            got = _try(key)
            if got is not None:
                return got

    if "default" in responses:
        return _try("default")

    return None


def example_for_primitive(schema: Mapping[str, Any]) -> Any:
    """Produce a minimal example value for a primitive schema type.

    The result does not aim to be realistic business data. It aims to be:

    - valid for the schema
    - deterministic
    - easy to inspect when a test fails
    """

    if "enum" in schema and isinstance(schema["enum"], list) and schema["enum"]:
        return schema["enum"][0]

    schema_type = schema.get("type")
    fmt = schema.get("format")

    if schema_type == "string" or schema_type is None:
        if "example" in schema:
            return schema["example"]
        if fmt in {"email", "uri", "uuid", "date-time"}:
            if fmt == "email":
                return "test@example.com"
            if fmt == "uuid":
                return "00000000-0000-0000-0000-000000000000"
            if fmt == "date-time":
                return "2024-01-01T00:00:00Z"
            return "https://example.com"
        return "test"
    if schema_type == "integer":
        return int(schema.get("example", 1))
    if schema_type == "number":
        return float(schema.get("example", 1.0))
    if schema_type == "boolean":
        return bool(schema.get("example", True))
    return "test"


def example_from_schema(spec: Mapping[str, Any], schema: Any) -> Any:
    """Build a best-effort example instance from a schema fragment.

    This function powers both request generation and response validation checks.
    It prefers documented examples when present, then falls back to small,
    schema-valid synthetic values.
    """

    schema = resolve_schema(spec, schema)
    if not isinstance(schema, Mapping):
        return schema

    if schema.get("nullable") is True:
        schema = {k: v for k, v in schema.items() if k != "nullable"}

    if "example" in schema:
        return schema["example"]

    if "allOf" in schema and isinstance(schema["allOf"], list) and schema["allOf"]:
        parts = [example_from_schema(spec, item) for item in schema["allOf"]]
        if all(isinstance(part, Mapping) for part in parts):
            merged: dict[str, Any] = {}
            for part in parts:
                merged.update(dict(part))
            return merged
        return parts[0]

    for key in ("oneOf", "anyOf"):
        if key in schema and isinstance(schema[key], list) and schema[key]:
            return example_from_schema(spec, schema[key][0])

    schema_type = schema.get("type")

    if schema_type == "array":
        return [example_from_schema(spec, schema.get("items", {}))]

    if schema_type == "object" or (schema_type is None and "properties" in schema):
        props = schema.get("properties", {})
        required = set(schema.get("required", []) or [])
        out: dict[str, Any] = {}
        if isinstance(props, Mapping):
            for name, prop_schema in props.items():
                if name in required:
                    out[name] = example_from_schema(spec, prop_schema)

        if not out and isinstance(props, Mapping) and props:
            first_key = next(iter(props.keys()))
            out[first_key] = example_from_schema(spec, props[first_key])

        if not out and schema.get("additionalProperties"):
            out["key"] = "value"

        return out

    return example_for_primitive(schema)


def validate(instance: Any, schema: Mapping[str, Any]) -> None:
    """Validate one instance against one JSON schema."""

    Draft202012Validator(schema).validate(instance)


def validate_response_examples(spec: Mapping[str, Any], cases: Iterable[OperationCase]) -> None:
    """Smoke-test every discovered response schema using a generated example.

    This gives us an early, schema-focused test that the documented response
    shapes are at least internally coherent before we even exercise an
    implementation under test.
    """

    for case in cases:
        if case.response_schema is None:
            continue
        validate(example_from_schema(spec, case.response_schema), case.response_schema)


def build_operation_cases(spec: Mapping[str, Any]) -> list[OperationCase]:
    """Turn the raw OpenAPI document into parametrized pytest cases.

    For each operation we gather:

    - required path parameters
    - required query parameters
    - a minimal JSON request body when one exists
    - the preferred success response schema and status code
    """

    cases: list[OperationCase] = []
    for op_id, method, path, op in iter_operations(spec):
        parameters: list[Mapping[str, Any]] = []

        path_item = spec.get("paths", {}).get(path, {})
        if isinstance(path_item, Mapping) and isinstance(path_item.get("parameters"), list):
            parameters.extend([p for p in path_item["parameters"] if isinstance(p, Mapping)])

        if isinstance(op.get("parameters"), list):
            parameters.extend([p for p in op["parameters"] if isinstance(p, Mapping)])

        path_params: dict[str, Any] = {}
        query_params: dict[str, Any] = {}

        for parameter in parameters:
            where = parameter.get("in")
            name = parameter.get("name")
            if not isinstance(name, str) or where not in {"path", "query"}:
                continue
            schema = parameter.get("schema") or {}
            value = parameter.get("example")
            if value is None:
                value = example_from_schema(spec, schema)
            if where == "path":
                path_params[name] = value
            elif parameter.get("required") is True:
                query_params[name] = value

        request_json: Any | None = None
        request_body = op.get("requestBody")
        if isinstance(request_body, Mapping):
            content = request_body.get("content")
            if isinstance(content, Mapping):
                picked = pick_json_media_type(content)
                if picked is not None:
                    _, app_json = picked
                else:
                    app_json = None
                if isinstance(app_json, Mapping) and isinstance(app_json.get("schema"), (Mapping, list)):
                    request_json = example_from_schema(spec, app_json["schema"])

        response_schema: dict[str, Any] | None = None
        status_code = 200
        responses = op.get("responses")
        if isinstance(responses, Mapping):
            pick = pick_success_response(responses)
            if pick is not None:
                status_code, raw_schema = pick
                response_schema = (
                    resolve_schema(spec, raw_schema) if isinstance(raw_schema, Mapping) else None
                )

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

    return cases


def format_path(path: str, path_params: Mapping[str, Any]) -> str:
    """Replace `{pathParam}` placeholders with concrete example values."""

    out = path
    for key, value in path_params.items():
        out = out.replace("{" + key + "}", str(value))
    return out


def run_operation_contract(
    *,
    request: Any,
    spec: Mapping[str, Any],
    case: OperationCase,
    respx_mock: Any,
    request_headers: Mapping[str, str] | None = None,
) -> None:
    """Execute the core request/response contract for one operation case.

    Individual endpoint suites all call this helper so they do not each need
    their own copy of the same `respx` wiring and assertion logic.

    The helper verifies:

    - the implementation made the expected HTTP request
    - required query parameters were sent
    - JSON request bodies were serialized correctly
    - optional request headers were forwarded when required
    - the returned payload matches the documented response schema
    """

    formatted_path = format_path(case.path, case.path_params)
    url = f"{spec_base_url(spec)}{formatted_path}"

    response_payload: Any = None
    if case.response_schema is not None:
        response_payload = example_from_schema(spec, case.response_schema)
        if response_payload is None:
            response_payload = {}
        validate(response_payload, case.response_schema)

    route_kwargs: dict[str, Any] = {"status_code": case.status_code}
    if case.response_schema is not None:
        route_kwargs["json"] = response_payload
    route = respx_mock.request(case.method, url).mock(return_value=httpx.Response(**route_kwargs))

    result = request(
        case.method,
        case.path,
        path_params=case.path_params or None,
        params=case.query_params or None,
        json=case.request_json,
        headers=dict(request_headers) if request_headers else None,
    )

    got = result.json() if isinstance(result, httpx.Response) and result.content else result
    assert route.called

    call = route.calls[-1].request
    if case.query_params:
        for key, value in case.query_params.items():
            assert call.url.params.get(key) == str(value)
    if request_headers:
        for key, value in request_headers.items():
            assert call.headers.get(key) == value
    if case.request_json is not None and case.method in {"POST", "PUT", "PATCH"}:
        assert call.headers.get("content-type", "").startswith("application/json")
        sent = json.loads(call.content.decode("utf-8")) if call.content else None
        assert sent == case.request_json

    if case.response_schema is not None:
        validate(got, case.response_schema)
        assert got == response_payload
    else:
        assert got is None
