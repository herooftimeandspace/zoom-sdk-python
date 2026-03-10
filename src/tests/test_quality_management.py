"""Schema-driven contract tests for the Zoom Quality Management endpoints."""

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


SPEC_PATH = Path(__file__).resolve().parent / "schemas" / "business_services" / "Quality Management.json"
TITLE = "Quality Management"
FIXTURE_NAME = "quality_management_client"


# Load the Quality Management schema from disk.
@pytest.fixture
def quality_management_spec() -> dict[str, Any]:
    return load_openapi_spec(SPEC_PATH, TITLE)


# Build concrete, schema-derived operation cases for reuse across tests.
@pytest.fixture
def quality_management_cases(quality_management_spec: dict[str, Any]):
    cases = build_operation_cases(quality_management_spec)
    if not cases:
        raise AssertionError("No operations discovered in Quality Management OpenAPI spec.")
    return cases


# Verify that the schema file is the expected OpenAPI document.
def test_quality_management_spec_is_openapi_3(quality_management_spec: dict[str, Any]) -> None:
    assert quality_management_spec.get("openapi", "").startswith("3.")
    assert quality_management_spec.get("info", {}).get("title") == TITLE
    assert "paths" in quality_management_spec and isinstance(quality_management_spec["paths"], Mapping)


# Operation IDs are required to keep parametrized output readable.
def test_quality_management_operations_have_operation_ids(quality_management_cases) -> None:
    assert not [case for case in quality_management_cases if not case.operation_id]


# Validate generated example responses using the real schema.
def test_quality_management_embedded_json_schemas_validate(
    quality_management_cases,
    quality_management_spec: dict[str, Any],
) -> None:
    validate_response_examples(quality_management_spec, quality_management_cases)


# Create one pytest case per documented endpoint operation.
def pytest_generate_tests(metafunc: Any) -> None:
    if "quality_management_case" in metafunc.fixturenames:
        spec = load_openapi_spec(SPEC_PATH, TITLE)
        cases = build_operation_cases(spec)
        ids = [f"{snake_case(case.operation_id)}[{case.method} {case.path}]" for case in cases]
        metafunc.parametrize("quality_management_case", cases, ids=ids)


# Run the shared contract assertions for a single endpoint case.
@pytest.mark.usefixtures("respx_mock")
def test_quality_management_operation_contract(
    quality_management_client: Any,
    quality_management_spec: dict[str, Any],
    quality_management_case,
    respx_mock: Any,
) -> None:
    run_operation_contract(
        request=get_request_callable(quality_management_client, FIXTURE_NAME),
        spec=quality_management_spec,
        case=quality_management_case,
        respx_mock=respx_mock,
    )


# Explain fixture contract problems with an immediate, direct failure.
def test_quality_management_client_uses_callable_fixture(quality_management_client: Any) -> None:
    assert callable(get_request_callable(quality_management_client, FIXTURE_NAME))
