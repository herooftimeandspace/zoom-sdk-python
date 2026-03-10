"""Schema-driven contract tests for the Zoom Scheduler endpoints."""

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


SPEC_PATH = Path(__file__).resolve().parent / "schemas" / "workplace" / "Scheduler.json"
TITLE = "Scheduler"
FIXTURE_NAME = "scheduler_client"


# Load the Scheduler schema from the checked-in schema assets.
@pytest.fixture
def scheduler_spec() -> dict[str, Any]:
    return load_openapi_spec(SPEC_PATH, TITLE)


# Convert the schema into concrete operation cases for reuse across tests.
@pytest.fixture
def scheduler_cases(scheduler_spec: dict[str, Any]):
    cases = build_operation_cases(scheduler_spec)
    if not cases:
        raise AssertionError("No operations discovered in Scheduler OpenAPI spec.")
    return cases


# Confirm the schema file itself is structurally what we expect.
def test_scheduler_spec_is_openapi_3(scheduler_spec: dict[str, Any]) -> None:
    assert scheduler_spec.get("openapi", "").startswith("3.")
    assert scheduler_spec.get("info", {}).get("title") == TITLE
    assert "paths" in scheduler_spec and isinstance(scheduler_spec["paths"], Mapping)


# Operation IDs keep parametrized failure output readable.
def test_scheduler_operations_have_operation_ids(scheduler_cases) -> None:
    assert not [case for case in scheduler_cases if not case.operation_id]


# Validate example response payloads generated from the real schema.
def test_scheduler_embedded_json_schemas_validate(
    scheduler_cases,
    scheduler_spec: dict[str, Any],
) -> None:
    validate_response_examples(scheduler_spec, scheduler_cases)


# Create one test case per documented Scheduler operation.
def pytest_generate_tests(metafunc: Any) -> None:
    if "scheduler_case" in metafunc.fixturenames:
        spec = load_openapi_spec(SPEC_PATH, TITLE)
        cases = build_operation_cases(spec)
        ids = [f"{snake_case(case.operation_id)}[{case.method} {case.path}]" for case in cases]
        metafunc.parametrize("scheduler_case", cases, ids=ids)


# Run the shared contract helper for one Scheduler endpoint case.
@pytest.mark.usefixtures("respx_mock")
def test_scheduler_operation_contract(
    scheduler_client: Any,
    scheduler_spec: dict[str, Any],
    scheduler_case,
    respx_mock: Any,
) -> None:
    run_operation_contract(
        request=get_request_callable(scheduler_client, FIXTURE_NAME),
        spec=scheduler_spec,
        case=scheduler_case,
        respx_mock=respx_mock,
    )


# Make the required fixture shape explicit and easy to diagnose.
def test_scheduler_client_uses_callable_fixture(scheduler_client: Any) -> None:
    assert callable(get_request_callable(scheduler_client, FIXTURE_NAME))
