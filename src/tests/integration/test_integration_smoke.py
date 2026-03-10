"""Minimal live integration smoke tests for `zoompy`.

The contract suites cover most behavior offline with mocked HTTP. This file is
deliberately small and exists only to prove that live configuration can produce
an OAuth token in an environment where Zoom credentials are available.
"""

from __future__ import annotations

import os

import pytest

from zoompy import ZoomClient


REQUIRED_ENV_VARS = (
    "ZOOM_ACCOUNT_ID",
    "ZOOM_CLIENT_ID",
    "ZOOM_CLIENT_SECRET",
)


@pytest.mark.integration
def test_integration_smoke_token_acquisition() -> None:
    """Acquire a real token when integration credentials are available."""

    missing = [name for name in REQUIRED_ENV_VARS if not os.getenv(name)]
    if missing:
        pytest.skip(
            "Integration credentials are missing: " + ", ".join(missing)
        )

    client = ZoomClient()
    try:
        token = client.get_access_token()
        assert isinstance(token, str)
        assert token
    finally:
        client.close()
