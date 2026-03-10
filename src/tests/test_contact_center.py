"""Schema-driven contract tests for the Zoom Contact Center endpoints."""

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


SPEC_PATH = Path(__file__).resolve().parent / "schemas" / "business_services" / "Contact Center.json"
TITLE = "Contact Center"
FIXTURE_NAME = "contact_center_client"


# Load the Contact Center schema from the repository.
@pytest.fixture
def contact_center_spec() -> dict[str, Any]:
    return load_openapi_spec(SPEC_PATH, TITLE)


# Build one reusable operation case per documented endpoint.
@pytest.fixture
def contact_center_cases(contact_center_spec: dict[str, Any]):
    cases = build_operation_cases(contact_center_spec)
    if not cases:
        raise AssertionError("No operations discovered in Contact Center OpenAPI spec.")
    return cases


# Verify that the schema file itself looks like the expected OpenAPI document.
def test_contact_center_spec_is_openapi_3(contact_center_spec: dict[str, Any]) -> None:
    assert contact_center_spec.get("openapi", "").startswith("3.")
    assert contact_center_spec.get("info", {}).get("title") == TITLE
    assert "paths" in contact_center_spec and isinstance(contact_center_spec["paths"], Mapping)


# Operation IDs keep parametrized case names debuggable.
def test_contact_center_operations_have_operation_ids(contact_center_cases) -> None:
    assert not [case for case in contact_center_cases if not case.operation_id]


# Generate example response data from the real schema and validate it.
def test_contact_center_embedded_json_schemas_validate(
    contact_center_cases,
    contact_center_spec: dict[str, Any],
) -> None:
    validate_response_examples(contact_center_spec, contact_center_cases)


# Ask pytest to create one test instance per schema operation.
def pytest_generate_tests(metafunc: Any) -> None:
    if "contact_center_case" in metafunc.fixturenames:
        spec = load_openapi_spec(SPEC_PATH, TITLE)
        cases = build_operation_cases(spec)
        ids = [f"{snake_case(case.operation_id)}[{case.method} {case.path}]" for case in cases]
        metafunc.parametrize("contact_center_case", cases, ids=ids)


# Main contract test: use the shared helper to mock HTTP and verify behavior.
@pytest.mark.usefixtures("respx_mock")
def test_contact_center_operation_contract(
    contact_center_client: Any,
    contact_center_spec: dict[str, Any],
    contact_center_case,
    respx_mock: Any,
) -> None:
    run_operation_contract(
        request=get_request_callable(contact_center_client, FIXTURE_NAME),
        spec=contact_center_spec,
        case=contact_center_case,
        respx_mock=respx_mock,
    )


# Fail clearly if the provided fixture is not the required callable.
def test_contact_center_client_uses_callable_fixture(contact_center_client: Any) -> None:
    assert callable(get_request_callable(contact_center_client, FIXTURE_NAME))
