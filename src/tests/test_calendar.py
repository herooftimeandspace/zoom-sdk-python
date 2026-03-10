"""Schema-driven contract tests for the Zoom Calendar endpoints.

This file is designed for readers who want to know which schema is being used,
which fixture must be supplied by the implementation, and how the generated
cases are fed into the shared contract runner.
"""

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


SPEC_PATH = Path(__file__).resolve().parent / "schemas" / "workplace" / "Calendar.json"
TITLE = "Calendar"
FIXTURE_NAME = "calendar_client"


# Load the Calendar OpenAPI document from disk.
@pytest.fixture
def calendar_spec() -> dict[str, Any]:
    return load_openapi_spec(SPEC_PATH, TITLE)


# Precompute generated operation cases so multiple tests can reuse them.
@pytest.fixture
def calendar_cases(calendar_spec: dict[str, Any]):
    cases = build_operation_cases(calendar_spec)
    if not cases:
        raise AssertionError("No operations discovered in Calendar OpenAPI spec.")
    return cases


# Sanity-check that the schema file is the expected OpenAPI document.
def test_calendar_spec_is_openapi_3(calendar_spec: dict[str, Any]) -> None:
    assert calendar_spec.get("openapi", "").startswith("3.")
    assert calendar_spec.get("info", {}).get("title") == TITLE
    assert "paths" in calendar_spec and isinstance(calendar_spec["paths"], Mapping)


# Require operation IDs so parametrized tests remain readable and stable.
def test_calendar_operations_have_operation_ids(calendar_cases) -> None:
    assert not [case for case in calendar_cases if not case.operation_id]


# Use the real schema to generate and validate example response instances.
def test_calendar_embedded_json_schemas_validate(
    calendar_cases,
    calendar_spec: dict[str, Any],
) -> None:
    validate_response_examples(calendar_spec, calendar_cases)


# Build one parametrized pytest case per schema operation.
def pytest_generate_tests(metafunc: Any) -> None:
    if "calendar_case" in metafunc.fixturenames:
        spec = load_openapi_spec(SPEC_PATH, TITLE)
        cases = build_operation_cases(spec)
        ids = [f"{snake_case(case.operation_id)}[{case.method} {case.path}]" for case in cases]
        metafunc.parametrize("calendar_case", cases, ids=ids)


# Main contract test: mock HTTP, call the implementation, verify request and
# response behavior against the schema-derived case.
@pytest.mark.usefixtures("respx_mock")
def test_calendar_operation_contract(
    calendar_client: Any,
    calendar_spec: dict[str, Any],
    calendar_case,
    respx_mock: Any,
) -> None:
    run_operation_contract(
        request=get_request_callable(calendar_client, FIXTURE_NAME),
        spec=calendar_spec,
        case=calendar_case,
        respx_mock=respx_mock,
    )


# Make the fixture contract explicit for implementers.
def test_calendar_client_uses_callable_fixture(calendar_client: Any) -> None:
    assert callable(get_request_callable(calendar_client, FIXTURE_NAME))
