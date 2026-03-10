"""Schema-driven contract tests for the Zoom Tasks endpoints."""

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


SPEC_PATH = Path(__file__).resolve().parent / "schemas" / "workplace" / "Tasks.json"
TITLE = "Tasks"
FIXTURE_NAME = "tasks_client"


# Load the Tasks schema document from the checked-in assets.
@pytest.fixture
def tasks_spec() -> dict[str, Any]:
    return load_openapi_spec(SPEC_PATH, TITLE)


# Build one concrete case per documented Tasks operation.
@pytest.fixture
def tasks_cases(tasks_spec: dict[str, Any]):
    cases = build_operation_cases(tasks_spec)
    if not cases:
        raise AssertionError("No operations discovered in Tasks OpenAPI spec.")
    return cases


# Confirm the schema file itself is the expected OpenAPI document.
def test_tasks_spec_is_openapi_3(tasks_spec: dict[str, Any]) -> None:
    assert tasks_spec.get("openapi", "").startswith("3.")
    assert tasks_spec.get("info", {}).get("title") == TITLE
    assert "paths" in tasks_spec and isinstance(tasks_spec["paths"], Mapping)


# Operation IDs are required for understandable parametrized case names.
def test_tasks_operations_have_operation_ids(tasks_cases) -> None:
    assert not [case for case in tasks_cases if not case.operation_id]


# Validate schema-generated example responses against the actual schema.
def test_tasks_embedded_json_schemas_validate(tasks_cases, tasks_spec: dict[str, Any]) -> None:
    validate_response_examples(tasks_spec, tasks_cases)


# Generate one pytest case per documented Tasks endpoint operation.
def pytest_generate_tests(metafunc: Any) -> None:
    if "tasks_case" in metafunc.fixturenames:
        spec = load_openapi_spec(SPEC_PATH, TITLE)
        cases = build_operation_cases(spec)
        ids = [f"{snake_case(case.operation_id)}[{case.method} {case.path}]" for case in cases]
        metafunc.parametrize("tasks_case", cases, ids=ids)


# Execute the shared contract logic for one Tasks endpoint case.
@pytest.mark.usefixtures("respx_mock")
def test_tasks_operation_contract(
    tasks_client: Any,
    tasks_spec: dict[str, Any],
    tasks_case,
    respx_mock: Any,
) -> None:
    run_operation_contract(
        request=get_request_callable(tasks_client, FIXTURE_NAME),
        spec=tasks_spec,
        case=tasks_case,
        respx_mock=respx_mock,
    )


# Fail directly if the project fixture does not return the required callable.
def test_tasks_client_uses_callable_fixture(tasks_client: Any) -> None:
    assert callable(get_request_callable(tasks_client, FIXTURE_NAME))
