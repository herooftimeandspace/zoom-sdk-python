"""Schema-driven contract tests for the Zoom Meetings endpoints."""

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


SPEC_PATH = Path(__file__).resolve().parent / "schemas" / "workplace" / "Meetings.json"
TITLE = "Meetings"
FIXTURE_NAME = "meetings_client"


# Load the Meetings schema file.
@pytest.fixture
def meetings_spec() -> dict[str, Any]:
    return load_openapi_spec(SPEC_PATH, TITLE)


# Generate reusable per-operation test cases from the schema.
@pytest.fixture
def meetings_cases(meetings_spec: dict[str, Any]):
    cases = build_operation_cases(meetings_spec)
    if not cases:
        raise AssertionError("No operations discovered in Meetings OpenAPI spec.")
    return cases


# Check that the schema file is structurally what we expect.
def test_meetings_spec_is_openapi_3(meetings_spec: dict[str, Any]) -> None:
    assert meetings_spec.get("openapi", "").startswith("3.")
    assert meetings_spec.get("info", {}).get("title") == TITLE
    assert "paths" in meetings_spec and isinstance(meetings_spec["paths"], Mapping)


# Require operation IDs so parametrized failures remain understandable.
def test_meetings_operations_have_operation_ids(meetings_cases) -> None:
    assert not [case for case in meetings_cases if not case.operation_id]


# Validate generated example response instances against the actual schema.
def test_meetings_embedded_json_schemas_validate(
    meetings_cases,
    meetings_spec: dict[str, Any],
) -> None:
    validate_response_examples(meetings_spec, meetings_cases)


# Create one parametrized test case per discovered schema operation.
def pytest_generate_tests(metafunc: Any) -> None:
    if "meetings_case" in metafunc.fixturenames:
        spec = load_openapi_spec(SPEC_PATH, TITLE)
        cases = build_operation_cases(spec)
        ids = [f"{snake_case(case.operation_id)}[{case.method} {case.path}]" for case in cases]
        metafunc.parametrize("meetings_case", cases, ids=ids)


# Run the shared HTTP contract checks for a single Meetings operation.
@pytest.mark.usefixtures("respx_mock")
def test_meetings_operation_contract(
    meetings_client: Any,
    meetings_spec: dict[str, Any],
    meetings_case,
    respx_mock: Any,
) -> None:
    run_operation_contract(
        request=get_request_callable(meetings_client, FIXTURE_NAME),
        spec=meetings_spec,
        case=meetings_case,
        respx_mock=respx_mock,
    )


# Give a direct and readable fixture-contract failure when needed.
def test_meetings_client_uses_callable_fixture(meetings_client: Any) -> None:
    assert callable(get_request_callable(meetings_client, FIXTURE_NAME))
