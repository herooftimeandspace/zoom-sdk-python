"""Schema-driven contract tests for the Zoom Clips endpoints.

The purpose of comments in these thin wrappers is to explain the role of each
pytest hook and fixture, not to repeat the detailed OpenAPI logic already
documented in `_openapi_contract.py`.
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


SPEC_PATH = Path(__file__).resolve().parent / "schemas" / "workplace" / "Clips.json"
TITLE = "Clips"
FIXTURE_NAME = "clips_client"


# Read the Clips schema document from the checked-in test assets.
@pytest.fixture
def clips_spec() -> dict[str, Any]:
    return load_openapi_spec(SPEC_PATH, TITLE)


# Turn the raw schema into concrete, reusable test cases.
@pytest.fixture
def clips_cases(clips_spec: dict[str, Any]):
    cases = build_operation_cases(clips_spec)
    if not cases:
        raise AssertionError("No operations discovered in Clips OpenAPI spec.")
    return cases


# Basic correctness check for the schema file itself.
def test_clips_spec_is_openapi_3(clips_spec: dict[str, Any]) -> None:
    assert clips_spec.get("openapi", "").startswith("3.")
    assert clips_spec.get("info", {}).get("title") == TITLE
    assert "paths" in clips_spec and isinstance(clips_spec["paths"], Mapping)


# Missing operation IDs make the contract suite much harder to debug.
def test_clips_operations_have_operation_ids(clips_cases) -> None:
    assert not [case for case in clips_cases if not case.operation_id]


# Confirm that example responses generated from the schema validate cleanly.
def test_clips_embedded_json_schemas_validate(
    clips_cases,
    clips_spec: dict[str, Any],
) -> None:
    validate_response_examples(clips_spec, clips_cases)


# Dynamically create pytest cases from the schema contents.
def pytest_generate_tests(metafunc: Any) -> None:
    if "clips_case" in metafunc.fixturenames:
        spec = load_openapi_spec(SPEC_PATH, TITLE)
        cases = build_operation_cases(spec)
        ids = [f"{snake_case(case.operation_id)}[{case.method} {case.path}]" for case in cases]
        metafunc.parametrize("clips_case", cases, ids=ids)


# Exercise one endpoint case through the shared runner.
@pytest.mark.usefixtures("respx_mock")
def test_clips_operation_contract(
    clips_client: Any,
    clips_spec: dict[str, Any],
    clips_case,
    respx_mock: Any,
) -> None:
    run_operation_contract(
        request=get_request_callable(clips_client, FIXTURE_NAME),
        spec=clips_spec,
        case=clips_case,
        respx_mock=respx_mock,
    )


# Ensure the fixture exposed by the implementation has the expected callable form.
def test_clips_client_uses_callable_fixture(clips_client: Any) -> None:
    assert callable(get_request_callable(clips_client, FIXTURE_NAME))
