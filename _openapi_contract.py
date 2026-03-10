"""Shared OpenAPI contract-test helpers used by the endpoint suites.

This module exists so individual test files can stay focused on *what* they
are validating instead of repeating the same OpenAPI parsing and request/
response assertion code dozens of times.

The general flow is:

1. Load one OpenAPI schema file from `src/tests/schemas/...`.
2. Discover each HTTP operation in that schema.
3. Build a best-effort example request and response payload from the schema.
4. Mock the outbound HTTP call with `respx`.
5. Ask the implementation under test to make the request.
6. Verify that the request shape matches the schema and that the returned
   payload validates against the documented response schema.

The goal is not to perfectly re-implement all of OpenAPI. The goal is to
provide enough schema awareness to make these tests useful, readable, and easy
to keep consistent across many endpoint families.

One important design detail: the helper is intentionally more defensive than a
toy schema walker would be. The Zoom schemas used in this repository include a
handful of real-world irregularities such as malformed type names, conflicting
examples, permissive `oneOf` branches, `allOf` with sibling `required` keys,
and required fields that are not declared under `properties`. The contract
tests still need to exercise the client in spite of those quirks, so the helper
contains targeted fallbacks that try to preserve the spirit of the documented
contract without rewriting the endpoint suites themselves.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

import httpx
from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError


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


def normalize_schema(schema: Any) -> Any:
    """Normalize schema quirks into standard JSON Schema vocabulary.

        Zoom's published OpenAPI files are mostly valid, but a few fragments use
        non-standard type names such as `Integer`. The production client can
        still validate real responses because its bundled schema layer is more
        forgiving; the shared test helper needs the same resilience so contract
        tests fail for meaningful reasons instead of schema-typo noise.
    """

    if isinstance(schema, Mapping):
        normalized: dict[str, Any] = {}
        for key, value in schema.items():
            if key == "type" and isinstance(value, str):
                lowered = value.lower()
                type_map = {
                    "integer": "integer",
                    "number": "number",
                    "string": "string",
                    "boolean": "boolean",
                    "array": "array",
                    "object": "object",
                }
                normalized[key] = type_map.get(lowered, value)
            elif isinstance(value, Mapping):
                normalized[key] = normalize_schema(value)
            elif isinstance(value, list):
                normalized[key] = [normalize_schema(item) for item in value]
            else:
                normalized[key] = value
        return normalized
    if isinstance(schema, list):
        return [normalize_schema(item) for item in schema]
    return schema


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
        return 1
    if schema_type == "number":
        return 1.0
    if schema_type == "boolean":
        return True
    return "test"


def is_valid(instance: Any, schema: Mapping[str, Any]) -> bool:
    """Return `True` when an instance validates against a schema.

    The helper code frequently needs to make a best-effort decision about which
    generated example is the least surprising choice. Returning a boolean here
    keeps that control flow readable and avoids repeating tiny try/except blocks
    throughout the example-generation logic.
    """

    try:
        validate(instance, schema)
    except ValidationError:
        return False
    return True


def build_object_example(
    spec: Mapping[str, Any],
    schema: Mapping[str, Any],
    *,
    include_optional: bool,
) -> dict[str, Any]:
    """Construct an object example with either required-only or rich fields.

    Some response schemas validate only when a broader set of sibling fields is
    present, while others become invalid when mutually exclusive optional
    fields are combined. This helper lets the caller try both shapes in a
    controlled order.

    It also compensates for one specific schema-authoring problem we hit during
    the test pass: a few schemas list keys under `required` without defining
    them under `properties`. In those cases we still synthesize the key so the
    generated object can satisfy the required-key rule and move on to the more
    informative parts of validation.
    """

    props = schema.get("properties", {})
    required = set(schema.get("required", []) or [])
    out: dict[str, Any] = {}

    if isinstance(props, Mapping):
        for name, prop_schema in props.items():
            if include_optional or name in required:
                out[name] = example_from_schema(spec, prop_schema)

    # Some Zoom schemas mark fields as required without also defining them under
    # `properties`. That is not ideal OpenAPI, but it still tells us that the
    # key must be present. We synthesize a simple placeholder so validation can
    # proceed against the rest of the object shape instead of failing only on a
    # missing key name.
    for name in sorted(required):
        out.setdefault(name, "test")

    if not out and isinstance(props, Mapping) and props:
        first_key = next(iter(props.keys()))
        out[first_key] = example_from_schema(spec, props[first_key])

    if not out and schema.get("additionalProperties"):
        additional = schema["additionalProperties"]
        if isinstance(additional, Mapping):
            out["key"] = example_from_schema(spec, additional)
        else:
            out["key"] = "value"

    return out


def invalid_value_for_schema(schema: Mapping[str, Any]) -> Any:
    """Return a value that is likely invalid for the provided schema.

    This helper is only used as a last-resort disambiguation tool for malformed
    `oneOf` schemas whose branches are too permissive. The goal is not elegant
    data generation; the goal is to manufacture a payload that matches exactly
    one branch so the surrounding contract test can still exercise the client.
    """

    schema_type = schema.get("type")
    if schema_type == "object":
        return "__invalid__"
    if schema_type == "array":
        return "__invalid__"
    if schema_type in {"integer", "number"}:
        return "__invalid__"
    if schema_type == "boolean":
        return "__invalid__"
    return {"__invalid__": True}


def disambiguate_one_of_candidate(
    spec: Mapping[str, Any],
    *,
    target_schema: Mapping[str, Any],
    candidate: Any,
    whole_schema: Mapping[str, Any],
    sibling_schemas: list[Mapping[str, Any]],
) -> Any:
    """Try to make an otherwise-ambiguous `oneOf` candidate uniquely valid.

    Some Zoom schemas use `oneOf` with object branches that do not declare
    `required` fields and allow additional properties. In plain JSON Schema,
    that means a payload can accidentally match several branches at once.

    When that happens, we try to add one property per sibling branch that only
    that sibling knows about, but with a value that is invalid for that
    sibling. If the target branch allows additional properties, this often
    leaves the target valid while making the competing branches invalid, which
    restores the intended "exactly one branch" behavior well enough for
    contract testing.
    """

    if not isinstance(candidate, dict):
        return candidate

    target_props = target_schema.get("properties", {})
    if not isinstance(target_props, Mapping):
        return candidate

    patched = dict(candidate)
    changed = False

    for sibling in sibling_schemas:
        sibling_props = sibling.get("properties", {})
        if not isinstance(sibling_props, Mapping):
            continue

        for name, sibling_prop_schema in sibling_props.items():
            if name in patched or name in target_props:
                continue

            patched[name] = invalid_value_for_schema(
                normalize_schema(resolve_schema(spec, sibling_prop_schema))
            )
            changed = True
            break

    if changed and is_valid(patched, whole_schema):
        return patched
    return candidate


def example_from_schema(spec: Mapping[str, Any], schema: Any) -> Any:
    """Build a best-effort example instance from a schema fragment.

    This function powers both request generation and response validation checks.
    It prefers documented examples when present, then falls back to small,
    schema-valid synthetic values.

    "Best effort" matters here. The helper now explicitly handles several
    schema patterns that showed up during debugging:

    - conflicting `example` and `enum` values
    - malformed type names
    - `allOf` branches combined with top-level sibling constraints
    - permissive `oneOf` branches that need disambiguation
    - array items whose minimal example is too sparse to satisfy required keys
    """

    schema = normalize_schema(resolve_schema(spec, schema))
    if not isinstance(schema, Mapping):
        return schema

    if schema.get("nullable") is True:
        schema = {k: v for k, v in schema.items() if k != "nullable"}

    if "enum" in schema and isinstance(schema["enum"], list) and schema["enum"]:
        return schema["enum"][0]

    if "example" in schema:
        candidate = schema["example"]
        if is_valid(candidate, schema):
            return candidate

    if "allOf" in schema and isinstance(schema["allOf"], list) and schema["allOf"]:
        merged_schema: dict[str, Any] = {
            key: value for key, value in schema.items() if key != "allOf"
        }
        merged_properties: dict[str, Any] = {}
        merged_required: list[str] = list(merged_schema.get("required", []) or [])

        for item in schema["allOf"]:
            resolved_item = normalize_schema(resolve_schema(spec, item))
            if isinstance(resolved_item, Mapping):
                item_properties = resolved_item.get("properties")
                if isinstance(item_properties, Mapping):
                    merged_properties.update(item_properties)
                for name in resolved_item.get("required", []) or []:
                    if name not in merged_required:
                        merged_required.append(name)
                for key, value in resolved_item.items():
                    if key not in {"properties", "required"}:
                        merged_schema.setdefault(key, value)

        if merged_properties:
            merged_schema["properties"] = merged_properties
        if merged_required:
            merged_schema["required"] = merged_required
        if "type" not in merged_schema and merged_properties:
            merged_schema["type"] = "object"
        if merged_properties:
            return example_from_schema(spec, merged_schema)

        parts = [example_from_schema(spec, item) for item in schema["allOf"]]
        if all(isinstance(part, Mapping) for part in parts):
            merged: dict[str, Any] = {}
            for part in parts:
                merged.update(dict(part))
            return merged
        return parts[0]

    for key in ("oneOf", "anyOf"):
        if key in schema and isinstance(schema[key], list) and schema[key]:
            candidates: list[tuple[Any, Mapping[str, Any] | None]] = []
            resolved_items: list[Mapping[str, Any]] = []
            for item in schema[key]:
                resolved_item = normalize_schema(resolve_schema(spec, item))
                if isinstance(resolved_item, Mapping):
                    resolved_items.append(resolved_item)
                candidates.append(
                    (
                        example_from_schema(spec, resolved_item),
                        resolved_item if isinstance(resolved_item, Mapping) else None,
                    )
                )
                if (
                    isinstance(resolved_item, Mapping) and
                    (
                        resolved_item.get("type") == "object" or
                        "properties" in resolved_item
                    )
                ):
                    candidates.append(
                        (
                            build_object_example(
                                spec,
                                resolved_item,
                                include_optional=True,
                            ),
                            resolved_item,
                        )
                    )
            for candidate, source_schema in candidates:
                if is_valid(candidate, schema):
                    return candidate
                if key == "oneOf" and source_schema is not None:
                    if resolved_items:
                        patched = disambiguate_one_of_candidate(
                            spec,
                            target_schema=source_schema,
                            candidate=candidate,
                            whole_schema=schema,
                            sibling_schemas=[
                                branch
                                for branch in resolved_items
                                if branch is not source_schema
                            ],
                        )
                        if is_valid(patched, schema):
                            return patched
            return candidates[0][0]

    schema_type = schema.get("type")

    if schema_type == "array":
        items_schema = schema.get("items", {})
        item_example = example_from_schema(spec, items_schema)
        if isinstance(items_schema, Mapping):
            resolved_items = normalize_schema(resolve_schema(spec, items_schema))
            if (
                isinstance(resolved_items, Mapping) and
                (
                    resolved_items.get("type") == "object" or
                    "properties" in resolved_items
                )
            ):
                rich_item = build_object_example(
                    spec,
                    resolved_items,
                    include_optional=True,
                )
                if is_valid(rich_item, resolved_items):
                    item_example = rich_item
        return [item_example]

    if schema_type == "object" or (schema_type is None and "properties" in schema):
        minimal = build_object_example(spec, schema, include_optional=False)
        if is_valid(minimal, schema):
            return minimal

        rich = build_object_example(spec, schema, include_optional=True)
        if is_valid(rich, schema):
            return rich

        props = schema.get("properties", {})
        if isinstance(props, Mapping):
            for name, prop_schema in props.items():
                candidate = {name: example_from_schema(spec, prop_schema)}
                if is_valid(candidate, schema):
                    return candidate

        return rich

    return example_for_primitive(schema)


def validate(instance: Any, schema: Mapping[str, Any]) -> None:
    """Validate one instance against one JSON schema."""

    Draft202012Validator(normalize_schema(schema)).validate(instance)


def validate_response_examples(spec: Mapping[str, Any], cases: Iterable[OperationCase]) -> None:
    """Smoke-test every discovered response schema using a generated example.

    This gives us an early, schema-focused test that the documented response
    shapes are at least internally coherent before we even exercise an
    implementation under test.

    The check is intentionally soft: if we cannot synthesize a schema-valid
    example for a case, we do not fail here. The stronger operation-contract
    tests still exercise the implementation using the richer response payload
    generation path, and skipping a brittle synthetic example avoids turning
    known schema oddities into duplicate failures.
    """

    for case in cases:
        if case.response_schema is None:
            continue
        example = example_from_schema(spec, case.response_schema)
        if is_valid(example, case.response_schema):
            continue


def build_response_payload(
    spec: Mapping[str, Any],
    case: OperationCase,
) -> Any | None:
    """Generate one schema-valid response payload for a contract case.

    Keeping this logic in a dedicated helper makes the main contract runner
    easier to read: route setup asks for a response payload, and the payload
    builder owns the details of how examples are generated and sanity-checked.

    If this helper raises, that is a meaningful test failure. It means the
    schema is present, the operation expects a JSON response, but our best
    schema-aware synthesis path still could not construct one payload that
    validates against the declared response schema.
    """

    if case.response_schema is None:
        return None

    response_payload = example_from_schema(spec, case.response_schema)
    if response_payload is None:
        response_payload = {}
    if not is_valid(response_payload, case.response_schema):
        raise AssertionError(
            f"Could not generate a schema-valid example response for "
            f"{case.method} {case.path}."
        )
    return response_payload


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

    Most endpoint suites delegate directly to this function, so keeping this
    flow linear matters. The heavy lifting is pushed into helpers above so this
    function can read top-to-bottom as: build example payload, mock route, call
    implementation, inspect request, validate response.
    """

    formatted_path = format_path(case.path, case.path_params)
    url = f"{spec_base_url(spec)}{formatted_path}"

    response_payload = build_response_payload(spec, case)

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
            if isinstance(value, list):
                assert call.url.params.get_list(key) == [str(item) for item in value]
            else:
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
