"""Schema-driven contract tests for the Zoom Virtual Agent endpoints."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

import pytest

from _openapi_contract import (
    build_operation_cases,
    get_request_callable,
    load_openapi_spec,
    run_operation_contract,
    snake_case,
    validate_response_examples,
)


SPEC_PATH = Path(__file__).resolve().parent / "schemas" / "business_services" / "Virtual Agent.json"
TITLE = "Virtual Agent"
FIXTURE_NAME = "virtual_agent_client"


# Load the Virtual Agent schema document from disk.
@pytest.fixture
def virtual_agent_spec() -> dict[str, Any]:
    return load_openapi_spec(SPEC_PATH, TITLE)


# Build one concrete, reusable operation case per documented endpoint.
@pytest.fixture
def virtual_agent_cases(virtual_agent_spec: dict[str, Any]):
    cases = build_operation_cases(virtual_agent_spec)
    if not cases:
        raise AssertionError("No operations discovered in Virtual Agent OpenAPI spec.")
    return cases


# Confirm the schema file itself is the expected OpenAPI document.
def test_virtual_agent_spec_is_openapi_3(virtual_agent_spec: dict[str, Any]) -> None:
    assert virtual_agent_spec.get("openapi", "").startswith("3.")
    assert virtual_agent_spec.get("info", {}).get("title") == TITLE
    assert "paths" in virtual_agent_spec and isinstance(virtual_agent_spec["paths"], Mapping)


# Operation IDs are required so failure output remains readable.
def test_virtual_agent_operations_have_operation_ids(virtual_agent_cases) -> None:
    assert not [case for case in virtual_agent_cases if not case.operation_id]


# Validate generated example responses against the actual Virtual Agent schema.
def test_virtual_agent_embedded_json_schemas_validate(
    virtual_agent_cases,
    virtual_agent_spec: dict[str, Any],
) -> None:
    validate_response_examples(virtual_agent_spec, virtual_agent_cases)


# Generate one pytest case per documented operation.
def pytest_generate_tests(metafunc: Any) -> None:
    if "virtual_agent_case" in metafunc.fixturenames:
        spec = load_openapi_spec(SPEC_PATH, TITLE)
        cases = build_operation_cases(spec)
        ids = [f"{snake_case(case.operation_id)}[{case.method} {case.path}]" for case in cases]
        metafunc.parametrize("virtual_agent_case", cases, ids=ids)


# Execute the shared request/response contract for one endpoint case.
@pytest.mark.usefixtures("respx_mock")
def test_virtual_agent_operation_contract(
    virtual_agent_client: Any,
    virtual_agent_spec: dict[str, Any],
    virtual_agent_case,
    respx_mock: Any,
) -> None:
    run_operation_contract(
        request=get_request_callable(virtual_agent_client, FIXTURE_NAME),
        spec=virtual_agent_spec,
        case=virtual_agent_case,
        respx_mock=respx_mock,
    )


# Explain fixture shape problems with a direct, readable failure.
def test_virtual_agent_client_uses_callable_fixture(virtual_agent_client: Any) -> None:
    assert callable(get_request_callable(virtual_agent_client, FIXTURE_NAME))
