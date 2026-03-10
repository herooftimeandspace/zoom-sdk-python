"""Schema-driven contract tests for the Zoom Phone endpoints."""

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


SPEC_PATH = Path(__file__).resolve().parent / "schemas" / "workplace" / "Phone.json"
TITLE = "Phone"
FIXTURE_NAME = "phone_client"


# Load the Phone schema from the checked-in schema fixtures.
@pytest.fixture
def phone_spec() -> dict[str, Any]:
    return load_openapi_spec(SPEC_PATH, TITLE)


# Create concrete operation cases derived from the schema.
@pytest.fixture
def phone_cases(phone_spec: dict[str, Any]):
    cases = build_operation_cases(phone_spec)
    if not cases:
        raise AssertionError("No operations discovered in Phone OpenAPI spec.")
    return cases


# Ensure the schema file itself is the expected OpenAPI document.
def test_phone_spec_is_openapi_3(phone_spec: dict[str, Any]) -> None:
    assert phone_spec.get("openapi", "").startswith("3.")
    assert phone_spec.get("info", {}).get("title") == TITLE
    assert "paths" in phone_spec and isinstance(phone_spec["paths"], Mapping)


# Operation IDs are required for readable parametrized failures.
def test_phone_operations_have_operation_ids(phone_cases) -> None:
    assert not [case for case in phone_cases if not case.operation_id]


# Validate generated example response instances against the real schema.
def test_phone_embedded_json_schemas_validate(phone_cases, phone_spec: dict[str, Any]) -> None:
    validate_response_examples(phone_spec, phone_cases)


# Dynamically parametrize the main contract test from the schema.
def pytest_generate_tests(metafunc: Any) -> None:
    if "phone_case" in metafunc.fixturenames:
        spec = load_openapi_spec(SPEC_PATH, TITLE)
        cases = build_operation_cases(spec)
        ids = [f"{snake_case(case.operation_id)}[{case.method} {case.path}]" for case in cases]
        metafunc.parametrize("phone_case", cases, ids=ids)


# Execute the main request/response contract for one Phone endpoint case.
@pytest.mark.usefixtures("respx_mock")
def test_phone_operation_contract(
    phone_client: Any,
    phone_spec: dict[str, Any],
    phone_case,
    respx_mock: Any,
) -> None:
    run_operation_contract(
        request=get_request_callable(phone_client, FIXTURE_NAME),
        spec=phone_spec,
        case=phone_case,
        respx_mock=respx_mock,
    )


# Make the fixture contract explicit to the implementation author.
def test_phone_client_uses_callable_fixture(phone_client: Any) -> None:
    assert callable(get_request_callable(phone_client, FIXTURE_NAME))
