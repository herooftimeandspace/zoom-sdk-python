"""Coverage for sideloaded PBX schema routes and generated SDK methods."""

from __future__ import annotations

import inspect
import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from zoom_sdk import ZoomClient
from zoom_sdk.schema import SchemaRegistry


def _load_har_observed_routes() -> list[dict[str, str]]:
    """Load the curated route inventory extracted from HAR captures."""

    fixture_path = Path(__file__).parent / "fixtures" / "pbx_routes_from_hars.json"
    payload = json.loads(fixture_path.read_text(encoding="utf-8"))
    observed = payload.get("observed_routes")
    if not isinstance(observed, list):
        return []
    return [
        {"method": str(item.get("method", "")).upper(), "path": str(item.get("path", ""))}
        for item in observed
        if isinstance(item, dict)
    ]


def test_pbx_sideloaded_routes_are_indexed_from_har_fixture() -> None:
    """Ensure every non-preflight route discovered in HAR files is indexed."""

    registry = SchemaRegistry()
    indexed = {
        (operation.method, operation.template_path)
        for operation in registry.iter_operations()
        if operation.template_path.startswith("/api/v2/pbx/")
    }
    expected = {
        (route["method"], route["path"])
        for route in _load_har_observed_routes()
        if route["method"] != "OPTIONS"
    }

    assert indexed == expected


def test_pbx_sideloaded_options_preflight_is_not_indexed() -> None:
    """Keep browser preflight methods out of the generated SDK surface."""

    registry = SchemaRegistry()
    indexed = {
        (operation.method, operation.template_path)
        for operation in registry.iter_operations()
        if operation.template_path.startswith("/api/v2/pbx/")
    }
    options_routes = {
        (route["method"], route["path"])
        for route in _load_har_observed_routes()
        if route["method"] == "OPTIONS"
    }

    assert options_routes
    assert indexed.isdisjoint(options_routes)


def test_sdk_exposes_pbx_namespaces_and_methods() -> None:
    """Expose generated PBX methods from sideloaded schemas."""

    client = ZoomClient(access_token="test-access-token")
    try:
        assert callable(client.pbx.devices.get)
        assert callable(client.pbx.devices.update)
        assert callable(client.pbx.devices.list_extensions)
        assert callable(client.pbx.devices.list_manufacturers)
        assert callable(client.pbx.devices.list_models)
        assert callable(client.pbx.devices.list_service_endpoints)
        assert callable(client.pbx.account.get_current)
        assert callable(client.pbx.account.get_user_telemetry)
        assert callable(client.pbx.config.get_enable_xss_filter)
        assert callable(client.pbx.web.get_menu)
        assert callable(client.pbx.web.get_user_info)
    finally:
        client.close()


def test_sdk_normalizes_pbx_query_parameter_names() -> None:
    """Expose snake_case PBX query params from camelCase schema names."""

    client = ZoomClient(access_token="test-access-token")
    try:
        signature = inspect.signature(client.pbx.devices.list_service_endpoints)
    finally:
        client.close()

    assert "account_id" in signature.parameters
    assert "keyword" in signature.parameters
    assert "page_size" in signature.parameters
    assert "page_number" in signature.parameters


def test_pbx_methods_expose_typed_models_and_description_field() -> None:
    """Ensure sideloaded PBX methods build response models for typed SDK access."""

    client = ZoomClient(access_token="test-access-token")
    try:
        detail_model = client.pbx.devices.get.response_model
        update_request_model = client.pbx.devices.update.request_model
        update_response_model = client.pbx.devices.update.response_model
        service_model = client.pbx.devices.list_service_endpoints.response_model
        user_info_model = client.pbx.web.get_user_info.response_model
    finally:
        client.close()

    assert detail_model is not None
    assert update_request_model is not None
    assert update_response_model is not None
    assert service_model is not None
    assert user_info_model is not None
    assert "description" in detail_model.model_fields
    assert "description" in update_request_model.model_fields
    assert "description" in update_response_model.model_fields


def test_pbx_requests_use_configured_pbx_base_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Route PBX requests to `pbx_base_url` instead of the ordinary base URL."""

    client = ZoomClient(
        access_token="test-access-token",
        base_url="https://api.example.test/v2",
        pbx_base_url="https://pbx.example.test",
    )
    captured_url: dict[str, str] = {}

    def fake_http_request(
        method: str,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        json: Any | None = None,
        headers: dict[str, str] | None = None,
        timeout: float | None = None,
    ) -> httpx.Response:
        _ = (params, json, headers, timeout)
        captured_url["value"] = url
        return httpx.Response(
            200,
            json={"enable_xss_filter": True},
            request=httpx.Request(method, url),
        )

    monkeypatch.setattr(client._http, "request", fake_http_request)

    try:
        payload = client.request("GET", "/api/v2/pbx/config/enable_xss_filter")
    finally:
        client.close()

    assert payload == {"enable_xss_filter": True}
    assert captured_url["value"] == "https://pbx.example.test/api/v2/pbx/config/enable_xss_filter"


def test_pbx_account_id_auto_discovery_is_cached(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Resolve PBX account id once and reuse it across account-scoped calls."""

    client = ZoomClient(access_token="test-access-token")
    calls: list[tuple[str, str, dict[str, Any] | None]] = []

    def fake_request(
        method: str,
        path: str,
        *,
        path_params: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        json: Any | None = None,
        headers: dict[str, str] | None = None,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        _ = (params, json, headers, timeout)
        calls.append((method, path, path_params))
        if path == "/api/v2/pbx/current/account":
            return {"accountId": "acct-123"}
        if path == "/api/v2/pbx/account/{accountId}/device/{deviceId}":
            assert path_params is not None
            assert path_params["accountId"] == "acct-123"
            return {
                "accountId": "acct-123",
                "deviceId": str(path_params["deviceId"]),
                "description": "desk phone",
            }
        raise AssertionError(f"Unexpected request: {method} {path}")

    monkeypatch.setattr(client, "request", fake_request)

    try:
        first = client.pbx.devices.get.raw(device_id="dev-1")
        second = client.pbx.devices.get.raw(device_id="dev-2")
    finally:
        client.close()

    assert isinstance(first, dict)
    assert isinstance(second, dict)
    current_account_calls = [
        call for call in calls if call[1] == "/api/v2/pbx/current/account"
    ]
    assert len(current_account_calls) == 1


def test_pbx_update_auto_discovery_and_body_mapping(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Resolve account id for update and map body fields into PATCH JSON."""

    client = ZoomClient(access_token="test-access-token")
    calls: list[tuple[str, str, dict[str, Any] | None, dict[str, Any] | None]] = []

    def fake_request(
        method: str,
        path: str,
        *,
        path_params: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        json: Any | None = None,
        headers: dict[str, str] | None = None,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        _ = (params, headers, timeout)
        payload = json if isinstance(json, dict) else None
        calls.append((method, path, path_params, payload))
        if path == "/api/v2/pbx/current/account":
            return {"accountId": "acct-123"}
        if path == "/api/v2/pbx/account/{accountId}/device/{deviceId}":
            assert method == "PATCH"
            assert path_params is not None
            assert path_params["accountId"] == "acct-123"
            assert path_params["deviceId"] == "dev-1"
            assert payload == {
                "name": "Desk Phone",
                "description": "Front office",
            }
            return {
                "accountId": "acct-123",
                "deviceId": "dev-1",
                "description": "Front office",
            }
        raise AssertionError(f"Unexpected request: {method} {path}")

    monkeypatch.setattr(client, "request", fake_request)

    try:
        payload = client.pbx.devices.update.raw(
            device_id="dev-1",
            name="Desk Phone",
            description="Front office",
        )
    finally:
        client.close()

    assert isinstance(payload, dict)
    current_account_calls = [
        call for call in calls if call[1] == "/api/v2/pbx/current/account"
    ]
    assert len(current_account_calls) == 1


def test_pbx_account_id_auto_discovery_is_skipped_when_explicit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Use explicit account ids without issuing a discovery request."""

    client = ZoomClient(access_token="test-access-token")
    calls: list[tuple[str, str, dict[str, Any] | None]] = []

    def fake_request(
        method: str,
        path: str,
        *,
        path_params: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        json: Any | None = None,
        headers: dict[str, str] | None = None,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        _ = (params, json, headers, timeout)
        calls.append((method, path, path_params))
        if path == "/api/v2/pbx/account/{accountId}/device/{deviceId}":
            assert path_params is not None
            assert path_params["accountId"] == "explicit-acct"
            return {
                "accountId": "explicit-acct",
                "deviceId": str(path_params["deviceId"]),
                "description": "desk phone",
            }
        raise AssertionError(f"Unexpected request: {method} {path}")

    monkeypatch.setattr(client, "request", fake_request)

    try:
        payload = client.pbx.devices.get.raw(
            account_id="explicit-acct",
            device_id="dev-1",
        )
    finally:
        client.close()

    assert isinstance(payload, dict)
    assert not any(call[1] == "/api/v2/pbx/current/account" for call in calls)


def test_pbx_account_id_auto_discovery_raises_on_missing_account_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Raise a clear error when account discovery does not return `accountId`."""

    client = ZoomClient(access_token="test-access-token")
    calls: list[tuple[str, str, dict[str, Any] | None]] = []

    def fake_request(
        method: str,
        path: str,
        *,
        path_params: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        json: Any | None = None,
        headers: dict[str, str] | None = None,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        _ = (path_params, params, json, headers, timeout)
        calls.append((method, path, None))
        if path == "/api/v2/pbx/current/account":
            return {"name": "missing account id"}
        raise AssertionError(f"Unexpected request: {method} {path}")

    monkeypatch.setattr(client, "request", fake_request)

    try:
        with pytest.raises(ValueError, match="accountId"):
            client.pbx.devices.get.raw(device_id="dev-1")
    finally:
        client.close()

    assert not any(
        call[1] == "/api/v2/pbx/account/{accountId}/device/{deviceId}"
        for call in calls
    )
