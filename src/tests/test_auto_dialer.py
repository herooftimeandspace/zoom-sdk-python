"""Schema-driven contract tests for the Zoom Auto Dialer endpoints.

This file intentionally contains only endpoint-specific configuration plus a
small amount of explanatory structure. The heavy lifting happens in the shared
OpenAPI contract helper.
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


SPEC_PATH = Path(__file__).resolve().parent / "schemas" / "business_services" / "Auto Dialer.json"
TITLE = "Auto Dialer"
FIXTURE_NAME = "auto_dialer_client"


# Load the Auto Dialer schema from the repository so tests can derive their
# cases directly from the documented contract.
@pytest.fixture
def auto_dialer_spec() -> dict[str, Any]:
    return load_openapi_spec(SPEC_PATH, TITLE)


# Expand the schema into one prepared test case per discovered endpoint.
@pytest.fixture
def auto_dialer_cases(auto_dialer_spec: dict[str, Any]):
    cases = build_operation_cases(auto_dialer_spec)
    if not cases:
        raise AssertionError("No operations discovered in Auto Dialer OpenAPI spec.")
    return cases


# Basic schema sanity check before deeper behavioral assertions.
def test_auto_dialer_spec_is_openapi_3(auto_dialer_spec: dict[str, Any]) -> None:
    assert auto_dialer_spec.get("openapi", "").startswith("3.")
    assert auto_dialer_spec.get("info", {}).get("title") == TITLE
    assert "paths" in auto_dialer_spec and isinstance(auto_dialer_spec["paths"], Mapping)


# Require every operation to have a stable identifier for readable test output.
def test_auto_dialer_operations_have_operation_ids(auto_dialer_cases) -> None:
    assert not [case for case in auto_dialer_cases if not case.operation_id]


# Validate example response instances against the real schema definitions.
def test_auto_dialer_embedded_json_schemas_validate(
    auto_dialer_cases,
    auto_dialer_spec: dict[str, Any],
) -> None:
    validate_response_examples(auto_dialer_spec, auto_dialer_cases)


# Parametrize pytest dynamically from the schema's declared operations.
def pytest_generate_tests(metafunc: Any) -> None:
    if "auto_dialer_case" in metafunc.fixturenames:
        spec = load_openapi_spec(SPEC_PATH, TITLE)
        cases = build_operation_cases(spec)
        ids = [f"{snake_case(case.operation_id)}[{case.method} {case.path}]" for case in cases]
        metafunc.parametrize("auto_dialer_case", cases, ids=ids)


# Run the shared request/response contract against one generated endpoint case.
@pytest.mark.usefixtures("respx_mock")
def test_auto_dialer_operation_contract(
    auto_dialer_client: Any,
    auto_dialer_spec: dict[str, Any],
    auto_dialer_case,
    respx_mock: Any,
) -> None:
    run_operation_contract(
        request=get_request_callable(auto_dialer_client, FIXTURE_NAME),
        spec=auto_dialer_spec,
        case=auto_dialer_case,
        respx_mock=respx_mock,
    )


# Give an explicit failure if the fixture is not the expected callable.
def test_auto_dialer_client_uses_callable_fixture(auto_dialer_client: Any) -> None:
    assert callable(get_request_callable(auto_dialer_client, FIXTURE_NAME))
