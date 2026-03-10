"""Schema-driven contract tests for the Zoom Number Management endpoints."""

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


SPEC_PATH = Path(__file__).resolve().parent / "schemas" / "business_services" / "Number Management.json"
TITLE = "Number Management"
FIXTURE_NAME = "number_management_client"


# Load the Number Management schema from the repository.
@pytest.fixture
def number_management_spec() -> dict[str, Any]:
    return load_openapi_spec(SPEC_PATH, TITLE)


# Expand schema operations into concrete cases the tests can execute.
@pytest.fixture
def number_management_cases(number_management_spec: dict[str, Any]):
    cases = build_operation_cases(number_management_spec)
    if not cases:
        raise AssertionError("No operations discovered in Number Management OpenAPI spec.")
    return cases


# Basic schema sanity check before behavioral assertions begin.
def test_number_management_spec_is_openapi_3(number_management_spec: dict[str, Any]) -> None:
    assert number_management_spec.get("openapi", "").startswith("3.")
    assert number_management_spec.get("info", {}).get("title") == TITLE
    assert "paths" in number_management_spec and isinstance(number_management_spec["paths"], Mapping)


# Require operation IDs for readable and stable parametrized test names.
def test_number_management_operations_have_operation_ids(number_management_cases) -> None:
    assert not [case for case in number_management_cases if not case.operation_id]


# Validate example responses generated from the real schema.
def test_number_management_embedded_json_schemas_validate(
    number_management_cases,
    number_management_spec: dict[str, Any],
) -> None:
    validate_response_examples(number_management_spec, number_management_cases)


# Generate one pytest case per documented operation.
def pytest_generate_tests(metafunc: Any) -> None:
    if "number_management_case" in metafunc.fixturenames:
        spec = load_openapi_spec(SPEC_PATH, TITLE)
        cases = build_operation_cases(spec)
        ids = [f"{snake_case(case.operation_id)}[{case.method} {case.path}]" for case in cases]
        metafunc.parametrize("number_management_case", cases, ids=ids)


# Run the shared request/response contract for one endpoint case.
@pytest.mark.usefixtures("respx_mock")
def test_number_management_operation_contract(
    number_management_client: Any,
    number_management_spec: dict[str, Any],
    number_management_case,
    respx_mock: Any,
) -> None:
    run_operation_contract(
        request=get_request_callable(number_management_client, FIXTURE_NAME),
        spec=number_management_spec,
        case=number_management_case,
        respx_mock=respx_mock,
    )


# Make fixture wiring errors fail with a direct message.
def test_number_management_client_uses_callable_fixture(number_management_client: Any) -> None:
    assert callable(get_request_callable(number_management_client, FIXTURE_NAME))
