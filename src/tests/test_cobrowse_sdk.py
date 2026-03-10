"""Schema-driven contract tests for the Zoom Cobrowse SDK endpoints."""

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


SPEC_PATH = Path(__file__).resolve().parent / "schemas" / "build_platform" / "Cobrowse SDK.json"
TITLE = "Cobrowse SDK"
FIXTURE_NAME = "cobrowse_sdk_client"


# Load the Cobrowse SDK schema from the repository.
@pytest.fixture
def cobrowse_sdk_spec() -> dict[str, Any]:
    return load_openapi_spec(SPEC_PATH, TITLE)


# Convert schema operations into concrete test inputs and expected outputs.
@pytest.fixture
def cobrowse_sdk_cases(cobrowse_sdk_spec: dict[str, Any]):
    cases = build_operation_cases(cobrowse_sdk_spec)
    if not cases:
        raise AssertionError("No operations discovered in Cobrowse SDK OpenAPI spec.")
    return cases


# Confirm we are working with the expected OpenAPI document.
def test_cobrowse_sdk_spec_is_openapi_3(cobrowse_sdk_spec: dict[str, Any]) -> None:
    assert cobrowse_sdk_spec.get("openapi", "").startswith("3.")
    assert cobrowse_sdk_spec.get("info", {}).get("title") == TITLE
    assert "paths" in cobrowse_sdk_spec and isinstance(cobrowse_sdk_spec["paths"], Mapping)


# Stable operation IDs matter for both readability and debugging.
def test_cobrowse_sdk_operations_have_operation_ids(cobrowse_sdk_cases) -> None:
    assert not [case for case in cobrowse_sdk_cases if not case.operation_id]


# Smoke-test each documented response schema using generated example data.
def test_cobrowse_sdk_embedded_json_schemas_validate(
    cobrowse_sdk_cases,
    cobrowse_sdk_spec: dict[str, Any],
) -> None:
    validate_response_examples(cobrowse_sdk_spec, cobrowse_sdk_cases)


# Parametrize the main contract test from the schema document.
def pytest_generate_tests(metafunc: Any) -> None:
    if "cobrowse_sdk_case" in metafunc.fixturenames:
        spec = load_openapi_spec(SPEC_PATH, TITLE)
        cases = build_operation_cases(spec)
        ids = [f"{snake_case(case.operation_id)}[{case.method} {case.path}]" for case in cases]
        metafunc.parametrize("cobrowse_sdk_case", cases, ids=ids)


# Execute one full request/response contract case for the implementation.
@pytest.mark.usefixtures("respx_mock")
def test_cobrowse_sdk_operation_contract(
    cobrowse_sdk_client: Any,
    cobrowse_sdk_spec: dict[str, Any],
    cobrowse_sdk_case,
    respx_mock: Any,
) -> None:
    run_operation_contract(
        request=get_request_callable(cobrowse_sdk_client, FIXTURE_NAME),
        spec=cobrowse_sdk_spec,
        case=cobrowse_sdk_case,
        respx_mock=respx_mock,
    )


# Make the integration contract obvious to whoever wires up the fixture.
def test_cobrowse_sdk_client_uses_callable_fixture(cobrowse_sdk_client: Any) -> None:
    assert callable(get_request_callable(cobrowse_sdk_client, FIXTURE_NAME))
