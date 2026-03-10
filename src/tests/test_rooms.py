"""Schema-driven contract tests for the Zoom Rooms endpoints."""

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


SPEC_PATH = Path(__file__).resolve().parent / "schemas" / "workplace" / "Rooms.json"
TITLE = "Rooms"
FIXTURE_NAME = "rooms_client"


# Load the Rooms schema file from the repository.
@pytest.fixture
def rooms_spec() -> dict[str, Any]:
    return load_openapi_spec(SPEC_PATH, TITLE)


# Build reusable operation cases from the schema document.
@pytest.fixture
def rooms_cases(rooms_spec: dict[str, Any]):
    cases = build_operation_cases(rooms_spec)
    if not cases:
        raise AssertionError("No operations discovered in Rooms OpenAPI spec.")
    return cases


# Sanity-check the schema file itself.
def test_rooms_spec_is_openapi_3(rooms_spec: dict[str, Any]) -> None:
    assert rooms_spec.get("openapi", "").startswith("3.")
    assert rooms_spec.get("info", {}).get("title") == TITLE
    assert "paths" in rooms_spec and isinstance(rooms_spec["paths"], Mapping)


# Stable operation IDs are required for readable parametrized output.
def test_rooms_operations_have_operation_ids(rooms_cases) -> None:
    assert not [case for case in rooms_cases if not case.operation_id]


# Validate generated example response payloads against the schema.
def test_rooms_embedded_json_schemas_validate(rooms_cases, rooms_spec: dict[str, Any]) -> None:
    validate_response_examples(rooms_spec, rooms_cases)


# Generate one pytest case per documented Rooms operation.
def pytest_generate_tests(metafunc: Any) -> None:
    if "rooms_case" in metafunc.fixturenames:
        spec = load_openapi_spec(SPEC_PATH, TITLE)
        cases = build_operation_cases(spec)
        ids = [f"{snake_case(case.operation_id)}[{case.method} {case.path}]" for case in cases]
        metafunc.parametrize("rooms_case", cases, ids=ids)


# Execute the shared request/response contract for a Rooms endpoint case.
@pytest.mark.usefixtures("respx_mock")
def test_rooms_operation_contract(
    rooms_client: Any,
    rooms_spec: dict[str, Any],
    rooms_case,
    respx_mock: Any,
) -> None:
    run_operation_contract(
        request=get_request_callable(rooms_client, FIXTURE_NAME),
        spec=rooms_spec,
        case=rooms_case,
        respx_mock=respx_mock,
    )


# Keep fixture integration failures direct and obvious.
def test_rooms_client_uses_callable_fixture(rooms_client: Any) -> None:
    assert callable(get_request_callable(rooms_client, FIXTURE_NAME))
