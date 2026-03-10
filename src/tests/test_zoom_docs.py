"""Schema-driven contract tests for the Zoom Docs endpoints."""

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


SPEC_PATH = Path(__file__).resolve().parent / "schemas" / "workplace" / "Zoom Docs.json"
TITLE = "Zoom Docs"
FIXTURE_NAME = "zoom_docs_client"


# Load the Zoom Docs schema from the checked-in test assets.
@pytest.fixture
def zoom_docs_spec() -> dict[str, Any]:
    return load_openapi_spec(SPEC_PATH, TITLE)


# Convert the schema into concrete per-operation test cases.
@pytest.fixture
def zoom_docs_cases(zoom_docs_spec: dict[str, Any]):
    cases = build_operation_cases(zoom_docs_spec)
    if not cases:
        raise AssertionError("No operations discovered in Zoom Docs OpenAPI spec.")
    return cases


# Confirm that the schema file is the expected OpenAPI document.
def test_zoom_docs_spec_is_openapi_3(zoom_docs_spec: dict[str, Any]) -> None:
    assert zoom_docs_spec.get("openapi", "").startswith("3.")
    assert zoom_docs_spec.get("info", {}).get("title") == TITLE
    assert "paths" in zoom_docs_spec and isinstance(zoom_docs_spec["paths"], Mapping)


# Operation IDs are required so parametrized test names stay readable.
def test_zoom_docs_operations_have_operation_ids(zoom_docs_cases) -> None:
    assert not [case for case in zoom_docs_cases if not case.operation_id]


# Validate generated example responses against the real schema.
def test_zoom_docs_embedded_json_schemas_validate(
    zoom_docs_cases,
    zoom_docs_spec: dict[str, Any],
) -> None:
    validate_response_examples(zoom_docs_spec, zoom_docs_cases)


# Dynamically parametrize the main contract test from schema operations.
def pytest_generate_tests(metafunc: Any) -> None:
    if "zoom_docs_case" in metafunc.fixturenames:
        spec = load_openapi_spec(SPEC_PATH, TITLE)
        cases = build_operation_cases(spec)
        ids = [f"{snake_case(case.operation_id)}[{case.method} {case.path}]" for case in cases]
        metafunc.parametrize("zoom_docs_case", cases, ids=ids)


# Execute the shared request/response contract for one Zoom Docs endpoint case.
@pytest.mark.usefixtures("respx_mock")
def test_zoom_docs_operation_contract(
    zoom_docs_client: Any,
    zoom_docs_spec: dict[str, Any],
    zoom_docs_case,
    respx_mock: Any,
) -> None:
    run_operation_contract(
        request=get_request_callable(zoom_docs_client, FIXTURE_NAME),
        spec=zoom_docs_spec,
        case=zoom_docs_case,
        respx_mock=respx_mock,
    )


# Keep fixture integration failures direct and understandable.
def test_zoom_docs_client_uses_callable_fixture(zoom_docs_client: Any) -> None:
    assert callable(get_request_callable(zoom_docs_client, FIXTURE_NAME))
