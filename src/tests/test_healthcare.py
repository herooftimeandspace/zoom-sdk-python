"""Schema-driven contract tests for the Zoom Healthcare endpoints."""

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


SPEC_PATH = Path(__file__).resolve().parent / "schemas" / "business_services" / "Healthcare.json"
TITLE = "Healthcare"
FIXTURE_NAME = "healthcare_client"


# Load the Healthcare schema used by this contract suite.
@pytest.fixture
def healthcare_spec() -> dict[str, Any]:
    return load_openapi_spec(SPEC_PATH, TITLE)


# Transform the schema into a list of reusable operation test cases.
@pytest.fixture
def healthcare_cases(healthcare_spec: dict[str, Any]):
    cases = build_operation_cases(healthcare_spec)
    if not cases:
        raise AssertionError("No operations discovered in Healthcare OpenAPI spec.")
    return cases


# Confirm we are pointed at the right schema file and format.
def test_healthcare_spec_is_openapi_3(healthcare_spec: dict[str, Any]) -> None:
    assert healthcare_spec.get("openapi", "").startswith("3.")
    assert healthcare_spec.get("info", {}).get("title") == TITLE
    assert "paths" in healthcare_spec and isinstance(healthcare_spec["paths"], Mapping)


# Stable operation IDs are required for understandable parametrization.
def test_healthcare_operations_have_operation_ids(healthcare_cases) -> None:
    assert not [case for case in healthcare_cases if not case.operation_id]


# Ensure schema-derived example responses are valid according to the schema.
def test_healthcare_embedded_json_schemas_validate(
    healthcare_cases,
    healthcare_spec: dict[str, Any],
) -> None:
    validate_response_examples(healthcare_spec, healthcare_cases)


# Generate one case per schema operation at collection time.
def pytest_generate_tests(metafunc: Any) -> None:
    if "healthcare_case" in metafunc.fixturenames:
        spec = load_openapi_spec(SPEC_PATH, TITLE)
        cases = build_operation_cases(spec)
        ids = [f"{snake_case(case.operation_id)}[{case.method} {case.path}]" for case in cases]
        metafunc.parametrize("healthcare_case", cases, ids=ids)


# Execute the shared request/response contract for one Healthcare operation.
@pytest.mark.usefixtures("respx_mock")
def test_healthcare_operation_contract(
    healthcare_client: Any,
    healthcare_spec: dict[str, Any],
    healthcare_case,
    respx_mock: Any,
) -> None:
    run_operation_contract(
        request=get_request_callable(healthcare_client, FIXTURE_NAME),
        spec=healthcare_spec,
        case=healthcare_case,
        respx_mock=respx_mock,
    )


# Give an explicit error if the project fixture is wired incorrectly.
def test_healthcare_client_uses_callable_fixture(healthcare_client: Any) -> None:
    assert callable(get_request_callable(healthcare_client, FIXTURE_NAME))
