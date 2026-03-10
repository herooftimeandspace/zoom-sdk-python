"""Schema-driven contract tests for the Zoom AI Companion endpoints.

Future readers should think of this file as a thin adapter between one schema
 file and the shared OpenAPI contract runner.
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


SPEC_PATH = Path(__file__).resolve().parent / "schemas" / "workplace" / "AI Companion.json"
TITLE = "AI Companion"
FIXTURE_NAME = "ai_companion_client"


# Load the AI Companion schema so the rest of the file has one canonical source
# of truth for paths, parameters, and response shapes.
@pytest.fixture
def ai_companion_spec() -> dict[str, Any]:
    return load_openapi_spec(SPEC_PATH, TITLE)


# Convert the raw schema into concrete operation cases with example inputs.
@pytest.fixture
def ai_companion_cases(ai_companion_spec: dict[str, Any]):
    cases = build_operation_cases(ai_companion_spec)
    if not cases:
        raise AssertionError("No operations discovered in AI Companion OpenAPI spec.")
    return cases


# Confirm that we loaded the right kind of document before doing deeper checks.
def test_ai_companion_spec_is_openapi_3(ai_companion_spec: dict[str, Any]) -> None:
    assert ai_companion_spec.get("openapi", "").startswith("3.")
    assert ai_companion_spec.get("info", {}).get("title") == TITLE
    assert "paths" in ai_companion_spec and isinstance(ai_companion_spec["paths"], Mapping)


# Operation IDs are required so parametrized tests remain understandable.
def test_ai_companion_operations_have_operation_ids(ai_companion_cases) -> None:
    assert not [case for case in ai_companion_cases if not case.operation_id]


# Validate generated example responses against the real schema definitions.
def test_ai_companion_embedded_json_schemas_validate(
    ai_companion_cases,
    ai_companion_spec: dict[str, Any],
) -> None:
    validate_response_examples(ai_companion_spec, ai_companion_cases)


# Generate one pytest case per operation declared in the schema.
def pytest_generate_tests(metafunc: Any) -> None:
    if "ai_companion_case" in metafunc.fixturenames:
        spec = load_openapi_spec(SPEC_PATH, TITLE)
        cases = build_operation_cases(spec)
        ids = [f"{snake_case(case.operation_id)}[{case.method} {case.path}]" for case in cases]
        metafunc.parametrize("ai_companion_case", cases, ids=ids)


# Exercise the implementation under test against one generated operation case.
@pytest.mark.usefixtures("respx_mock")
def test_ai_companion_operation_contract(
    ai_companion_client: Any,
    ai_companion_spec: dict[str, Any],
    ai_companion_case,
    respx_mock: Any,
) -> None:
    run_operation_contract(
        request=get_request_callable(ai_companion_client, FIXTURE_NAME),
        spec=ai_companion_spec,
        case=ai_companion_case,
        respx_mock=respx_mock,
    )


# Fail fast with a clear message if the fixture contract is wrong.
def test_ai_companion_client_uses_callable_fixture(ai_companion_client: Any) -> None:
    assert callable(get_request_callable(ai_companion_client, FIXTURE_NAME))
