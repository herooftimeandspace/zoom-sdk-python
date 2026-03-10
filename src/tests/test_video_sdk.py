"""Schema-driven contract tests for the Zoom Video SDK endpoints."""

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


SPEC_PATH = Path(__file__).resolve().parent / "schemas" / "build_platform" / "Video SDK.json"
TITLE = "Video SDK"
FIXTURE_NAME = "video_sdk_client"


# Load the Video SDK schema from the checked-in test assets.
@pytest.fixture
def video_sdk_spec() -> dict[str, Any]:
    return load_openapi_spec(SPEC_PATH, TITLE)


# Convert the schema into concrete operation cases.
@pytest.fixture
def video_sdk_cases(video_sdk_spec: dict[str, Any]):
    cases = build_operation_cases(video_sdk_spec)
    if not cases:
        raise AssertionError("No operations discovered in Video SDK OpenAPI spec.")
    return cases


# Verify that the schema file itself is the expected OpenAPI document.
def test_video_sdk_spec_is_openapi_3(video_sdk_spec: dict[str, Any]) -> None:
    assert video_sdk_spec.get("openapi", "").startswith("3.")
    assert video_sdk_spec.get("info", {}).get("title") == TITLE
    assert "paths" in video_sdk_spec and isinstance(video_sdk_spec["paths"], Mapping)


# Operation IDs are required for helpful parametrized output.
def test_video_sdk_operations_have_operation_ids(video_sdk_cases) -> None:
    assert not [case for case in video_sdk_cases if not case.operation_id]


# Validate example responses generated from the real Video SDK schema.
def test_video_sdk_embedded_json_schemas_validate(
    video_sdk_cases,
    video_sdk_spec: dict[str, Any],
) -> None:
    validate_response_examples(video_sdk_spec, video_sdk_cases)


# Generate a pytest case per documented Video SDK operation.
def pytest_generate_tests(metafunc: Any) -> None:
    if "video_sdk_case" in metafunc.fixturenames:
        spec = load_openapi_spec(SPEC_PATH, TITLE)
        cases = build_operation_cases(spec)
        ids = [f"{snake_case(case.operation_id)}[{case.method} {case.path}]" for case in cases]
        metafunc.parametrize("video_sdk_case", cases, ids=ids)


# Run the shared request/response contract for a single Video SDK case.
@pytest.mark.usefixtures("respx_mock")
def test_video_sdk_operation_contract(
    video_sdk_client: Any,
    video_sdk_spec: dict[str, Any],
    video_sdk_case,
    respx_mock: Any,
) -> None:
    run_operation_contract(
        request=get_request_callable(video_sdk_client, FIXTURE_NAME),
        spec=video_sdk_spec,
        case=video_sdk_case,
        respx_mock=respx_mock,
    )


# Make the expected fixture callable contract explicit.
def test_video_sdk_client_uses_callable_fixture(video_sdk_client: Any) -> None:
    assert callable(get_request_callable(video_sdk_client, FIXTURE_NAME))
