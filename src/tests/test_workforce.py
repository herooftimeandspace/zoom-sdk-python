

from __future__ import annotations

import io
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

import httpx
import pytest
import respx
from jsonschema import Draft202012Validator


SPEC_PATH = (
    Path(__file__).resolve().parent
    / "schemas"
    / "build_platform"
    / "Workforce Management.json"
)


def _load_openapi_spec() -> dict[str, Any]:
    # The schema file is checked into the repo under src/tests/schemas/...
    raw = SPEC_PATH.read_text(encoding="utf-8")
    return json.loads(raw)


def _get_operation(spec: Mapping[str, Any], path: str, method: str) -> Mapping[str, Any]:
    paths = spec.get("paths", {})
    op = paths.get(path, {}).get(method.lower())
    if not op:
        raise KeyError(f"Missing operation for {method.upper()} {path}")
    return op


def _get_response_schema(
    spec: Mapping[str, Any],
    path: str,
    method: str,
    status_code: int,
    content_type: str = "application/json",
) -> Mapping[str, Any] | None:
    op = _get_operation(spec, path, method)
    responses = op.get("responses", {})
    resp = responses.get(str(status_code))
    if not resp:
        return None
    content = (resp.get("content") or {}).get(content_type)
    if not content:
        return None
    schema = content.get("schema")
    return schema


def _assert_json_matches_schema(payload: Any, schema: Mapping[str, Any]) -> None:
    # Draft 2020-12 is the most modern draft jsonschema supports well.
    Draft202012Validator(schema).validate(payload)


@dataclass(frozen=True)
class WorkforceManagementClient:
    """Tiny reference client.

    These tests are meant to validate the request/response contract for any
    implementation talking to these endpoints. If your real client behaves
    differently, the contract is still the contract.
    """

    base_url: str
    token: str
    http: httpx.Client

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"}

    # Forecasts
    def list_forecasts(self, **params: Any) -> httpx.Response:
        return self.http.get(
            f"{self.base_url}/workforce-management/forecasts",
            headers=self._headers(),
            params=params,
        )

    def get_forecast_for_scheduling_group(
        self, forecast_id: str, scheduling_group_id: str, **params: Any
    ) -> httpx.Response:
        return self.http.get(
            f"{self.base_url}/workforce-management/forecasts/{forecast_id}/scheduling-groups/{scheduling_group_id}",
            headers=self._headers(),
            params=params,
        )

    # Imports
    def upload_historical_queue_metrics(
        self,
        file_bytes: bytes,
        filename: str = "HistoricalData.csv",
        timezone: str | None = None,
        allow_overwrite: bool | None = None,
    ) -> httpx.Response:
        files = {"file": (filename, io.BytesIO(file_bytes), "text/csv")}
        data: dict[str, Any] = {}
        if timezone is not None:
            data["timezone"] = timezone
        if allow_overwrite is not None:
            data["allow_overwrite"] = allow_overwrite
        return self.http.post(
            f"{self.base_url}/workforce-management/imports/historical-queue-metrics",
            headers=self._headers(),
            files=files,
            data=data,
        )

    def get_historical_queue_metrics_import_metadata(
        self, import_id: str, **params: Any
    ) -> httpx.Response:
        return self.http.get(
            f"{self.base_url}/workforce-management/imports/{import_id}/historical-queue-metrics",
            headers=self._headers(),
            params=params,
        )

    # Organizational Groups
    def list_organizational_groups(self, **params: Any) -> httpx.Response:
        return self.http.get(
            f"{self.base_url}/workforce-management/organizational-groups",
            headers=self._headers(),
            params=params,
        )

    def create_organizational_group(self, payload: Mapping[str, Any]) -> httpx.Response:
        return self.http.post(
            f"{self.base_url}/workforce-management/organizational-groups",
            headers={**self._headers(), "Content-Type": "application/json"},
            json=dict(payload),
        )

    def get_organizational_group(self, organizational_group_id: str) -> httpx.Response:
        return self.http.get(
            f"{self.base_url}/workforce-management/organizational-groups/{organizational_group_id}",
            headers=self._headers(),
        )

    def update_organizational_group(
        self, organizational_group_id: str, payload: Mapping[str, Any]
    ) -> httpx.Response:
        return self.http.patch(
            f"{self.base_url}/workforce-management/organizational-groups/{organizational_group_id}",
            headers={**self._headers(), "Content-Type": "application/json"},
            json=dict(payload),
        )

    def delete_organizational_group(self, organizational_group_id: str) -> httpx.Response:
        return self.http.delete(
            f"{self.base_url}/workforce-management/organizational-groups/{organizational_group_id}",
            headers=self._headers(),
        )

    # Reports
    def list_adherence_agents(self, *, date: str, **params: Any) -> httpx.Response:
        # date is required by the spec
        return self.http.get(
            f"{self.base_url}/workforce-management/reports/adherence/agents",
            headers=self._headers(),
            params={"date": date, **params},
        )

    def list_schedule_agents(self, *, date: str, **params: Any) -> httpx.Response:
        # date is required by the spec
        return self.http.get(
            f"{self.base_url}/workforce-management/reports/schedules/agents",
            headers=self._headers(),
            params={"date": date, **params},
        )


@pytest.fixture(scope="session")
def spec() -> dict[str, Any]:
    return _load_openapi_spec()


@pytest.fixture()
def base_url() -> str:
    return "https://api.zoom.us/v2"


@pytest.fixture()
def token() -> str:
    # In mocked tests this can be anything.
    return "test-token"


@pytest.fixture()
def http_client() -> Iterable[httpx.Client]:
    with httpx.Client(timeout=5.0) as client:
        yield client


@pytest.fixture()
def wfm(base_url: str, token: str, http_client: httpx.Client) -> WorkforceManagementClient:
    return WorkforceManagementClient(base_url=base_url, token=token, http=http_client)


def _minimal_forecasts_list_response() -> dict[str, Any]:
    return {
        "next_page_token": None,
        "page_size": 10,
        "total_records": 1,
        "forecasts": [
            {
                "forecast_id": "cm2n7z2vl000e9cllp4ckoc45",
                "name": "Weekday forecast",
                "description": "Forecast for business days",
                "type": "SHORT_TERM",
                "status": "ready_step_1",
                "start": "2025-01-01T00:00:00Z",
                "end": "2025-01-06T23:59:59Z",
                "create_time": "2024-12-16T04:21:23.207Z",
                "modify_time": "2024-12-16T04:21:23.207Z",
                "interval_minutes": 15,
                "forecast_profile_id": None,
                "scheduling_groups": [
                    {
                        "scheduling_group_id": "cm2n7z2vl000e9cllp4ckoc45",
                        "name": "Infra support",
                        "color_code": "#c0106f",
                        "sla": 75,
                        "sla_target_time": 30,
                        "asa": 30,
                        "occupancy": 85,
                        "fixed_shrinkage": 20,
                        "dynamic_shrinkage": None,
                        "deferrable_sla": 75,
                        "deferrable_sla_target_time": 30,
                    }
                ],
            }
        ],
    }


def _minimal_forecast_sg_response() -> dict[str, Any]:
    return {
        "forecast_id": "cm2n7z2vl000e9cllp4ckoc45",
        "scheduling_group_id": "cm2n7z2vl000e9cllp4ckoc45",
        "forecast_intervals": [
            {
                "timestamp": "2025-01-01T00:00:00Z",
                "forecast": {"agents": 5},
            }
        ],
    }


def _minimal_upload_import_response() -> dict[str, Any]:
    return {"import_id": "cmgoyz7mb00002f6obth9ojea"}


def _minimal_import_metadata_response() -> dict[str, Any]:
    return {
        "status": "SUCCESS",
        "create_time": "2025-11-05T04:13:40.800Z",
        "row_processed": 1000,
        "total_rows": 1000,
        "import_id": "cmgoyz7mb00002f6obth9ojea",
        "file_name": "HistoricalData.csv",
        "timezone": "America/New_York",
        "imported_by": "3U-_aQo_ROeigseGAQL5_A",
    }


def _minimal_list_org_groups_response() -> dict[str, Any]:
    return {
        "organizational_groups": [
            {
                "org_group_id": "cmgoyz7mb00002f6obth9ojea",
                "name": "West Coast Operations",
                "description": "Organizational group for west coast teams",
                "created_at": "2024-01-15T10:30:00Z",
                "updated_at": "2024-01-15T10:30:00Z",
            }
        ],
        "page_size": 10,
        "total_records": "1",
        "next_page_token": "cm2n7z2vl000e9cllp4ckoc45",
    }


def _minimal_org_group_response() -> dict[str, Any]:
    return {
        "org_group_id": "cmgoyz7mb00002f6obth9ojea",
        "name": "West Coast Operations",
        "description": "Organizational group for west coast teams",
        "created_at": "2024-01-15T10:30:00Z",
        "updated_at": "2024-01-15T10:30:00Z",
    }


def _minimal_single_org_group_response() -> dict[str, Any]:
    return {
        "org_group_id": "cmgoyz7mb00002f6obth9ojea",
        "name": "West Coast Operations",
        "description": "Organizational group for west coast teams",
        "created_at": "2024-01-15T10:30:00Z",
        "updated_at": "2024-01-15T10:30:00Z",
        "agent_count": 42,
        "queue_count": 8,
        "scheduling_groups": [
            {"scheduling_group_id": "cmgoyz7mb00002f6obth9ojea", "name": "Morning Shift"}
        ],
    }


def _minimal_list_adherence_agents_response() -> dict[str, Any]:
    return {
        "agents": [
            {
                "user_id": "0c30da44bd68aae3b5714abb885a59",
                "display_name": "Alex",
                "shifts": [
                    {
                        "start_time": "2024-11-06T03:30:00.000Z",
                        "end_time": "2024-11-06T03:30:00.000Z",
                        "start_in_adherence": 0,
                        "end_in_adherence": 0,
                    }
                ],
                "schedule_activities": [
                    {
                        "activity_id": "0c30da44bd68aae3b5714abb885a59",
                        "activity_name": "Chat",
                        "start_time": 1730896200000,
                        "end_time": 1730896200000,
                    }
                ],
                "adherence_time_for_activity": [
                    {
                        "activity_id": "0c30da44bd68aae3b5714abb885a59",
                        "activity_name": "Chat",
                        "activity_in_adherence": 0,
                        "activity_out_adherence": 0,
                    }
                ],
            }
        ],
        "next_page_token": "jA5csQv1W1oXuYZLspNIZzMOXqTD9r9Rje2",
        "page_size": 10,
        "timezone": "America/Los_Angeles",
        "total_records": 1,
    }


def _minimal_list_schedule_agents_response() -> dict[str, Any]:
    return {
        "agents": [
            {
                "user_id": "0c30da44bd68aae3b5714abb885a59",
                "display_name": "Alex",
                "user_email": "alex@example.com",
                "scheduling_group_name": "Sales",
                "total_paid_time": 340,
                "total_scheduled_time": 480,
                "activities": [
                    {
                        "schedule_activity_id": "cll20wknm01cwex0isvewiegl",
                        "start_time": "2024-07-20T14:00:00-08:00",
                        "end_time": "2024-07-20T14:00:00-08:00",
                        "activity_name": "SMS",
                        "activity_type": "Productive",
                        "is_paid": True,
                    }
                ],
            }
        ],
        "next_page_token": "jA5csQv1W1oXuYZLspNIZzMOXqTD9r9Rje2",
        "page_size": 10,
        "timezone": "America/Los_Angeles",
        "total_records": 1,
    }


@respx.mock
def test_list_forecasts_contract(spec: dict[str, Any], wfm: WorkforceManagementClient) -> None:
    route = respx.get("https://api.zoom.us/v2/workforce-management/forecasts").mock(
        return_value=httpx.Response(200, json=_minimal_forecasts_list_response())
    )

    resp = wfm.list_forecasts(page_size=10)

    assert route.called
    assert resp.status_code == 200

    schema = _get_response_schema(
        spec, "/workforce-management/forecasts", "get", 200, "application/json"
    )
    assert schema is not None
    _assert_json_matches_schema(resp.json(), schema)


@respx.mock
def test_get_forecast_for_scheduling_group_contract(
    spec: dict[str, Any],
    wfm: WorkforceManagementClient,
) -> None:
    forecast_id = "cm2n7z2vl000e9cllp4ckoc45"
    sg_id = "cm2n7z2vl000e9cllp4ckoc45"

    route = respx.get(
        f"https://api.zoom.us/v2/workforce-management/forecasts/{forecast_id}/scheduling-groups/{sg_id}"
    ).mock(return_value=httpx.Response(200, json=_minimal_forecast_sg_response()))

    resp = wfm.get_forecast_for_scheduling_group(forecast_id, sg_id)

    assert route.called
    assert resp.status_code == 200

    schema = _get_response_schema(
        spec,
        "/workforce-management/forecasts/{forecastId}/scheduling-groups/{schedulingGroupId}",
        "get",
        200,
    )
    assert schema is not None
    _assert_json_matches_schema(resp.json(), schema)


@respx.mock
def test_upload_historical_queue_metrics_contract(
    spec: dict[str, Any],
    wfm: WorkforceManagementClient,
) -> None:
    route = respx.post(
        "https://api.zoom.us/v2/workforce-management/imports/historical-queue-metrics"
    ).mock(return_value=httpx.Response(201, json=_minimal_upload_import_response()))

    resp = wfm.upload_historical_queue_metrics(
        b"a,b,c\n1,2,3\n", timezone="America/Los_Angeles", allow_overwrite=True
    )

    assert route.called
    request = route.calls[0].request
    assert request.headers.get("Authorization") == "Bearer test-token"
    assert request.headers.get("content-type", "").startswith("multipart/form-data")

    assert resp.status_code == 201
    schema = _get_response_schema(
        spec,
        "/workforce-management/imports/historical-queue-metrics",
        "post",
        201,
    )
    assert schema is not None
    _assert_json_matches_schema(resp.json(), schema)


@respx.mock
def test_get_import_metadata_contract(spec: dict[str, Any], wfm: WorkforceManagementClient) -> None:
    import_id = "cmgoyz7mb00002f6obth9ojea"

    route = respx.get(
        f"https://api.zoom.us/v2/workforce-management/imports/{import_id}/historical-queue-metrics"
    ).mock(return_value=httpx.Response(200, json=_minimal_import_metadata_response()))

    resp = wfm.get_historical_queue_metrics_import_metadata(import_id)

    assert route.called
    assert resp.status_code == 200

    schema = _get_response_schema(
        spec,
        "/workforce-management/imports/{importId}/historical-queue-metrics",
        "get",
        200,
    )
    assert schema is not None
    _assert_json_matches_schema(resp.json(), schema)


@respx.mock
def test_list_organizational_groups_contract(
    spec: dict[str, Any], wfm: WorkforceManagementClient
) -> None:
    route = respx.get(
        "https://api.zoom.us/v2/workforce-management/organizational-groups"
    ).mock(return_value=httpx.Response(200, json=_minimal_list_org_groups_response()))

    resp = wfm.list_organizational_groups(page_size=10)

    assert route.called
    assert resp.status_code == 200

    schema = _get_response_schema(
        spec, "/workforce-management/organizational-groups", "get", 200
    )
    assert schema is not None
    _assert_json_matches_schema(resp.json(), schema)


@respx.mock
def test_create_organizational_group_contract(
    spec: dict[str, Any], wfm: WorkforceManagementClient
) -> None:
    route = respx.post(
        "https://api.zoom.us/v2/workforce-management/organizational-groups"
    ).mock(return_value=httpx.Response(201, json=_minimal_org_group_response()))

    payload = {
        "name": "West Coast Operations",
        "description": "Organizational group for west coast teams",
        "scheduling_group_ids": ["cmgoyz7mb00002f6obth9ojea"],
    }
    resp = wfm.create_organizational_group(payload)

    assert route.called
    request = route.calls[0].request
    assert request.method == "POST"
    assert request.headers.get("Authorization") == "Bearer test-token"

    assert resp.status_code == 201

    schema = _get_response_schema(
        spec, "/workforce-management/organizational-groups", "post", 201
    )
    assert schema is not None
    _assert_json_matches_schema(resp.json(), schema)


@respx.mock
def test_get_update_delete_organizational_group_contract(
    spec: dict[str, Any],
    wfm: WorkforceManagementClient,
) -> None:
    og_id = "cmgoyz7mb00002f6obth9ojea"

    get_route = respx.get(
        f"https://api.zoom.us/v2/workforce-management/organizational-groups/{og_id}"
    ).mock(return_value=httpx.Response(200, json=_minimal_single_org_group_response()))

    patch_route = respx.patch(
        f"https://api.zoom.us/v2/workforce-management/organizational-groups/{og_id}"
    ).mock(return_value=httpx.Response(200, json=_minimal_org_group_response()))

    delete_route = respx.delete(
        f"https://api.zoom.us/v2/workforce-management/organizational-groups/{og_id}"
    ).mock(return_value=httpx.Response(204))

    # GET
    resp = wfm.get_organizational_group(og_id)
    assert get_route.called
    assert resp.status_code == 200

    get_schema = _get_response_schema(
        spec,
        "/workforce-management/organizational-groups/{organizationalGroupId}",
        "get",
        200,
    )
    assert get_schema is not None
    _assert_json_matches_schema(resp.json(), get_schema)

    # PATCH
    resp = wfm.update_organizational_group(og_id, {"name": "West Coast Ops"})
    assert patch_route.called
    assert resp.status_code == 200

    patch_schema = _get_response_schema(
        spec,
        "/workforce-management/organizational-groups/{organizationalGroupId}",
        "patch",
        200,
    )
    assert patch_schema is not None
    _assert_json_matches_schema(resp.json(), patch_schema)

    # DELETE
    resp = wfm.delete_organizational_group(og_id)
    assert delete_route.called
    assert resp.status_code == 204


@respx.mock
def test_reports_adherence_agents_contract(
    spec: dict[str, Any],
    wfm: WorkforceManagementClient,
) -> None:
    route = respx.get(
        "https://api.zoom.us/v2/workforce-management/reports/adherence/agents"
    ).mock(return_value=httpx.Response(200, json=_minimal_list_adherence_agents_response()))

    resp = wfm.list_adherence_agents(date="2025-09-01", timezone="America/Los_Angeles")

    assert route.called

    request = route.calls[0].request
    assert "date=2025-09-01" in str(request.url)

    assert resp.status_code == 200
    schema = _get_response_schema(
        spec, "/workforce-management/reports/adherence/agents", "get", 200
    )
    assert schema is not None
    _assert_json_matches_schema(resp.json(), schema)


@respx.mock
def test_reports_schedule_agents_contract(
    spec: dict[str, Any],
    wfm: WorkforceManagementClient,
) -> None:
    route = respx.get(
        "https://api.zoom.us/v2/workforce-management/reports/schedules/agents"
    ).mock(return_value=httpx.Response(200, json=_minimal_list_schedule_agents_response()))

    resp = wfm.list_schedule_agents(date="2025-09-01", timezone="America/Los_Angeles")

    assert route.called

    request = route.calls[0].request
    assert "date=2025-09-01" in str(request.url)

    assert resp.status_code == 200
    schema = _get_response_schema(
        spec, "/workforce-management/reports/schedules/agents", "get", 200
    )
    assert schema is not None
    _assert_json_matches_schema(resp.json(), schema)


def test_openapi_spec_has_expected_endpoints(spec: dict[str, Any]) -> None:
    # A quick sanity check that the spec file we ship in the repo still contains
    # the things these tests are asserting.
    expected: list[tuple[str, str]] = [
        ("/workforce-management/forecasts", "get"),
        (
            "/workforce-management/forecasts/{forecastId}/scheduling-groups/{schedulingGroupId}",
            "get",
        ),
        ("/workforce-management/imports/historical-queue-metrics", "post"),
        ("/workforce-management/imports/{importId}/historical-queue-metrics", "get"),
        ("/workforce-management/organizational-groups", "get"),
        ("/workforce-management/organizational-groups", "post"),
        ("/workforce-management/organizational-groups/{organizationalGroupId}", "get"),
        ("/workforce-management/organizational-groups/{organizationalGroupId}", "patch"),
        ("/workforce-management/organizational-groups/{organizationalGroupId}", "delete"),
        ("/workforce-management/reports/adherence/agents", "get"),
        ("/workforce-management/reports/schedules/agents", "get"),
    ]

    for path, method in expected:
        _get_operation(spec, path, method)