from __future__ import annotations

from typing import Any, Iterable
import httpx

from .errors import ZoomAPIError

def _raise_for_status(resp: httpx.Response) -> None:
    if 200 <= resp.status_code < 300:
        return
    try:
        payload = resp.json()
        msg = payload.get("message") or str(payload)
    except Exception:
        payload = None
        msg = resp.text or resp.reason_phrase
    raise ZoomAPIError(msg, status_code=resp.status_code, payload=payload)

def _csv(value: str | Iterable[str] | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return ",".join(value)

class AccountsAPI:
    def __init__(self, http: httpx.Client):
        self._http = http

    def get_managed_domains(self, account_id: str) -> dict[str, Any]:
        r = self._http.get(f"/accounts/{account_id}/managed_domains")
        _raise_for_status(r)
        return r.json()

    def get_trusted_domains(self, account_id: str) -> dict[str, Any]:
        r = self._http.get(f"/accounts/{account_id}/trusted_domains")
        _raise_for_status(r)
        return r.json()

    def get_lock_settings(self, account_id: str, *, option: str | None = None, custom_query_fields=None):
        params = {k: v for k, v in {
            "option": option,
            "custom_query_fields": _csv(custom_query_fields),
        }.items() if v is not None}
        r = self._http.get(f"/accounts/{account_id}/lock_settings", params=params)
        _raise_for_status(r)
        return r.json()

    def update_lock_settings(self, account_id: str, data: dict[str, Any]):
        r = self._http.patch(f"/accounts/{account_id}/lock_settings", json=data)
        _raise_for_status(r)
        return r.json()

    def get_settings(self, account_id: str, *, option: str | None = None, custom_query_fields=None):
        params = {k: v for k, v in {
            "option": option,
            "custom_query_fields": _csv(custom_query_fields),
        }.items() if v is not None}
        r = self._http.get(f"/accounts/{account_id}/settings", params=params)
        _raise_for_status(r)
        return r.json()

    def update_settings(self, account_id: str, data: dict[str, Any], *, option: str | None = None):
        params = {k: v for k, v in {"option": option}.items() if v is not None}
        r = self._http.patch(f"/accounts/{account_id}/settings", params=params, json=data)
        _raise_for_status(r)
        return None if r.status_code == 204 else r.json()

    def get_registration_settings(self, account_id: str, *, type: str):
        r = self._http.get(f"/accounts/{account_id}/settings/registration", params={"type": type})
        _raise_for_status(r)
        return r.json()

    def update_registration_settings(self, account_id: str, *, type: str, data: dict[str, Any]):
        r = self._http.patch(f"/accounts/{account_id}/settings/registration", params={"type": type}, json=data)
        _raise_for_status(r)
        return None if r.status_code == 204 else r.json()

    def update_owner(self, account_id: str, *, email: str):
        r = self._http.put(f"/accounts/{account_id}/owner", json={"email": email})
        _raise_for_status(r)
        return None if r.status_code == 204 else r.json()

    def upload_virtual_background(self, account_id: str, *, filename: str, file, content_type: str):
        files = {"file": (filename, file, content_type)}
        r = self._http.post(f"/accounts/{account_id}/settings/virtual_backgrounds", files=files)
        _raise_for_status(r)
        return r.json()

    def delete_virtual_backgrounds(self, account_id: str, *, file_ids: Iterable[str] | str):
        params = {"file_ids": _csv(file_ids)}
        r = self._http.delete(f"/accounts/{account_id}/settings/virtual_backgrounds", params=params)
        _raise_for_status(r)
        return None if r.status_code == 204 else r.json()