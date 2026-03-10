"""Schema-driven contract tests for the Zoom QSS endpoints."""

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


SPEC_PATH = Path(__file__).resolve().parent / "schemas" / "accounts" / "QSS.json"
TITLE = "QSS"
FIXTURE_NAME = "qss_client"


# Load the QSS schema document.
@pytest.fixture
def qss_spec() -> dict[str, Any]:
    return load_openapi_spec(SPEC_PATH, TITLE)


# Turn the schema into ready-to-run operation cases.
@pytest.fixture
def qss_cases(qss_spec: dict[str, Any]):
    cases = build_operation_cases(qss_spec)
    if not cases:
        raise AssertionError("No operations discovered in QSS OpenAPI spec.")
    return cases


# Confirm the schema file itself is the expected OpenAPI document.
def test_qss_spec_is_openapi_3(qss_spec: dict[str, Any]) -> None:
    assert qss_spec.get("openapi", "").startswith("3.")
    assert qss_spec.get("info", {}).get("title") == TITLE
    assert "paths" in qss_spec and isinstance(qss_spec["paths"], Mapping)


# Operation IDs are required so case names stay understandable.
def test_qss_operations_have_operation_ids(qss_cases) -> None:
    assert not [case for case in qss_cases if not case.operation_id]


# Validate example response payloads generated from the actual schema.
def test_qss_embedded_json_schemas_validate(qss_cases, qss_spec: dict[str, Any]) -> None:
    validate_response_examples(qss_spec, qss_cases)


# Generate a separate pytest case for every schema operation.
def pytest_generate_tests(metafunc: Any) -> None:
    if "qss_case" in metafunc.fixturenames:
        spec = load_openapi_spec(SPEC_PATH, TITLE)
        cases = build_operation_cases(spec)
        ids = [f"{snake_case(case.operation_id)}[{case.method} {case.path}]" for case in cases]
        metafunc.parametrize("qss_case", cases, ids=ids)


# Execute the shared contract logic for one QSS endpoint case.
@pytest.mark.usefixtures("respx_mock")
def test_qss_operation_contract(
    qss_client: Any,
    qss_spec: dict[str, Any],
    qss_case,
    respx_mock: Any,
) -> None:
    run_operation_contract(
        request=get_request_callable(qss_client, FIXTURE_NAME),
        spec=qss_spec,
        case=qss_case,
        respx_mock=respx_mock,
    )


# Provide a direct failure if the fixture is not callable as required.
def test_qss_client_uses_callable_fixture(qss_client: Any) -> None:
    assert callable(get_request_callable(qss_client, FIXTURE_NAME))
