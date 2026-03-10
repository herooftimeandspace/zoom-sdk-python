"""Schema-driven contract tests for the Zoom SCIM 2.0 endpoints.

SCIM is the one suite that also forwards an explicit `Accept` header because
the API commonly documents `application/scim+json` media types.
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


SPEC_PATH = Path(__file__).resolve().parent / "schemas" / "accounts" / "SCIM2.json"
TITLE = "SCIM2"
FIXTURE_NAME = "scim_client"


# Load the SCIM schema file from the repository.
@pytest.fixture
def scim_spec() -> dict[str, Any]:
    return load_openapi_spec(SPEC_PATH, TITLE)


# Convert the schema into reusable per-operation test cases.
@pytest.fixture
def scim_cases(scim_spec: dict[str, Any]):
    cases = build_operation_cases(scim_spec)
    if not cases:
        raise AssertionError("No operations discovered in SCIM2 OpenAPI spec.")
    return cases


# Sanity-check the schema file before deeper behavior checks.
def test_scim_spec_is_openapi_3(scim_spec: dict[str, Any]) -> None:
    assert scim_spec.get("openapi", "").startswith("3.")
    assert scim_spec.get("info", {}).get("title") == TITLE
    assert "paths" in scim_spec and isinstance(scim_spec["paths"], Mapping)


# Operation IDs are required so parametrized test names stay readable.
def test_scim_operations_have_operation_ids(scim_cases) -> None:
    assert not [case for case in scim_cases if not case.operation_id]


# Validate example SCIM responses generated from the real schema.
def test_scim_embedded_json_schemas_validate(scim_cases, scim_spec: dict[str, Any]) -> None:
    validate_response_examples(scim_spec, scim_cases)


# Create one pytest case per documented SCIM operation.
def pytest_generate_tests(metafunc: Any) -> None:
    if "scim_case" in metafunc.fixturenames:
        spec = load_openapi_spec(SPEC_PATH, TITLE)
        cases = build_operation_cases(spec)
        ids = [f"{snake_case(case.operation_id)}[{case.method} {case.path}]" for case in cases]
        metafunc.parametrize("scim_case", cases, ids=ids)


# Run the shared request/response contract while also asserting that the SCIM
# media-type header is passed through correctly.
@pytest.mark.usefixtures("respx_mock")
def test_scim_operation_contract(
    scim_client: Any,
    scim_spec: dict[str, Any],
    scim_case,
    respx_mock: Any,
) -> None:
    run_operation_contract(
        request=get_request_callable(scim_client, FIXTURE_NAME),
        spec=scim_spec,
        case=scim_case,
        respx_mock=respx_mock,
        request_headers={"accept": "application/scim+json"},
    )


# Make the expected fixture shape explicit for future integrators.
def test_scim_client_uses_callable_fixture(scim_client: Any) -> None:
    assert callable(get_request_callable(scim_client, FIXTURE_NAME))
