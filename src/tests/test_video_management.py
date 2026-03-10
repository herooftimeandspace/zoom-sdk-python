"""Schema-driven contract tests for the Zoom Video Management endpoints."""

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


SPEC_PATH = Path(__file__).resolve().parent / "schemas" / "business_services" / "Video Management.json"
TITLE = "Video Management"
FIXTURE_NAME = "video_management_client"


# Load the Video Management schema document.
@pytest.fixture
def video_management_spec() -> dict[str, Any]:
    return load_openapi_spec(SPEC_PATH, TITLE)


# Build concrete operation cases derived from that schema.
@pytest.fixture
def video_management_cases(video_management_spec: dict[str, Any]):
    cases = build_operation_cases(video_management_spec)
    if not cases:
        raise AssertionError("No operations discovered in Video Management OpenAPI spec.")
    return cases


# Basic schema sanity check before deeper contract assertions.
def test_video_management_spec_is_openapi_3(video_management_spec: dict[str, Any]) -> None:
    assert video_management_spec.get("openapi", "").startswith("3.")
    assert video_management_spec.get("info", {}).get("title") == TITLE
    assert "paths" in video_management_spec and isinstance(video_management_spec["paths"], Mapping)


# Operation IDs are required for readable parametrized output.
def test_video_management_operations_have_operation_ids(video_management_cases) -> None:
    assert not [case for case in video_management_cases if not case.operation_id]


# Validate generated example responses against the real schema definitions.
def test_video_management_embedded_json_schemas_validate(
    video_management_cases,
    video_management_spec: dict[str, Any],
) -> None:
    validate_response_examples(video_management_spec, video_management_cases)


# Generate one pytest case per documented Video Management operation.
def pytest_generate_tests(metafunc: Any) -> None:
    if "video_management_case" in metafunc.fixturenames:
        spec = load_openapi_spec(SPEC_PATH, TITLE)
        cases = build_operation_cases(spec)
        ids = [f"{snake_case(case.operation_id)}[{case.method} {case.path}]" for case in cases]
        metafunc.parametrize("video_management_case", cases, ids=ids)


# Execute the shared request/response contract for one endpoint case.
@pytest.mark.usefixtures("respx_mock")
def test_video_management_operation_contract(
    video_management_client: Any,
    video_management_spec: dict[str, Any],
    video_management_case,
    respx_mock: Any,
) -> None:
    run_operation_contract(
        request=get_request_callable(video_management_client, FIXTURE_NAME),
        spec=video_management_spec,
        case=video_management_case,
        respx_mock=respx_mock,
    )


# Fail clearly if the implementation fixture is not callable as expected.
def test_video_management_client_uses_callable_fixture(video_management_client: Any) -> None:
    assert callable(get_request_callable(video_management_client, FIXTURE_NAME))
