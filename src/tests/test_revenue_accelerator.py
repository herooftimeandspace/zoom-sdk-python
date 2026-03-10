"""Schema-driven contract tests for the Zoom Revenue Accelerator endpoints."""

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


SPEC_PATH = Path(__file__).resolve().parent / "schemas" / "business_services" / "Revenue Accelerator.json"
TITLE = "Revenue Accelerator"
FIXTURE_NAME = "revenue_accelerator_client"


# Load the Revenue Accelerator schema document from disk.
@pytest.fixture
def revenue_accelerator_spec() -> dict[str, Any]:
    return load_openapi_spec(SPEC_PATH, TITLE)


# Expand the schema into concrete per-operation test cases.
@pytest.fixture
def revenue_accelerator_cases(revenue_accelerator_spec: dict[str, Any]):
    cases = build_operation_cases(revenue_accelerator_spec)
    if not cases:
        raise AssertionError("No operations discovered in Revenue Accelerator OpenAPI spec.")
    return cases


# Confirm the schema file is the expected OpenAPI document.
def test_revenue_accelerator_spec_is_openapi_3(revenue_accelerator_spec: dict[str, Any]) -> None:
    assert revenue_accelerator_spec.get("openapi", "").startswith("3.")
    assert revenue_accelerator_spec.get("info", {}).get("title") == TITLE
    assert "paths" in revenue_accelerator_spec and isinstance(
        revenue_accelerator_spec["paths"], Mapping
    )


# Operation IDs are required for clear parametrized test names.
def test_revenue_accelerator_operations_have_operation_ids(revenue_accelerator_cases) -> None:
    assert not [case for case in revenue_accelerator_cases if not case.operation_id]


# Validate generated response examples against the actual schema.
def test_revenue_accelerator_embedded_json_schemas_validate(
    revenue_accelerator_cases,
    revenue_accelerator_spec: dict[str, Any],
) -> None:
    validate_response_examples(revenue_accelerator_spec, revenue_accelerator_cases)


# Parametrize the main contract test from the schema's operations.
def pytest_generate_tests(metafunc: Any) -> None:
    if "revenue_accelerator_case" in metafunc.fixturenames:
        spec = load_openapi_spec(SPEC_PATH, TITLE)
        cases = build_operation_cases(spec)
        ids = [f"{snake_case(case.operation_id)}[{case.method} {case.path}]" for case in cases]
        metafunc.parametrize("revenue_accelerator_case", cases, ids=ids)


# Execute the shared request/response contract for one endpoint case.
@pytest.mark.usefixtures("respx_mock")
def test_revenue_accelerator_operation_contract(
    revenue_accelerator_client: Any,
    revenue_accelerator_spec: dict[str, Any],
    revenue_accelerator_case,
    respx_mock: Any,
) -> None:
    run_operation_contract(
        request=get_request_callable(revenue_accelerator_client, FIXTURE_NAME),
        spec=revenue_accelerator_spec,
        case=revenue_accelerator_case,
        respx_mock=respx_mock,
    )


# Make any fixture shape mismatch fail clearly and immediately.
def test_revenue_accelerator_client_uses_callable_fixture(
    revenue_accelerator_client: Any,
) -> None:
    assert callable(get_request_callable(revenue_accelerator_client, FIXTURE_NAME))
