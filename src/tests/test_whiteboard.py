"""Schema-driven contract tests for the Zoom Whiteboard endpoints."""

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


SPEC_PATH = Path(__file__).resolve().parent / "schemas" / "workplace" / "Whiteboard.json"
TITLE = "Whiteboard"
FIXTURE_NAME = "whiteboard_client"


# Load the Whiteboard schema document from disk.
@pytest.fixture
def whiteboard_spec() -> dict[str, Any]:
    return load_openapi_spec(SPEC_PATH, TITLE)


# Convert the schema into concrete, reusable operation cases.
@pytest.fixture
def whiteboard_cases(whiteboard_spec: dict[str, Any]):
    cases = build_operation_cases(whiteboard_spec)
    if not cases:
        raise AssertionError("No operations discovered in Whiteboard OpenAPI spec.")
    return cases


# Confirm that we are working with the expected OpenAPI document.
def test_whiteboard_spec_is_openapi_3(whiteboard_spec: dict[str, Any]) -> None:
    assert whiteboard_spec.get("openapi", "").startswith("3.")
    assert whiteboard_spec.get("info", {}).get("title") == TITLE
    assert "paths" in whiteboard_spec and isinstance(whiteboard_spec["paths"], Mapping)


# Operation IDs are required to keep parametrized case names useful.
def test_whiteboard_operations_have_operation_ids(whiteboard_cases) -> None:
    assert not [case for case in whiteboard_cases if not case.operation_id]


# Validate example response instances generated from the real schema.
def test_whiteboard_embedded_json_schemas_validate(
    whiteboard_cases,
    whiteboard_spec: dict[str, Any],
) -> None:
    validate_response_examples(whiteboard_spec, whiteboard_cases)


# Dynamically create one pytest case per documented Whiteboard operation.
def pytest_generate_tests(metafunc: Any) -> None:
    if "whiteboard_case" in metafunc.fixturenames:
        spec = load_openapi_spec(SPEC_PATH, TITLE)
        cases = build_operation_cases(spec)
        ids = [f"{snake_case(case.operation_id)}[{case.method} {case.path}]" for case in cases]
        metafunc.parametrize("whiteboard_case", cases, ids=ids)


# Execute the shared request/response contract for one Whiteboard case.
@pytest.mark.usefixtures("respx_mock")
def test_whiteboard_operation_contract(
    whiteboard_client: Any,
    whiteboard_spec: dict[str, Any],
    whiteboard_case,
    respx_mock: Any,
) -> None:
    run_operation_contract(
        request=get_request_callable(whiteboard_client, FIXTURE_NAME),
        spec=whiteboard_spec,
        case=whiteboard_case,
        respx_mock=respx_mock,
    )


# Make the expected fixture shape obvious to future maintainers.
def test_whiteboard_client_uses_callable_fixture(whiteboard_client: Any) -> None:
    assert callable(get_request_callable(whiteboard_client, FIXTURE_NAME))
