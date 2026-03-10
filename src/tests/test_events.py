"""Schema-driven contract tests for the Zoom Events endpoints."""

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


SPEC_PATH = Path(__file__).resolve().parent / "schemas" / "business_services" / "Events.json"
TITLE = "Events"
FIXTURE_NAME = "events_client"


# Load the Events schema document from the checked-in test assets.
@pytest.fixture
def events_spec() -> dict[str, Any]:
    return load_openapi_spec(SPEC_PATH, TITLE)


# Convert the schema into concrete test inputs and expected outputs.
@pytest.fixture
def events_cases(events_spec: dict[str, Any]):
    cases = build_operation_cases(events_spec)
    if not cases:
        raise AssertionError("No operations discovered in Events OpenAPI spec.")
    return cases


# Sanity-check the schema file before deeper assertions run.
def test_events_spec_is_openapi_3(events_spec: dict[str, Any]) -> None:
    assert events_spec.get("openapi", "").startswith("3.")
    assert events_spec.get("info", {}).get("title") == TITLE
    assert "paths" in events_spec and isinstance(events_spec["paths"], Mapping)


# We rely on operation IDs for readable pytest case names.
def test_events_operations_have_operation_ids(events_cases) -> None:
    assert not [case for case in events_cases if not case.operation_id]


# Validate generated example responses against the real schema.
def test_events_embedded_json_schemas_validate(events_cases, events_spec: dict[str, Any]) -> None:
    validate_response_examples(events_spec, events_cases)


# Build one parametrized pytest case for each documented operation.
def pytest_generate_tests(metafunc: Any) -> None:
    if "events_case" in metafunc.fixturenames:
        spec = load_openapi_spec(SPEC_PATH, TITLE)
        cases = build_operation_cases(spec)
        ids = [f"{snake_case(case.operation_id)}[{case.method} {case.path}]" for case in cases]
        metafunc.parametrize("events_case", cases, ids=ids)


# Run the shared contract logic for a single Events endpoint case.
@pytest.mark.usefixtures("respx_mock")
def test_events_operation_contract(
    events_client: Any,
    events_spec: dict[str, Any],
    events_case,
    respx_mock: Any,
) -> None:
    run_operation_contract(
        request=get_request_callable(events_client, FIXTURE_NAME),
        spec=events_spec,
        case=events_case,
        respx_mock=respx_mock,
    )


# Make the expected fixture shape obvious to anyone wiring this suite up.
def test_events_client_uses_callable_fixture(events_client: Any) -> None:
    assert callable(get_request_callable(events_client, FIXTURE_NAME))
