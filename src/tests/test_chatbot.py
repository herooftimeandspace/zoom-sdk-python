"""Schema-driven contract tests for the Zoom Chatbot endpoints.

All endpoint-specific files follow the same broad pattern so readers can move
between them without re-learning the structure every time.
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


SPEC_PATH = Path(__file__).resolve().parent / "schemas" / "workplace" / "Chatbot.json"
TITLE = "Chatbot"
FIXTURE_NAME = "chatbot_client"


# Load the Chatbot schema once per dependent test.
@pytest.fixture
def chatbot_spec() -> dict[str, Any]:
    return load_openapi_spec(SPEC_PATH, TITLE)


# Derive concrete operation cases from the schema's paths and methods.
@pytest.fixture
def chatbot_cases(chatbot_spec: dict[str, Any]):
    cases = build_operation_cases(chatbot_spec)
    if not cases:
        raise AssertionError("No operations discovered in Chatbot OpenAPI spec.")
    return cases


# Confirm the loaded document is the expected schema file.
def test_chatbot_spec_is_openapi_3(chatbot_spec: dict[str, Any]) -> None:
    assert chatbot_spec.get("openapi", "").startswith("3.")
    assert chatbot_spec.get("info", {}).get("title") == TITLE
    assert "paths" in chatbot_spec and isinstance(chatbot_spec["paths"], Mapping)


# Operation IDs are used to create understandable parametrized case names.
def test_chatbot_operations_have_operation_ids(chatbot_cases) -> None:
    assert not [case for case in chatbot_cases if not case.operation_id]


# Validate generated example responses against the real schema.
def test_chatbot_embedded_json_schemas_validate(
    chatbot_cases,
    chatbot_spec: dict[str, Any],
) -> None:
    validate_response_examples(chatbot_spec, chatbot_cases)


# Ask pytest to create one test instance per schema operation.
def pytest_generate_tests(metafunc: Any) -> None:
    if "chatbot_case" in metafunc.fixturenames:
        spec = load_openapi_spec(SPEC_PATH, TITLE)
        cases = build_operation_cases(spec)
        ids = [f"{snake_case(case.operation_id)}[{case.method} {case.path}]" for case in cases]
        metafunc.parametrize("chatbot_case", cases, ids=ids)


# Run the shared contract logic for a single schema-derived operation case.
@pytest.mark.usefixtures("respx_mock")
def test_chatbot_operation_contract(
    chatbot_client: Any,
    chatbot_spec: dict[str, Any],
    chatbot_case,
    respx_mock: Any,
) -> None:
    run_operation_contract(
        request=get_request_callable(chatbot_client, FIXTURE_NAME),
        spec=chatbot_spec,
        case=chatbot_case,
        respx_mock=respx_mock,
    )


# Provide a direct fixture-contract failure message if integration is wrong.
def test_chatbot_client_uses_callable_fixture(chatbot_client: Any) -> None:
    assert callable(get_request_callable(chatbot_client, FIXTURE_NAME))
