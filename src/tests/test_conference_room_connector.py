"""Schema-driven contract tests for the Zoom Conference Room Connector endpoints."""

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


SPEC_PATH = Path(__file__).resolve().parent / "schemas" / "workplace" / "Conference Room Connector.json"
TITLE = "Conference Room Connector"
FIXTURE_NAME = "conference_room_connector_client"


# Load the endpoint schema file used as the contract source of truth.
@pytest.fixture
def conference_room_connector_spec() -> dict[str, Any]:
    return load_openapi_spec(SPEC_PATH, TITLE)


# Expand the schema into concrete per-operation test cases.
@pytest.fixture
def conference_room_connector_cases(conference_room_connector_spec: dict[str, Any]):
    cases = build_operation_cases(conference_room_connector_spec)
    if not cases:
        raise AssertionError("No operations discovered in Conference Room Connector OpenAPI spec.")
    return cases


# Basic check that the loaded schema document is the one we expect.
def test_conference_room_connector_spec_is_openapi_3(
    conference_room_connector_spec: dict[str, Any],
) -> None:
    assert conference_room_connector_spec.get("openapi", "").startswith("3.")
    assert conference_room_connector_spec.get("info", {}).get("title") == TITLE
    assert "paths" in conference_room_connector_spec and isinstance(
        conference_room_connector_spec["paths"], Mapping
    )


# Require operation IDs so test case names are useful when failures happen.
def test_conference_room_connector_operations_have_operation_ids(
    conference_room_connector_cases,
) -> None:
    assert not [case for case in conference_room_connector_cases if not case.operation_id]


# Validate generated example responses against the real schema definitions.
def test_conference_room_connector_embedded_json_schemas_validate(
    conference_room_connector_cases,
    conference_room_connector_spec: dict[str, Any],
) -> None:
    validate_response_examples(conference_room_connector_spec, conference_room_connector_cases)


# Dynamically parametrize the main contract test from discovered schema operations.
def pytest_generate_tests(metafunc: Any) -> None:
    if "conference_room_connector_case" in metafunc.fixturenames:
        spec = load_openapi_spec(SPEC_PATH, TITLE)
        cases = build_operation_cases(spec)
        ids = [f"{snake_case(case.operation_id)}[{case.method} {case.path}]" for case in cases]
        metafunc.parametrize("conference_room_connector_case", cases, ids=ids)


# Run the shared request/response contract for one generated operation case.
@pytest.mark.usefixtures("respx_mock")
def test_conference_room_connector_operation_contract(
    conference_room_connector_client: Any,
    conference_room_connector_spec: dict[str, Any],
    conference_room_connector_case,
    respx_mock: Any,
) -> None:
    run_operation_contract(
        request=get_request_callable(conference_room_connector_client, FIXTURE_NAME),
        spec=conference_room_connector_spec,
        case=conference_room_connector_case,
        respx_mock=respx_mock,
    )


# Explicitly document the expected fixture shape for implementers.
def test_conference_room_connector_client_uses_callable_fixture(
    conference_room_connector_client: Any,
) -> None:
    assert callable(get_request_callable(conference_room_connector_client, FIXTURE_NAME))
