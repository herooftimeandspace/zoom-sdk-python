"""Schema-driven contract tests for the Zoom Accounts endpoints.

These tests are intentionally lightweight wrappers around the shared helper
module. The endpoint-specific file answers three questions:

1. Which OpenAPI schema file should be used?
2. Which pytest fixture should an implementation provide?
3. Which generated operation cases should be exercised?

Everything else is delegated to `_openapi_contract.py` so the behavior stays
consistent across the whole test suite.
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


SPEC_PATH = Path(__file__).resolve().parent / "schemas" / "accounts" / "Accounts.json"
TITLE = "Accounts"
FIXTURE_NAME = "accounts_client"


#
# This fixture loads the schema document once per test that needs it and gives
# the rest of the file a typed, validated starting point.
@pytest.fixture
def accounts_spec() -> dict[str, Any]:
    return load_openapi_spec(SPEC_PATH, TITLE)


#
# This fixture turns the raw OpenAPI document into a list of concrete pytest
# cases. Each case already contains example path/query/body values and the
# success response schema we expect to validate.
@pytest.fixture
def accounts_cases(accounts_spec: dict[str, Any]):
    cases = build_operation_cases(accounts_spec)
    if not cases:
        raise AssertionError("No operations discovered in Accounts OpenAPI spec.")
    return cases


#
# This is the shallow sanity check for the schema file itself. If this fails,
# the problem is usually a bad path, the wrong schema file, or an unexpected
# schema document shape.
def test_accounts_spec_is_openapi_3(accounts_spec: dict[str, Any]) -> None:
    assert accounts_spec.get("openapi", "").startswith("3.")
    assert accounts_spec.get("info", {}).get("title") == TITLE
    assert "paths" in accounts_spec and isinstance(accounts_spec["paths"], Mapping)


#
# Operation IDs are important because pytest uses them to build readable case
# names and because client implementations often map method names from them.
def test_accounts_operations_have_operation_ids(accounts_cases) -> None:
    assert not [case for case in accounts_cases if not case.operation_id]


#
# This verifies that the schema's documented success responses are internally
# coherent by generating example payloads from the real schema and validating
# them back against that same schema.
def test_accounts_embedded_json_schemas_validate(
    accounts_cases,
    accounts_spec: dict[str, Any],
) -> None:
    validate_response_examples(accounts_spec, accounts_cases)


#
# Pytest calls this hook during collection. We use it to create one test case
# per OpenAPI operation with readable IDs such as:
# `list_accounts[GET /accounts]`.
def pytest_generate_tests(metafunc: Any) -> None:
    if "accounts_case" in metafunc.fixturenames:
        spec = load_openapi_spec(SPEC_PATH, TITLE)
        cases = build_operation_cases(spec)
        ids = [f"{snake_case(case.operation_id)}[{case.method} {case.path}]" for case in cases]
        metafunc.parametrize("accounts_case", cases, ids=ids)


#
# This is the main contract test. It mocks the outbound HTTP call, invokes the
# implementation under test through the fixture callable, and checks both the
# outgoing request shape and the returned response payload.
@pytest.mark.usefixtures("respx_mock")
def test_accounts_operation_contract(
    accounts_client: Any,
    accounts_spec: dict[str, Any],
    accounts_case,
    respx_mock: Any,
) -> None:
    run_operation_contract(
        request=get_request_callable(accounts_client, FIXTURE_NAME),
        spec=accounts_spec,
        case=accounts_case,
        respx_mock=respx_mock,
    )


#
# This final check gives a direct, readable failure if the project-provided
# fixture does not return the callable shape expected by the shared contract
# machinery.
def test_accounts_client_uses_callable_fixture(accounts_client: Any) -> None:
    assert callable(get_request_callable(accounts_client, FIXTURE_NAME))
