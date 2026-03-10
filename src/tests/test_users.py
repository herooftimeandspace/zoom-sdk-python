"""Schema-driven contract tests for the Zoom Users endpoints."""

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


SPEC_PATH = Path(__file__).resolve().parent / "schemas" / "accounts" / "Users.json"
TITLE = "Users"
FIXTURE_NAME = "users_client"


# Load the Users schema file used by this suite.
@pytest.fixture
def users_spec() -> dict[str, Any]:
    return load_openapi_spec(SPEC_PATH, TITLE)


# Build schema-derived operation cases for reuse across tests.
@pytest.fixture
def users_cases(users_spec: dict[str, Any]):
    cases = build_operation_cases(users_spec)
    if not cases:
        raise AssertionError("No operations discovered in Users OpenAPI spec.")
    return cases


# Confirm the schema file itself is the expected OpenAPI document.
def test_users_spec_is_openapi_3(users_spec: dict[str, Any]) -> None:
    assert users_spec.get("openapi", "").startswith("3.")
    assert users_spec.get("info", {}).get("title") == TITLE
    assert "paths" in users_spec and isinstance(users_spec["paths"], Mapping)


# Operation IDs are required for readable parametrized failures.
def test_users_operations_have_operation_ids(users_cases) -> None:
    assert not [case for case in users_cases if not case.operation_id]


# Validate generated example responses against the real Users schema.
def test_users_embedded_json_schemas_validate(users_cases, users_spec: dict[str, Any]) -> None:
    validate_response_examples(users_spec, users_cases)


# Generate one pytest case per documented Users operation.
def pytest_generate_tests(metafunc: Any) -> None:
    if "users_case" in metafunc.fixturenames:
        spec = load_openapi_spec(SPEC_PATH, TITLE)
        cases = build_operation_cases(spec)
        ids = [f"{snake_case(case.operation_id)}[{case.method} {case.path}]" for case in cases]
        metafunc.parametrize("users_case", cases, ids=ids)


# Execute the shared request/response contract for one Users endpoint case.
@pytest.mark.usefixtures("respx_mock")
def test_users_operation_contract(
    users_client: Any,
    users_spec: dict[str, Any],
    users_case,
    respx_mock: Any,
) -> None:
    run_operation_contract(
        request=get_request_callable(users_client, FIXTURE_NAME),
        spec=users_spec,
        case=users_case,
        respx_mock=respx_mock,
    )


# Make the fixture integration contract obvious to future maintainers.
def test_users_client_uses_callable_fixture(users_client: Any) -> None:
    assert callable(get_request_callable(users_client, FIXTURE_NAME))
