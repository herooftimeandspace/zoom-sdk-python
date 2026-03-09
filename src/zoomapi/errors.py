from __future__ import annotations

class ZoomAPIError(RuntimeError):
    def __init__(self, message: str, *, status_code: int, payload: object | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.payload = payload