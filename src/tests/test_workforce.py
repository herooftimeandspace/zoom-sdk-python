"""Schema-driven contract tests for the Zoom Workforce Management endpoints."""

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


SPEC_PATH = Path(__file__).resolve().parent / "schemas" / "business_services" / "Workforce Management.json"
TITLE = "Workforce Management"
FIXTURE_NAME = "workforce_client"


# Load the Workforce Management schema from the repository.
@pytest.fixture
def workforce_spec() -> dict[str, Any]:
    return load_openapi_spec(SPEC_PATH, TITLE)


# Build one concrete test case per documented operation.
@pytest.fixture
def workforce_cases(workforce_spec: dict[str, Any]):
    cases = build_operation_cases(workforce_spec)
    if not cases:
        raise AssertionError("No operations discovered in Workforce Management OpenAPI spec.")
    return cases


# Verify that the schema file itself is the expected OpenAPI document.
def test_workforce_spec_is_openapi_3(workforce_spec: dict[str, Any]) -> None:
    assert workforce_spec.get("openapi", "").startswith("3.")
    assert workforce_spec.get("info", {}).get("title") == TITLE
    assert "paths" in workforce_spec and isinstance(workforce_spec["paths"], Mapping)


# Operation IDs are required for readable parametrized failures.
def test_workforce_operations_have_operation_ids(workforce_cases) -> None:
    assert not [case for case in workforce_cases if not case.operation_id]


# Validate generated example responses against the actual schema.
def test_workforce_embedded_json_schemas_validate(
    workforce_cases,
    workforce_spec: dict[str, Any],
) -> None:
    validate_response_examples(workforce_spec, workforce_cases)


# Generate one pytest case per documented Workforce operation.
def pytest_generate_tests(metafunc: Any) -> None:
    if "workforce_case" in metafunc.fixturenames:
        spec = load_openapi_spec(SPEC_PATH, TITLE)
        cases = build_operation_cases(spec)
        ids = [f"{snake_case(case.operation_id)}[{case.method} {case.path}]" for case in cases]
        metafunc.parametrize("workforce_case", cases, ids=ids)


# Execute the shared request/response contract for one Workforce endpoint case.
@pytest.mark.usefixtures("respx_mock")
def test_workforce_operation_contract(
    workforce_client: Any,
    workforce_spec: dict[str, Any],
    workforce_case,
    respx_mock: Any,
) -> None:
    run_operation_contract(
        request=get_request_callable(workforce_client, FIXTURE_NAME),
        spec=workforce_spec,
        case=workforce_case,
        respx_mock=respx_mock,
    )


# Fail clearly if the project fixture does not expose the required callable.
def test_workforce_client_uses_callable_fixture(workforce_client: Any) -> None:
    assert callable(get_request_callable(workforce_client, FIXTURE_NAME))
