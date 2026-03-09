

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

import httpx
import pytest
import respx
from jsonschema import Draft202012Validator


# These tests are *contract tests* for whatever Zoom API client you build.
# They intentionally assume a small, opinionated surface area so the library
# stays consistent as you add endpoints.
#
# Expected implementation (minimal contract):
# - `zoompy.client.ZoomClient` exists.
# - `ZoomClient` has `virtual_agent` attribute.
# - `virtual_agent` exposes one method per OpenAPI `operationId` (snake_case).
# - Each method issues the correct HTTP request using httpx.
# - Responses are JSON-decoded and validated against the OpenAPI response schema.
#   (Invalid responses must raise `ValueError`.)


SCHEMA_PATH = Path(__file__).resolve().parent / "schemas" / "build_platform" / "Virtual Agent.json"


@dataclass(frozen=True)
class Operation:
    path: str
    method: str
    operation_id: str
    parameters: tuple[dict[str, Any], ...]
    request_schema: dict[str, Any] | None
    response_schema: dict[str, Any] | None


def _snake_case(name: str) -> str:
    out: list[str] = []
    for ch in name:
        if ch.isupper() and out:
            out.append("_")
        out.append(ch.lower())
    return "".join(out).replace("__", "_")


def _load_openapi(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data.get("openapi"), "Schema must be an OpenAPI document"
    assert isinstance(data.get("paths"), dict) and data["paths"], "Schema must define paths"
    return data


def _json_pointer_get(doc: Any, pointer: str) -> Any:
    # pointer like: /components/schemas/Foo
    if not pointer.startswith("/"):
        raise ValueError(f"Unsupported JSON pointer: {pointer}")
    cur = doc
    for raw in pointer.lstrip("/").split("/"):
        key = raw.replace("~1", "/").replace("~0", "~")
        if isinstance(cur, dict):
            cur = cur[key]
        elif isinstance(cur, list):
            cur = cur[int(key)]
        else:
            raise KeyError(pointer)
    return cur


def _resolve_refs(spec: dict[str, Any], schema: Any) -> Any:
    # Minimal internal $ref resolver for local refs only.
    if isinstance(schema, dict):
        if "$ref" in schema:
            ref = schema["$ref"]
            if not ref.startswith("#"):
                raise ValueError(f"Only local $ref supported in tests: {ref}")
            target = _json_pointer_get(spec, ref[1:])
            return _resolve_refs(spec, target)
        return {k: _resolve_refs(spec, v) for k, v in schema.items()}
    if isinstance(schema, list):
        return [_resolve_refs(spec, v) for v in schema]
    return schema


def _extract_operations(spec: dict[str, Any]) -> list[Operation]:
    ops: list[Operation] = []
    for path, methods in spec["paths"].items():
        for method, op in methods.items():
            if method.startswith("x-"):
                continue
            operation_id = op.get("operationId")
            if not operation_id:
                continue

            params = tuple(op.get("parameters") or ())

            request_schema: dict[str, Any] | None = None
            if "requestBody" in op:
                content = (op["requestBody"].get("content") or {}).get("application/json")
                if content and "schema" in content:
                    request_schema = _resolve_refs(spec, content["schema"])

            response_schema: dict[str, Any] | None = None
            responses = op.get("responses") or {}
            resp_200 = responses.get("200")
            if resp_200:
                content = (resp_200.get("content") or {}).get("application/json")
                if content and "schema" in content:
                    response_schema = _resolve_refs(spec, content["schema"])

            ops.append(
                Operation(
                    path=path,
                    method=method.upper(),
                    operation_id=operation_id,
                    parameters=params,
                    request_schema=request_schema,
                    response_schema=response_schema,
                )
            )
    return ops


def _example_from_schema(schema: Any) -> Any:
    # Best-effort example builder that aims to satisfy required fields.
    if not isinstance(schema, dict):
        return None

    if "example" in schema:
        return schema["example"]

    if "enum" in schema and isinstance(schema["enum"], list) and schema["enum"]:
        return schema["enum"][0]

    schema_type = schema.get("type")

    if schema_type == "object" or ("properties" in schema and isinstance(schema.get("properties"), dict)):
        props: dict[str, Any] = schema.get("properties") or {}
        required: list[str] = list(schema.get("required") or [])
        out: dict[str, Any] = {}
        # Fill required first.
        for k in required:
            out[k] = _example_from_schema(props.get(k, {}))
        # Add one optional property if it helps avoid empty objects.
        if not out and props:
            k0 = next(iter(props.keys()))
            out[k0] = _example_from_schema(props[k0])
        return out

    if schema_type == "array":
        item_schema = schema.get("items") or {}
        min_items = int(schema.get("minItems") or 0)
        # Some schemas use maxItems only; keep payload small.
        count = max(1, min_items) if (min_items or item_schema) else 0
        return [_example_from_schema(item_schema) for _ in range(count)]

    if schema_type == "string":
        fmt = schema.get("format")
        if fmt == "date-time":
            return "2024-01-01T00:00:00Z"
        if fmt == "date":
            return "2024-01-01"
        return "string"

    if schema_type == "integer":
        minimum = schema.get("minimum")
        if isinstance(minimum, int):
            return minimum
        return 0

    if schema_type == "number":
        minimum = schema.get("minimum")
        if isinstance(minimum, (int, float)):
            return float(minimum)
        return 0.0

    if schema_type == "boolean":
        return False

    # Fallback when type is omitted but constructs exist.
    if "oneOf" in schema and isinstance(schema["oneOf"], list) and schema["oneOf"]:
        return _example_from_schema(schema["oneOf"][0])
    if "anyOf" in schema and isinstance(schema["anyOf"], list) and schema["anyOf"]:
        return _example_from_schema(schema["anyOf"][0])
    if "allOf" in schema and isinstance(schema["allOf"], list) and schema["allOf"]:
        # Merge is complicated; pick first as a pragmatic contract-test input.
        return _example_from_schema(schema["allOf"][0])

    return None


def _required_path_params(parameters: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for p in parameters:
        if p.get("in") != "path":
            continue
        name = p.get("name")
        if not name:
            continue
        schema = p.get("schema") or {}
        out[name] = _example_from_schema(schema) or "id"
    return out


def _query_params(parameters: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for p in parameters:
        if p.get("in") != "query":
            continue
        name = p.get("name")
        if not name:
            continue
        schema = p.get("schema") or {}
        if p.get("required"):
            out[name] = _example_from_schema(schema)
    return {k: v for k, v in out.items() if v is not None}


def _format_path(path_template: str, path_params: Mapping[str, Any]) -> str:
    out = path_template
    for k, v in path_params.items():
        out = out.replace("{" + k + "}", str(v))
    return out


@pytest.fixture(scope="module")
def virtual_agent_spec() -> dict[str, Any]:
    return _load_openapi(SCHEMA_PATH)


@pytest.fixture(scope="module")
def virtual_agent_ops(virtual_agent_spec: dict[str, Any]) -> list[Operation]:
    return _extract_operations(virtual_agent_spec)


def test_virtual_agent_schema_sanity(virtual_agent_spec: dict[str, Any]) -> None:
    assert virtual_agent_spec["info"]["title"] == "Virtual Agent"
    assert "/virtual_agent/report/engagements" in virtual_agent_spec["paths"]
    # The engagements endpoint advertises query parameters like agent_types and page_size.
    params = (virtual_agent_spec["paths"]["/virtual_agent/report/engagements"]["get"].get("parameters") or [])
    param_names = {p.get("name") for p in params}
    assert {"page_size", "next_page_token", "agent_types"}.issubset(param_names)


def test_virtual_agent_client_surface_area_matches_operation_ids(virtual_agent_ops: list[Operation]) -> None:
    from zoompy.client import ZoomClient  # type: ignore

    client = ZoomClient(base_url="https://api.zoom.us/v2", token="test")
    va = getattr(client, "virtual_agent")

    missing: list[str] = []
    for op in virtual_agent_ops:
        method_name = _snake_case(op.operation_id)
        if not hasattr(va, method_name):
            missing.append(f"{op.operation_id} -> virtual_agent.{method_name}()")

    assert not missing, "Missing endpoint methods:\n" + "\n".join(missing)


@pytest.mark.parametrize("operation_id", [
    "GetZVAEngagements",
    "GetZVAQueryDetails",
    "GetZVAengagementvariabledetails",
    "GetZVASurveys",
    "GetZVATranscripts",
    "GetArticles",
    "CreateArticle",
    "GetArticle",
    "UpdateArticle",
    "DeleteArticle",
    "CreateSyncRequest",
    "GetSync",
])
def test_virtual_agent_known_operation_ids_exist_in_schema(virtual_agent_ops: list[Operation], operation_id: str) -> None:
    assert any(op.operation_id == operation_id for op in virtual_agent_ops)


def test_virtual_agent_methods_issue_correct_http_requests_and_validate_responses(
    virtual_agent_spec: dict[str, Any],
    virtual_agent_ops: list[Operation],
) -> None:
    from zoompy.client import ZoomClient  # type: ignore

    base_url = "https://api.zoom.us/v2"
    client = ZoomClient(base_url=base_url, token="test")
    va = getattr(client, "virtual_agent")

    # We exercise a representative subset covering: path params, query params, and request bodies.
    chosen = [
        "GetZVAEngagements",       # GET with query params
        "GetArticles",             # GET with path param
        "CreateArticle",           # POST with JSON body
        "UpdateArticle",           # PUT with JSON body + path params
        "DeleteArticle",           # DELETE with path params
    ]

    by_id = {op.operation_id: op for op in virtual_agent_ops}

    with respx.mock(assert_all_called=True) as router:
        for op_id in chosen:
            op = by_id[op_id]
            method_name = _snake_case(op.operation_id)
            fn = getattr(va, method_name)

            path_params = _required_path_params(op.parameters)
            query = _query_params(op.parameters)
            url_path = _format_path(op.path, path_params)

            response_json: Any
            if op.response_schema is not None:
                response_json = _example_from_schema(op.response_schema)
            else:
                response_json = {}

            # Validate our generated example is actually schema-valid (otherwise the schema is weird).
            if op.response_schema is not None:
                Draft202012Validator(op.response_schema).validate(response_json)

            route = router.request(op.method, base_url + url_path).mock(
                return_value=httpx.Response(200, json=response_json)
            )

            args: list[Any] = []
            kwargs: dict[str, Any] = {}

            # Provide path params positionally when possible, else by keyword.
            # We assume the implementation chooses keyword-friendly names.
            kwargs.update(path_params)
            if query:
                kwargs.update(query)

            if op.request_schema is not None:
                body = _example_from_schema(op.request_schema)
                # Ensure body is schema-valid.
                Draft202012Validator(op.request_schema).validate(body)
                kwargs["json"] = body

            result = fn(*args, **kwargs)

            assert route.called, f"Expected HTTP request for {op.operation_id}"
            assert isinstance(result, (dict, list)), "Client should return decoded JSON"


def test_virtual_agent_raises_on_schema_mismatch(virtual_agent_ops: list[Operation]) -> None:
    from zoompy.client import ZoomClient  # type: ignore

    base_url = "https://api.zoom.us/v2"
    client = ZoomClient(base_url=base_url, token="test")
    va = getattr(client, "virtual_agent")

    # Pick an endpoint with a non-trivial response schema.
    op = next(o for o in virtual_agent_ops if o.operation_id == "GetZVAEngagements")
    assert op.response_schema is not None

    bad_payload = {"this": "is not what the schema says"}

    with respx.mock(assert_all_called=True) as router:
        router.get(base_url + op.path).mock(return_value=httpx.Response(200, json=bad_payload))

        fn = getattr(va, _snake_case(op.operation_id))
        with pytest.raises(ValueError):
            fn()