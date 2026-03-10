"""Schema-driven contract tests for the Zoom Commerce endpoints."""

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


SPEC_PATH = Path(__file__).resolve().parent / "schemas" / "business_services" / "Commerce.json"
TITLE = "Commerce"
FIXTURE_NAME = "commerce_client"


# Load the Commerce OpenAPI schema.
@pytest.fixture
def commerce_spec() -> dict[str, Any]:
    return load_openapi_spec(SPEC_PATH, TITLE)


# Build concrete test cases from the schema.
@pytest.fixture
def commerce_cases(commerce_spec: dict[str, Any]):
    cases = build_operation_cases(commerce_spec)
    if not cases:
        raise AssertionError("No operations discovered in Commerce OpenAPI spec.")
    return cases


# Confirm that the schema document is the expected OpenAPI 3 file.
def test_commerce_spec_is_openapi_3(commerce_spec: dict[str, Any]) -> None:
    assert commerce_spec.get("openapi", "").startswith("3.")
    assert commerce_spec.get("info", {}).get("title") == TITLE
    assert "paths" in commerce_spec and isinstance(commerce_spec["paths"], Mapping)


# Operation IDs are required for readable parametrized test output.
def test_commerce_operations_have_operation_ids(commerce_cases) -> None:
    assert not [case for case in commerce_cases if not case.operation_id]


# Validate generated example responses against the real documented schema.
def test_commerce_embedded_json_schemas_validate(
    commerce_cases,
    commerce_spec: dict[str, Any],
) -> None:
    validate_response_examples(commerce_spec, commerce_cases)


# Generate one parametrized test case per documented endpoint operation.
def pytest_generate_tests(metafunc: Any) -> None:
    if "commerce_case" in metafunc.fixturenames:
        spec = load_openapi_spec(SPEC_PATH, TITLE)
        cases = build_operation_cases(spec)
        ids = [f"{snake_case(case.operation_id)}[{case.method} {case.path}]" for case in cases]
        metafunc.parametrize("commerce_case", cases, ids=ids)


# Run the shared contract assertions for one Commerce operation case.
@pytest.mark.usefixtures("respx_mock")
def test_commerce_operation_contract(
    commerce_client: Any,
    commerce_spec: dict[str, Any],
    commerce_case,
    respx_mock: Any,
) -> None:
    run_operation_contract(
        request=get_request_callable(commerce_client, FIXTURE_NAME),
        spec=commerce_spec,
        case=commerce_case,
        respx_mock=respx_mock,
    )


# Give a direct failure when the project fixture shape is wrong.
def test_commerce_client_uses_callable_fixture(commerce_client: Any) -> None:
    assert callable(get_request_callable(commerce_client, FIXTURE_NAME))
