"""Schema-driven contract tests for the Zoom Team Chat endpoints."""

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


SPEC_PATH = Path(__file__).resolve().parent / "schemas" / "workplace" / "Team Chat.json"
TITLE = "Team Chat"
FIXTURE_NAME = "team_chat_client"


# Load the Team Chat schema from disk.
@pytest.fixture
def team_chat_spec() -> dict[str, Any]:
    return load_openapi_spec(SPEC_PATH, TITLE)


# Convert the schema into concrete per-operation test cases.
@pytest.fixture
def team_chat_cases(team_chat_spec: dict[str, Any]):
    cases = build_operation_cases(team_chat_spec)
    if not cases:
        raise AssertionError("No operations discovered in Team Chat OpenAPI spec.")
    return cases


# Verify that the schema file is the expected OpenAPI document.
def test_team_chat_spec_is_openapi_3(team_chat_spec: dict[str, Any]) -> None:
    assert team_chat_spec.get("openapi", "").startswith("3.")
    assert team_chat_spec.get("info", {}).get("title") == TITLE
    assert "paths" in team_chat_spec and isinstance(team_chat_spec["paths"], Mapping)


# Operation IDs are used to keep case names and failures readable.
def test_team_chat_operations_have_operation_ids(team_chat_cases) -> None:
    assert not [case for case in team_chat_cases if not case.operation_id]


# Validate generated response examples against the real Team Chat schema.
def test_team_chat_embedded_json_schemas_validate(
    team_chat_cases,
    team_chat_spec: dict[str, Any],
) -> None:
    validate_response_examples(team_chat_spec, team_chat_cases)


# Generate one pytest case per documented Team Chat operation.
def pytest_generate_tests(metafunc: Any) -> None:
    if "team_chat_case" in metafunc.fixturenames:
        spec = load_openapi_spec(SPEC_PATH, TITLE)
        cases = build_operation_cases(spec)
        ids = [f"{snake_case(case.operation_id)}[{case.method} {case.path}]" for case in cases]
        metafunc.parametrize("team_chat_case", cases, ids=ids)


# Run the shared request/response contract for a Team Chat endpoint case.
@pytest.mark.usefixtures("respx_mock")
def test_team_chat_operation_contract(
    team_chat_client: Any,
    team_chat_spec: dict[str, Any],
    team_chat_case,
    respx_mock: Any,
) -> None:
    run_operation_contract(
        request=get_request_callable(team_chat_client, FIXTURE_NAME),
        spec=team_chat_spec,
        case=team_chat_case,
        respx_mock=respx_mock,
    )


# Keep fixture integration errors direct and easy to understand.
def test_team_chat_client_uses_callable_fixture(team_chat_client: Any) -> None:
    assert callable(get_request_callable(team_chat_client, FIXTURE_NAME))
