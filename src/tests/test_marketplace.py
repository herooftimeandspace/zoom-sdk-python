"""Schema-driven contract tests for the Zoom Marketplace endpoints."""

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


SPEC_PATH = Path(__file__).resolve().parent / "schemas" / "marketplace" / "Marketplace.json"
TITLE = "Marketplace"
FIXTURE_NAME = "marketplace_client"


# Load the Marketplace schema document from disk.
@pytest.fixture
def marketplace_spec() -> dict[str, Any]:
    return load_openapi_spec(SPEC_PATH, TITLE)


# Convert the schema into concrete operation cases.
@pytest.fixture
def marketplace_cases(marketplace_spec: dict[str, Any]):
    cases = build_operation_cases(marketplace_spec)
    if not cases:
        raise AssertionError("No operations discovered in Marketplace OpenAPI spec.")
    return cases


# Sanity-check that we loaded the expected OpenAPI document.
def test_marketplace_spec_is_openapi_3(marketplace_spec: dict[str, Any]) -> None:
    assert marketplace_spec.get("openapi", "").startswith("3.")
    assert marketplace_spec.get("info", {}).get("title") == TITLE
    assert "paths" in marketplace_spec and isinstance(marketplace_spec["paths"], Mapping)


# Operation IDs are required for readable parametrized case names.
def test_marketplace_operations_have_operation_ids(marketplace_cases) -> None:
    assert not [case for case in marketplace_cases if not case.operation_id]


# Validate generated example response instances against the real schema.
def test_marketplace_embedded_json_schemas_validate(
    marketplace_cases,
    marketplace_spec: dict[str, Any],
) -> None:
    validate_response_examples(marketplace_spec, marketplace_cases)


# Create one pytest case per documented Marketplace operation.
def pytest_generate_tests(metafunc: Any) -> None:
    if "marketplace_case" in metafunc.fixturenames:
        spec = load_openapi_spec(SPEC_PATH, TITLE)
        cases = build_operation_cases(spec)
        ids = [f"{snake_case(case.operation_id)}[{case.method} {case.path}]" for case in cases]
        metafunc.parametrize("marketplace_case", cases, ids=ids)


# Run the shared request/response contract for one Marketplace endpoint case.
@pytest.mark.usefixtures("respx_mock")
def test_marketplace_operation_contract(
    marketplace_client: Any,
    marketplace_spec: dict[str, Any],
    marketplace_case,
    respx_mock: Any,
) -> None:
    run_operation_contract(
        request=get_request_callable(marketplace_client, FIXTURE_NAME),
        spec=marketplace_spec,
        case=marketplace_case,
        respx_mock=respx_mock,
    )


# Make the required fixture shape explicit and easy to diagnose.
def test_marketplace_client_uses_callable_fixture(marketplace_client: Any) -> None:
    assert callable(get_request_callable(marketplace_client, FIXTURE_NAME))
