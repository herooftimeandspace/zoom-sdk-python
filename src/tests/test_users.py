

"""Contract tests for the Zoom `/users` endpoints.

These tests are intentionally implementation-agnostic: they validate that *whatever* client you
build calls the correct Zoom REST endpoints and that request/response payloads conform to the
OpenAPI schema stored at:

    src/tests/schemas/accounts/users.json

If your implementation doesn't yet match the interface assumed here, that's the point: TDD.
Make the client fit the contract.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import json

import pytest
from jsonschema import validate
from jsonschema.exceptions import ValidationError


SCHEMA_PATH = Path(__file__).parent / "schemas" / "accounts" / "users.json"
DEFAULT_BASE_URL = "https://api.zoom.us/v2"


# ----------------------------
# Helpers: schema extraction
# ----------------------------

def _load_openapi() -> Dict[str, Any]:
    if not SCHEMA_PATH.exists():
        raise RuntimeError(
            f"Schema file not found at {SCHEMA_PATH}. "
            "Expected src/tests/schemas/accounts/users.json"
        )
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def _schema_for(path: str, method: str, status: str) -> Dict[str, Any]:
    doc = _load_openapi()
    paths = doc.get("paths", doc)
    op = paths[path][method.lower()]

    resp = op["responses"][status]
    # Some responses (204) have no content.
    content = resp.get("content")
    if not content:
        return {"type": "null"}

    return content["application/json"]["schema"]


def _request_schema_for(path: str, method: str) -> Dict[str, Any]:
    doc = _load_openapi()
    paths = doc.get("paths", doc)
    op = paths[path][method.lower()]
    return op["requestBody"]["content"]["application/json"]["schema"]


# ----------------------------
# Fake HTTP layer (for TDD)
# ----------------------------


@dataclass
class FakeResponse:
    status_code: int
    payload: Any = None

    def json(self) -> Any:
        return self.payload


class FakeHTTPClient:
    """Minimal requests/httpx-ish interface.

    Your implementation should be able to use an injected transport like this.
    We capture each call for assertions.
    """

    def __init__(self) -> None:
        self.calls: List[Tuple[str, str, Dict[str, Any], Any]] = []
        self._queue: List[FakeResponse] = []

    def queue(self, *responses: FakeResponse) -> None:
        self._queue.extend(responses)

    def request(
        self,
        method: str,
        url: str,
        params: Optional[Dict[str, Any]] = None,
        json: Any = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> FakeResponse:
        self.calls.append((method.upper(), url, params or {}, json))
        if not self._queue:
            raise AssertionError("FakeHTTPClient has no queued responses")
        return self._queue.pop(0)


# ----------------------------
# Fixtures
# ----------------------------


@pytest.fixture()
def http() -> FakeHTTPClient:
    return FakeHTTPClient()


@pytest.fixture()
def client(http: FakeHTTPClient):
    """The client-under-test.

    Contract:
      - Must be constructible with (token=..., base_url=..., http_client=...)
      - Must expose .users with methods:
            list(...)
            get(user_id)
            create(action, user_info)
            update(user_id, **fields)
            delete(user_id)

    If you decide to name things differently, adjust the implementation to match.
    The tests are the contract.
    """

    try:
        # Preferred import location
        from zoompy.client import ZoomClient  # type: ignore
    except Exception:
        try:
            # Fallback import
            from zoompy import ZoomClient  # type: ignore
        except Exception as e:
            raise AssertionError(
                "Could not import ZoomClient. Expected `zoompy.client.ZoomClient` or `zoompy.ZoomClient`."
            ) from e

    return ZoomClient(token="test-token", base_url=DEFAULT_BASE_URL, http_client=http)


# ----------------------------
# Sample payloads (minimal but valid)
# ----------------------------


def _sample_list_users_response() -> Dict[str, Any]:
    # Minimal object satisfying required fields in item schema: `email` and `type`.
    return {
        "page_count": 1,
        "page_number": 1,
        "page_size": 30,
        "total_records": 1,
        "next_page_token": "",
        "users": [
            {
                "id": "u_123",
                "email": "user@example.com",
                "type": 1,
                "first_name": "Test",
                "last_name": "User",
                "status": "active",
            }
        ],
    }


def _sample_get_user_response() -> Dict[str, Any]:
    # GET /users/{userId} schema is an allOf; required field is `type` (plus id in one part).
    return {
        "id": "u_123",
        "type": 1,
        "email": "user@example.com",
        "first_name": "Test",
        "last_name": "User",
        "timezone": "America/Los_Angeles",
        "created_at": "2020-01-01T00:00:00Z",
    }


def _sample_create_user_request() -> Dict[str, Any]:
    return {
        "action": "create",
        "user_info": {
            "email": "new.user@example.com",
            "type": 1,
            "first_name": "New",
            "last_name": "User",
        },
    }


def _sample_create_user_response() -> Dict[str, Any]:
    # Zoom typically returns at least an id; schema is permissive enough for this.
    return {"id": "u_new_123"}


# ----------------------------
# Tests: /users (GET)
# ----------------------------


def test_list_users_calls_expected_endpoint_and_query_params(client, http: FakeHTTPClient):
    http.queue(FakeResponse(200, _sample_list_users_response()))

    result = client.users.list(status="active", page_size=50, next_page_token="tok")

    assert http.calls, "Expected at least one HTTP call"
    method, url, params, body = http.calls[0]

    assert method == "GET"
    assert url == f"{DEFAULT_BASE_URL}/users"
    assert body is None

    # Parameters are defined on the endpoint (status, page_size, next_page_token, etc.).
    assert params.get("status") == "active"
    assert params.get("page_size") == 50
    assert params.get("next_page_token") == "tok"

    # Ensure response made it back through the client.
    assert isinstance(result, dict)
    assert "users" in result


def test_list_users_response_conforms_to_schema(client, http: FakeHTTPClient):
    payload = _sample_list_users_response()
    http.queue(FakeResponse(200, payload))

    result = client.users.list()

    schema = _schema_for("/users", "get", "200")
    validate(instance=result, schema=schema)


def test_list_users_schema_rejects_invalid_payload_shape():
    schema = _schema_for("/users", "get", "200")

    # Missing required users item fields: email, type
    bad = {
        "page_count": 1,
        "page_number": 1,
        "page_size": 30,
        "total_records": 1,
        "next_page_token": "",
        "users": [{"id": "u_123"}],
    }

    with pytest.raises(ValidationError):
        validate(instance=bad, schema=schema)


# ----------------------------
# Tests: /users/{userId} (GET)
# ----------------------------


def test_get_user_calls_expected_endpoint(client, http: FakeHTTPClient):
    http.queue(FakeResponse(200, _sample_get_user_response()))

    result = client.users.get("u_123")

    method, url, params, body = http.calls[0]
    assert method == "GET"
    assert url == f"{DEFAULT_BASE_URL}/users/u_123"
    assert params == {}
    assert body is None

    schema = _schema_for("/users/{userId}", "get", "200")
    validate(instance=result, schema=schema)


# ----------------------------
# Tests: /users (POST)
# ----------------------------


def test_create_user_calls_expected_endpoint_and_validates_request_body(client, http: FakeHTTPClient):
    req = _sample_create_user_request()
    http.queue(FakeResponse(201, _sample_create_user_response()))

    result = client.users.create(action=req["action"], user_info=req["user_info"])

    method, url, params, body = http.calls[0]
    assert method == "POST"
    assert url == f"{DEFAULT_BASE_URL}/users"
    assert params == {}

    # Request body must conform to the OpenAPI request schema.
    request_schema = _request_schema_for("/users", "post")
    validate(instance=body, schema=request_schema)

    # Response body must conform to the 201 schema.
    response_schema = _schema_for("/users", "post", "201")
    validate(instance=result, schema=response_schema)


def test_create_user_rejects_missing_required_fields_locally():
    request_schema = _request_schema_for("/users", "post")

    bad = {"user_info": {"email": "x@y.com", "type": 1}}
    with pytest.raises(ValidationError):
        validate(instance=bad, schema=request_schema)


# ----------------------------
# Tests: /users/{userId} (PATCH)
# ----------------------------


def test_update_user_calls_expected_endpoint_and_sends_patch_body(client, http: FakeHTTPClient):
    http.queue(FakeResponse(204, None))

    result = client.users.update("u_123", first_name="Updated", last_name="Name")

    method, url, params, body = http.calls[0]
    assert method == "PATCH"
    assert url == f"{DEFAULT_BASE_URL}/users/u_123"
    assert params == {}

    # Patch body should validate against request schema.
    request_schema = _request_schema_for("/users/{userId}", "patch")
    validate(instance=body, schema=request_schema)

    # 204: no JSON body.
    assert result is None


# ----------------------------
# Tests: /users/{userId} (DELETE)
# ----------------------------


def test_delete_user_calls_expected_endpoint(client, http: FakeHTTPClient):
    http.queue(FakeResponse(204, None))

    result = client.users.delete("u_123")

    method, url, params, body = http.calls[0]
    assert method == "DELETE"
    assert url == f"{DEFAULT_BASE_URL}/users/u_123"
    assert params == {}
    assert body is None
    assert result is None


# ----------------------------
# Error handling contract
# ----------------------------


@pytest.mark.parametrize(
    "status_code",
    [400, 401, 403, 404, 409, 429, 500],
)
def test_users_methods_raise_on_http_errors(client, http: FakeHTTPClient, status_code: int):
    """Any non-2xx should raise a meaningful exception.

    We don't pin you to a specific exception type yet (humans love bikeshedding names).
    But it must raise *something*.
    """

    http.queue(FakeResponse(status_code, {"message": "nope"}))

    with pytest.raises(Exception):
        client.users.list()