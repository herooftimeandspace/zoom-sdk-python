"""Broad read-only live integration coverage for `zoom_sdk`.

This module intentionally exercises only `GET` endpoints against a live account.
Every call records its response payload to a markdown artifact, and `4xx`
responses are documented but do not fail the suite yet.
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

import httpx
import pytest

from zoom_sdk import ZoomClient
from zoom_sdk.config import load_dotenv

REQUIRED_ENV_VARS = (
    "ZOOM_ACCOUNT_ID",
    "ZOOM_CLIENT_ID",
    "ZOOM_CLIENT_SECRET",
)
REPO_ROOT = Path(__file__).resolve().parents[3]
REPO_DOTENV = REPO_ROOT / ".env"
REPORT_PATH = (
    REPO_ROOT
    / ".pytest_cache"
    / "integration-read-only"
    / "read-only-integration-report.md"
)


IntegrationState = dict[str, Any]
PathParamsResolver = Callable[[IntegrationState], Mapping[str, Any]]
ParamsResolver = Callable[[IntegrationState], Mapping[str, Any]]
StateUpdater = Callable[[dict[str, Any], IntegrationState], None]
ExecutionMode = Literal["validated_request", "raw_get_schema_ambiguous"]
SCHEMA_AMBIGUITY_REASON = "oneOf overlap in bundled schema"


class CaseSkip(RuntimeError):
    """Raised when a case cannot run because live prerequisite data is missing."""


@dataclass(frozen=True)
class EndpointCase:
    """One read-only endpoint integration case."""

    key: str
    path: str
    params: Mapping[str, Any] | None = None
    params_resolver: ParamsResolver | None = None
    path_params_resolver: PathParamsResolver | None = None
    state_updater: StateUpdater | None = None
    execution_mode: ExecutionMode = "validated_request"


@dataclass
class RecordedCall:
    """One recorded integration endpoint outcome."""

    case_key: str
    method: str
    path: str
    outcome: str
    status_code: int | None
    params: dict[str, Any] | None
    path_params: dict[str, Any] | None
    response_body: Any | None = None
    message: str | None = None


@dataclass
class ResponseRecorder:
    """Collect integration outcomes and write a markdown report."""

    report_path: Path
    records: list[RecordedCall] = field(default_factory=list)

    def record_success(
        self,
        *,
        case_key: str,
        path: str,
        params: Mapping[str, Any] | None,
        path_params: Mapping[str, Any] | None,
        status_code: int,
        response_body: Any,
    ) -> None:
        self.records.append(
            RecordedCall(
                case_key=case_key,
                method="GET",
                path=path,
                outcome="success_2xx",
                status_code=status_code,
                params=dict(params) if params is not None else None,
                path_params=dict(path_params) if path_params is not None else None,
                response_body=response_body,
            )
        )

    def record_schema_ambiguous_success(
        self,
        *,
        case_key: str,
        path: str,
        params: Mapping[str, Any] | None,
        path_params: Mapping[str, Any] | None,
        status_code: int,
        response_body: Any,
        reason: str,
    ) -> None:
        self.records.append(
            RecordedCall(
                case_key=case_key,
                method="GET",
                path=path,
                outcome="success_2xx_schema_ambiguous",
                status_code=status_code,
                params=dict(params) if params is not None else None,
                path_params=dict(path_params) if path_params is not None else None,
                response_body=response_body,
                message=reason,
            )
        )

    def record_client_error(
        self,
        *,
        case_key: str,
        path: str,
        params: Mapping[str, Any] | None,
        path_params: Mapping[str, Any] | None,
        status_code: int,
        response_body: Any,
        message: str,
    ) -> None:
        self.records.append(
            RecordedCall(
                case_key=case_key,
                method="GET",
                path=path,
                outcome="client_error_4xx",
                status_code=status_code,
                params=dict(params) if params is not None else None,
                path_params=dict(path_params) if path_params is not None else None,
                response_body=response_body,
                message=message,
            )
        )

    def record_skip(
        self,
        *,
        case_key: str,
        path: str,
        message: str,
    ) -> None:
        self.records.append(
            RecordedCall(
                case_key=case_key,
                method="GET",
                path=path,
                outcome="skipped",
                status_code=None,
                params=None,
                path_params=None,
                message=message,
            )
        )

    def record_failure(
        self,
        *,
        case_key: str,
        path: str,
        params: Mapping[str, Any] | None,
        path_params: Mapping[str, Any] | None,
        status_code: int | None,
        response_body: Any | None,
        message: str,
    ) -> None:
        self.records.append(
            RecordedCall(
                case_key=case_key,
                method="GET",
                path=path,
                outcome="failed",
                status_code=status_code,
                params=dict(params) if params is not None else None,
                path_params=dict(path_params) if path_params is not None else None,
                response_body=response_body,
                message=message,
            )
        )

    def write_markdown(self) -> None:
        """Write the full integration report to `.pytest_cache` as markdown."""

        self.report_path.parent.mkdir(parents=True, exist_ok=True)

        two_xx = sum(record.outcome == "success_2xx" for record in self.records)
        two_xx_schema_ambiguous = sum(
            record.outcome == "success_2xx_schema_ambiguous"
            for record in self.records
        )
        four_xx = sum(record.outcome == "client_error_4xx" for record in self.records)
        skipped = sum(record.outcome == "skipped" for record in self.records)
        failed = sum(record.outcome == "failed" for record in self.records)
        total_calls = two_xx + two_xx_schema_ambiguous + four_xx + failed

        lines: list[str] = [
            "# Read-Only Integration Report",
            "",
            f"Generated at: `{datetime.now(UTC).isoformat()}`",
            "",
            "## Summary",
            "",
            f"- Total calls: `{total_calls}`",
            f"- 2xx responses: `{two_xx}`",
            f"- 2xx schema-ambiguous responses: `{two_xx_schema_ambiguous}`",
            f"- 4xx responses: `{four_xx}`",
            f"- Skipped cases: `{skipped}`",
            f"- Failed cases: `{failed}`",
            "",
            "## All Response Logs",
            "",
        ]

        if not self.records:
            lines.append("No integration cases were recorded.")
            lines.append("")

        for record in self.records:
            lines.extend(
                [
                    f"### {record.case_key}",
                    "",
                    f"- Method: `{record.method}`",
                    f"- Path: `{record.path}`",
                    f"- Outcome: `{record.outcome}`",
                    f"- Status: `{record.status_code if record.status_code is not None else 'n/a'}`",
                ]
            )
            if record.params is not None:
                lines.append(f"- Query params: `{record.params}`")
            if record.path_params is not None:
                lines.append(f"- Path params: `{record.path_params}`")
            if record.message:
                lines.append(f"- Message: `{record.message}`")
            lines.append("")

            if record.response_body is not None:
                lines.extend(
                    [
                        "```json",
                        _serialize_json(record.response_body),
                        "```",
                        "",
                    ]
                )

        lines.extend(["## Documented 4xx Errors", ""])

        client_errors = [
            record for record in self.records if record.outcome == "client_error_4xx"
        ]
        if not client_errors:
            lines.append("No 4xx responses were observed.")
            lines.append("")
        else:
            for record in client_errors:
                lines.extend(
                    [
                        f"### {record.case_key}",
                        "",
                        f"- Path: `{record.path}`",
                        f"- Status: `{record.status_code}`",
                        f"- Message: `{record.message or ''}`",
                        "",
                        "```json",
                        _serialize_json(record.response_body),
                        "```",
                        "",
                    ]
                )

        lines.extend(["## Documented Schema Ambiguities", ""])

        schema_ambiguous_records = [
            record
            for record in self.records
            if record.outcome == "success_2xx_schema_ambiguous"
        ]
        if not schema_ambiguous_records:
            lines.append("No schema-ambiguous successful responses were observed.")
            lines.append("")
        else:
            for record in schema_ambiguous_records:
                lines.extend(
                    [
                        f"### {record.case_key}",
                        "",
                        f"- Path: `{record.path}`",
                        f"- Status: `{record.status_code}`",
                        f"- Reason: `{record.message or ''}`",
                        "",
                        "```json",
                        _serialize_json(record.response_body),
                        "```",
                        "",
                    ]
                )

        self.report_path.write_text("\n".join(lines), encoding="utf-8")


def _serialize_json(value: Any) -> str:
    """Serialize payloads safely for inclusion in the markdown report."""

    try:
        return json.dumps(value, indent=2, sort_keys=True, ensure_ascii=True, default=str)
    except TypeError:
        return json.dumps(str(value), indent=2, ensure_ascii=True)


def _load_live_environment() -> None:
    """Load the repository `.env` file without overriding real env vars."""

    load_dotenv(REPO_DOTENV if REPO_DOTENV.exists() else None)


def _skip_if_credentials_missing() -> None:
    """Skip the suite when required live credentials are absent."""

    _load_live_environment()
    missing = [name for name in REQUIRED_ENV_VARS if not os.getenv(name)]
    if missing:
        pytest.skip("Integration credentials are missing: " + ", ".join(missing))


def _get_access_token_or_skip(client: ZoomClient) -> str:
    """Acquire a live token or skip when the environment cannot reach Zoom."""

    try:
        token = client.get_access_token()
    except httpx.TransportError as exc:
        pytest.skip(
            "Integration environment cannot reach Zoom OAuth: "
            f"{type(exc).__name__}: {exc}"
        )
    assert isinstance(token, str)
    assert token
    return token


def _items(payload: dict[str, Any], *keys: str) -> list[dict[str, Any]]:
    """Extract a list of objects from the first matching payload key."""

    for key in keys:
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return []


def _first_identifier(item: dict[str, Any], *keys: str) -> str | None:
    """Return the first non-empty identifier value from one resource object."""

    for key in keys:
        value = item.get(key)
        if isinstance(value, str) and value:
            return value
        if isinstance(value, int):
            return str(value)
    return None


def _store_first_identifier(
    payload: dict[str, Any],
    state: IntegrationState,
    *,
    state_key: str,
    list_keys: tuple[str, ...],
    id_keys: tuple[str, ...],
) -> None:
    """Store one identifier from a list payload into shared integration state."""

    records = _items(payload, *list_keys)
    if not records:
        return

    identifier = _first_identifier(records[0], *id_keys)
    if identifier:
        state[state_key] = identifier


def _update_user_id(payload: dict[str, Any], state: IntegrationState) -> None:
    _store_first_identifier(
        payload,
        state,
        state_key="user_id",
        list_keys=("users",),
        id_keys=("id",),
    )


def _update_meeting_id(payload: dict[str, Any], state: IntegrationState) -> None:
    _store_first_identifier(
        payload,
        state,
        state_key="meeting_id",
        list_keys=("meetings",),
        id_keys=("id", "uuid"),
    )


def _update_phone_user_id(payload: dict[str, Any], state: IntegrationState) -> None:
    _store_first_identifier(
        payload,
        state,
        state_key="phone_user_id",
        list_keys=("users", "phone_users"),
        id_keys=("id", "user_id"),
    )


def _update_phone_device_id(payload: dict[str, Any], state: IntegrationState) -> None:
    _store_first_identifier(
        payload,
        state,
        state_key="phone_device_id",
        list_keys=("devices", "phone_devices"),
        id_keys=("id", "device_id"),
    )


def _resolve_user_path_params(state: IntegrationState) -> Mapping[str, Any]:
    user_id = state.get("user_id")
    if isinstance(user_id, str) and user_id:
        return {"userId": user_id}
    return {"userId": "me"}


def _resolve_required_path_param(
    state: IntegrationState,
    *,
    state_key: str,
    param_name: str,
    description: str,
) -> Mapping[str, Any]:
    value = state.get(state_key)
    if isinstance(value, str) and value:
        return {param_name: value}

    raise CaseSkip(
        f"Skipping because no {description} identifier was discovered from prior list responses."
    )


def _resolve_report_daily_params(_: IntegrationState) -> Mapping[str, Any]:
    now = datetime.now(UTC)
    return {"year": now.year, "month": now.month}


def _extract_error_details(response: httpx.Response) -> tuple[Any, str]:
    """Extract a structured error payload and human-readable message."""

    message = response.text
    try:
        payload = response.json()
    except Exception:
        payload = response.text

    if isinstance(payload, dict):
        detail = payload.get("message")
        if isinstance(detail, str) and detail:
            message = detail

    return payload, message


def _execute_raw_get_without_schema_validation(
    *,
    client: ZoomClient,
    path: str,
    path_params: Mapping[str, Any] | None,
    params: Mapping[str, Any] | None,
) -> tuple[int, Any]:
    """Execute one authenticated GET without invoking schema validation."""

    raw_path = path if path.startswith("/") else f"/{path}"
    actual_path = client._render_path(raw_path, path_params)
    base_url = client._schemas.base_url_for_request(
        method="GET",
        raw_path=raw_path,
        actual_path=actual_path,
        fallback=client._base_url,
    )
    url = client._build_url(actual_path, base_url=base_url)
    timeout = client._default_timeout
    headers = client._build_headers(None, timeout=timeout)
    response = client._http.request(
        "GET",
        url,
        params=dict(params) if params is not None else None,
        headers=headers,
        timeout=timeout,
    )
    response.raise_for_status()
    if response.status_code == 204 or not response.content:
        return response.status_code, None
    try:
        return response.status_code, response.json()
    except Exception:
        return response.status_code, response.text


INTEGRATION_CASES: tuple[EndpointCase, ...] = (
    EndpointCase(
        key="users_list",
        path="/users",
        params={"page_size": 10},
        state_updater=_update_user_id,
    ),
    EndpointCase(
        key="users_detail",
        path="/users/{userId}",
        path_params_resolver=_resolve_user_path_params,
    ),
    EndpointCase(
        key="users_settings",
        path="/users/{userId}/settings",
        path_params_resolver=_resolve_user_path_params,
        execution_mode="raw_get_schema_ambiguous",
    ),
    EndpointCase(
        key="users_meetings_list",
        path="/users/{userId}/meetings",
        path_params_resolver=_resolve_user_path_params,
        params={"page_size": 10, "type": "scheduled"},
        state_updater=_update_meeting_id,
    ),
    EndpointCase(
        key="meeting_detail",
        path="/meetings/{meetingId}",
        path_params_resolver=lambda state: _resolve_required_path_param(
            state,
            state_key="meeting_id",
            param_name="meetingId",
            description="meeting",
        ),
    ),
    EndpointCase(
        key="phone_users_list",
        path="/phone/users",
        params={"page_size": 10},
        state_updater=_update_phone_user_id,
    ),
    EndpointCase(
        key="phone_user_detail",
        path="/phone/users/{userId}",
        path_params_resolver=lambda state: _resolve_required_path_param(
            state,
            state_key="phone_user_id",
            param_name="userId",
            description="phone user",
        ),
    ),
    EndpointCase(
        key="phone_devices_list",
        path="/phone/devices",
        params={"page_size": 10},
        state_updater=_update_phone_device_id,
    ),
    EndpointCase(
        key="phone_device_detail",
        path="/phone/devices/{deviceId}",
        path_params_resolver=lambda state: _resolve_required_path_param(
            state,
            state_key="phone_device_id",
            param_name="deviceId",
            description="phone device",
        ),
    ),
    EndpointCase(
        key="report_daily",
        path="/report/daily",
        params_resolver=_resolve_report_daily_params,
    ),
    EndpointCase(
        key="metrics_meetings",
        path="/metrics/meetings",
        params={"type": "past", "page_size": 10},
    ),
)


@pytest.fixture(scope="module")
def integration_state() -> IntegrationState:
    """Shared state cache for id dependencies between endpoint cases."""

    return {}


@pytest.fixture(scope="module", autouse=True)
def integration_recorder() -> Iterator[ResponseRecorder]:
    """Collect integration outcomes and always emit a markdown report."""

    recorder = ResponseRecorder(report_path=REPORT_PATH)
    try:
        yield recorder
    finally:
        recorder.write_markdown()


@pytest.fixture(scope="module")
def live_client() -> Iterator[ZoomClient]:
    """Provide one shared authenticated live client for this module."""

    _skip_if_credentials_missing()
    client = ZoomClient()
    try:
        _get_access_token_or_skip(client)
        yield client
    finally:
        client.close()


def _run_endpoint_case(
    *,
    client: ZoomClient,
    case: EndpointCase,
    state: IntegrationState,
    recorder: ResponseRecorder,
) -> None:
    """Execute one endpoint case with 4xx-as-documented handling."""

    try:
        path_params = (
            case.path_params_resolver(state) if case.path_params_resolver is not None else None
        )
        params = case.params_resolver(state) if case.params_resolver is not None else case.params
    except CaseSkip as exc:
        message = str(exc)
        recorder.record_skip(case_key=case.key, path=case.path, message=message)
        pytest.skip(message)

    try:
        status_code: int
        payload: Any
        if case.execution_mode == "validated_request":
            payload = client.request(
                "GET",
                case.path,
                path_params=path_params,
                params=params,
            )
            status_code = 200
        elif case.execution_mode == "raw_get_schema_ambiguous":
            status_code, payload = _execute_raw_get_without_schema_validation(
                client=client,
                path=case.path,
                path_params=path_params,
                params=params,
            )
        else:
            raise ValueError(f"Unknown execution mode: {case.execution_mode!r}")
    except httpx.HTTPStatusError as exc:
        status_code = exc.response.status_code
        response_body, message = _extract_error_details(exc.response)
        if 400 <= status_code <= 499:
            recorder.record_client_error(
                case_key=case.key,
                path=case.path,
                params=params,
                path_params=path_params,
                status_code=status_code,
                response_body=response_body,
                message=message,
            )
            return

        recorder.record_failure(
            case_key=case.key,
            path=case.path,
            params=params,
            path_params=path_params,
            status_code=status_code,
            response_body=response_body,
            message=message,
        )
        raise
    except Exception as exc:
        recorder.record_failure(
            case_key=case.key,
            path=case.path,
            params=params,
            path_params=path_params,
            status_code=None,
            response_body=None,
            message=f"{type(exc).__name__}: {exc}",
        )
        raise

    if case.state_updater is not None and isinstance(payload, dict):
        case.state_updater(payload, state)

    if case.execution_mode == "raw_get_schema_ambiguous":
        recorder.record_schema_ambiguous_success(
            case_key=case.key,
            path=case.path,
            params=params,
            path_params=path_params,
            status_code=status_code,
            response_body=payload,
            reason=SCHEMA_AMBIGUITY_REASON,
        )
    else:
        recorder.record_success(
            case_key=case.key,
            path=case.path,
            params=params,
            path_params=path_params,
            status_code=status_code,
            response_body=payload,
        )


@pytest.mark.integration
def test_integration_auth_and_client_bootstrap(live_client: ZoomClient) -> None:
    """Confirm live auth works and SDK namespaces are exposed."""

    token = live_client.get_access_token()
    assert token
    assert "users" in dir(live_client)


@pytest.mark.integration
@pytest.mark.parametrize(
    "case",
    INTEGRATION_CASES,
    ids=[case.key for case in INTEGRATION_CASES],
)
def test_read_only_integration_cases(
    case: EndpointCase,
    live_client: ZoomClient,
    integration_state: IntegrationState,
    integration_recorder: ResponseRecorder,
) -> None:
    """Run the curated read-only endpoint matrix against a live account."""

    _run_endpoint_case(
        client=live_client,
        case=case,
        state=integration_state,
        recorder=integration_recorder,
    )
