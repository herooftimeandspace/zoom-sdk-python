from __future__ import annotations

import httpx

from .accounts import AccountsAPI

class ZoomClient:
    def __init__(self, *, access_token: str, base_url: str = "https://api.zoom.us/v2"):
        self._http = httpx.Client(
            base_url=base_url,
            headers={"Authorization": f"Bearer {access_token}"},
        )
        self.accounts = AccountsAPI(self._http)