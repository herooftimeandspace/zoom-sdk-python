"""Schema-driven contract tests for the Zoom Mail endpoints."""

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


SPEC_PATH = Path(__file__).resolve().parent / "schemas" / "workplace" / "Mail.json"
TITLE = "Mail"
FIXTURE_NAME = "mail_client"


# Load the Mail schema so the tests can derive behavior from documentation.
@pytest.fixture
def mail_spec() -> dict[str, Any]:
    return load_openapi_spec(SPEC_PATH, TITLE)


# Precompute a case object for every documented operation.
@pytest.fixture
def mail_cases(mail_spec: dict[str, Any]):
    cases = build_operation_cases(mail_spec)
    if not cases:
        raise AssertionError("No operations discovered in Mail OpenAPI spec.")
    return cases


# Verify that the schema file itself is the expected OpenAPI document.
def test_mail_spec_is_openapi_3(mail_spec: dict[str, Any]) -> None:
    assert mail_spec.get("openapi", "").startswith("3.")
    assert mail_spec.get("info", {}).get("title") == TITLE
    assert "paths" in mail_spec and isinstance(mail_spec["paths"], Mapping)


# Missing operation IDs make failures much harder to interpret.
def test_mail_operations_have_operation_ids(mail_cases) -> None:
    assert not [case for case in mail_cases if not case.operation_id]


# Validate schema-derived example responses against the real schema.
def test_mail_embedded_json_schemas_validate(mail_cases, mail_spec: dict[str, Any]) -> None:
    validate_response_examples(mail_spec, mail_cases)


# Dynamically create one pytest test case per schema operation.
def pytest_generate_tests(metafunc: Any) -> None:
    if "mail_case" in metafunc.fixturenames:
        spec = load_openapi_spec(SPEC_PATH, TITLE)
        cases = build_operation_cases(spec)
        ids = [f"{snake_case(case.operation_id)}[{case.method} {case.path}]" for case in cases]
        metafunc.parametrize("mail_case", cases, ids=ids)


# Execute the main request/response contract for one Mail endpoint case.
@pytest.mark.usefixtures("respx_mock")
def test_mail_operation_contract(
    mail_client: Any,
    mail_spec: dict[str, Any],
    mail_case,
    respx_mock: Any,
) -> None:
    run_operation_contract(
        request=get_request_callable(mail_client, FIXTURE_NAME),
        spec=mail_spec,
        case=mail_case,
        respx_mock=respx_mock,
    )


# Clarify the exact fixture shape expected from the implementation under test.
def test_mail_client_uses_callable_fixture(mail_client: Any) -> None:
    assert callable(get_request_callable(mail_client, FIXTURE_NAME))
