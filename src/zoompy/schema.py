"""OpenAPI schema loading and response validation for `zoompy`.

The client always validates JSON responses against the bundled OpenAPI schema
files. This module owns that behavior so request execution code stays focused on
HTTP mechanics rather than schema traversal.

The Zoom-published OpenAPI files are good enough to drive broad validation, but
they are not perfectly uniform. A few documents use slightly non-standard JSON
Schema details such as capitalized type names or inconsistent server URLs. The
logic in this module is intentionally a little forgiving so callers see
validation errors for meaningful response-shape problems instead of noise caused
by minor schema formatting issues.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Any, Iterable, Mapping

from jsonschema import Draft202012Validator


@dataclass(frozen=True)
class SchemaOperation:
    """One HTTP operation extracted from a single OpenAPI document."""

    schema_name: str
    method: str
    template_path: str
    path_regex: re.Pattern[str]
    responses: Mapping[str, Any]
    spec: Mapping[str, Any]
    server_url: str | None


class SchemaRegistry:
    """Index packaged OpenAPI schema files for fast operation lookup.

        The registry builds a small prefix index so we do not need to scan every
        single operation for every request. That said, correctness is more
        important than theoretical performance here, so the implementation stays
        intentionally straightforward and readable.

        This class also acts as the package's "schema normalizer". The
        production client should validate real API responses strictly, but it
        also needs to tolerate small quirks in the upstream schema files. That
        balance lives here instead of being spread across the HTTP client.
    """

    def __init__(self) -> None:
        """Load bundled schema files and build the operation index."""

        self._operations_by_prefix: dict[str, list[SchemaOperation]] = {}
        self._load_packaged_schemas()

    def validate_response(
        self,
        *,
        method: str,
        raw_path: str,
        actual_path: str,
        status_code: int,
        payload: Any,
    ) -> None:
        """Validate one response payload against the matching OpenAPI schema.

        Parameters
        ----------
        method:
            The HTTP method used for the request.
        raw_path:
            The path string originally passed to `ZoomClient.request()`. This may
            still contain `{pathParam}` placeholders.
        actual_path:
            The fully rendered path that was sent over HTTP.
        status_code:
            The HTTP response status code.
        payload:
            The parsed JSON payload, or `None` when the response had no body.

        The validator uses a resolved and normalized schema tree. In practice
        that means local `$ref` values are inlined first, and then small schema
        quirks such as `type: Integer` are corrected before JSON Schema
        validation runs.
        """

        operation = self.find_operation(method=method, raw_path=raw_path, actual_path=actual_path)
        schema = self._pick_response_schema(operation, status_code)

        # No-content responses are allowed to omit a schema entirely.
        if payload is None:
            return

        if schema is None:
            raise ValueError(
                f"No response schema found for {method.upper()} {actual_path} "
                f"with status {status_code}."
            )

        # We normalize after resolving refs so type corrections apply to both
        # inline schema fragments and component schemas reached through `$ref`.
        resolved_schema = self._normalize_schema(
            self._resolve_schema(operation.spec, schema)
        )
        validator = Draft202012Validator(resolved_schema)
        errors = sorted(validator.iter_errors(payload), key=lambda item: list(item.path))
        if errors:
            formatted = "; ".join(
                f"path={list(error.path)} message={error.message}"
                for error in errors[:5]
            )
            raise ValueError(
                f"Schema validation failed for {method.upper()} {actual_path} "
                f"status {status_code}: {formatted}"
            )

    def base_url_for_request(
        self,
        *,
        method: str,
        raw_path: str,
        actual_path: str,
        fallback: str,
    ) -> str:
        """Return the most appropriate server URL for one request.

        The bundled schemas are not perfectly uniform about their server URLs.
        Most endpoints use `https://api.zoom.us/v2`, while a few families such
        as Clips and SCIM are documented at `https://api.zoom.us` instead.

        The client still needs one deterministic URL to call, so we first try
        to match the operation in the schema registry and then return that
        operation's declared server URL. If the lookup fails for any reason, we
        fall back to the client's configured base URL rather than making schema
        lookup a hard precondition for sending the request.
        """

        try:
            operation = self.find_operation(
                method=method,
                raw_path=raw_path,
                actual_path=actual_path,
            )
        except ValueError:
            return fallback.rstrip("/")

        if operation.server_url:
            return operation.server_url.rstrip("/")
        return fallback.rstrip("/")

    def find_operation(
        self,
        *,
        method: str,
        raw_path: str,
        actual_path: str,
    ) -> SchemaOperation:
        """Find the schema operation that matches a request.

        We first narrow by the path's leading segment, then try:

        1. exact match on the raw path
        2. exact match on the rendered path
        3. regex match against templated paths
        """

        candidates = self._candidate_operations(raw_path, actual_path)
        upper_method = method.upper()

        for candidate in candidates:
            if (
                candidate.method == upper_method and
                candidate.template_path == raw_path
            ):
                return candidate

        for candidate in candidates:
            if (
                candidate.method == upper_method and
                candidate.template_path == actual_path
            ):
                return candidate

        for candidate in candidates:
            if (
                candidate.method == upper_method and
                candidate.path_regex.fullmatch(actual_path)
            ):
                return candidate

        raise ValueError(
            f"Could not find OpenAPI operation for {upper_method} {actual_path} "
            f"(raw path: {raw_path})."
        )

    def _candidate_operations(
        self,
        raw_path: str,
        actual_path: str,
    ) -> list[SchemaOperation]:
        """Return operations from the relevant prefix buckets.

        The first path segment is a good enough discriminator for this package's
        current schema layout and keeps lookup logic simple to explain.
        """

        prefixes = {self._path_prefix(raw_path), self._path_prefix(actual_path)}
        candidates: list[SchemaOperation] = []
        seen: set[tuple[str, str, str]] = set()

        for prefix in prefixes:
            for operation in self._operations_by_prefix.get(prefix, []):
                key = (
                    operation.schema_name,
                    operation.method,
                    operation.template_path,
                )
                if key not in seen:
                    seen.add(key)
                    candidates.append(operation)
        return candidates

    def _load_packaged_schemas(self) -> None:
        """Load every bundled schema JSON file into the registry."""

        schema_root = resources.files("zoompy") / "schemas"
        for schema_path in self._iter_schema_files(schema_root):
            spec = json.loads(schema_path.read_text(encoding="utf-8"))
            schema_name = str(spec.get("info", {}).get("title", schema_path.stem))
            server_url = self._pick_server_url(spec)

            for path, path_item in spec.get("paths", {}).items():
                if not isinstance(path_item, Mapping):
                    continue

                for method in ("get", "post", "put", "patch", "delete"):
                    operation = path_item.get(method)
                    if not isinstance(operation, Mapping):
                        continue

                    compiled = re.compile(
                        "^" + re.sub(r"\{[^/]+\}", r"[^/]+", path) + "$"
                    )
                    entry = SchemaOperation(
                        schema_name=schema_name,
                        method=method.upper(),
                        template_path=path,
                        path_regex=compiled,
                        responses=operation.get("responses", {}),
                        spec=spec,
                        server_url=server_url,
                    )
                    prefix = self._path_prefix(path)
                    self._operations_by_prefix.setdefault(prefix, []).append(entry)

    def _iter_schema_files(self, root: Any) -> Iterable[Path]:
        """Recursively yield packaged JSON schema files.

        `importlib.resources.files()` returns a traversable object, not always a
        plain `Path`, so we use only the small subset of methods shared by both.
        """

        for child in root.iterdir():
            if child.is_dir():
                yield from self._iter_schema_files(child)
            elif child.name.endswith(".json"):
                yield Path(str(child))

    def _pick_server_url(self, spec: Mapping[str, Any]) -> str | None:
        """Return the primary server URL declared by one OpenAPI document.

        Zoom's OpenAPI files typically list several URLs near the top of the
        document, including documentation URLs such as `developer.zoom.us` and
        the actual API server URL. We specifically prefer `api.zoom.us`
        endpoints because those are the executable servers the client should
        call during real requests and test mocks.
        """

        servers = spec.get("servers")
        if not isinstance(servers, list):
            return None

        fallback: str | None = None
        for entry in servers:
            if not isinstance(entry, Mapping):
                continue

            url = entry.get("url")
            if not isinstance(url, str) or not url:
                continue

            cleaned = url.rstrip("/")
            if fallback is None:
                fallback = cleaned
            if "api.zoom.us" in cleaned:
                return cleaned

        return fallback

    def _path_prefix(self, path: str) -> str:
        """Return the leading path segment used for schema bucketing."""

        parts = [part for part in path.split("/") if part]
        return f"/{parts[0]}" if parts else "/"

    def _pick_response_schema(
        self,
        operation: SchemaOperation,
        status_code: int,
    ) -> Mapping[str, Any] | None:
        """Select the best matching response schema for one status code."""

        responses = operation.responses
        preferred_keys = [str(status_code)]
        preferred_keys.extend(
            key for key in responses if key.isdigit() and 200 <= int(key) < 300
        )
        preferred_keys.append("default")

        seen: set[str] = set()
        for key in preferred_keys:
            if key in seen:
                continue
            seen.add(key)

            response = responses.get(key)
            if not isinstance(response, Mapping):
                continue

            content = response.get("content")
            if not isinstance(content, Mapping):
                return None

            media = self._pick_json_media(content)
            if media is None:
                return None

            schema = media.get("schema")
            if isinstance(schema, Mapping):
                return schema
            return None

        return None

    def _pick_json_media(self, content: Mapping[str, Any]) -> Mapping[str, Any] | None:
        """Select a JSON-like media type block from an OpenAPI content map."""

        preferred = (
            "application/json",
            "application/json; charset=utf-8",
            "application/scim+json",
        )
        for key in preferred:
            candidate = content.get(key)
            if isinstance(candidate, Mapping):
                return candidate

        for media_type, candidate in content.items():
            if "json" in str(media_type) and isinstance(candidate, Mapping):
                return candidate
        return None

    def _resolve_ref(self, spec: Mapping[str, Any], ref: str) -> Any:
        """Resolve a local JSON Pointer reference inside an OpenAPI document."""

        if not ref.startswith("#/"):
            raise ValueError(f"Only local refs are supported, got: {ref}")

        current: Any = spec
        for part in ref.lstrip("#/").split("/"):
            if not isinstance(current, Mapping) or part not in current:
                raise ValueError(f"Unresolvable $ref: {ref}")
            current = current[part]
        return current

    def _resolve_schema(self, spec: Mapping[str, Any], schema: Any) -> Any:
        """Recursively inline local `$ref` values within a schema fragment."""

        if not isinstance(schema, Mapping):
            return schema

        if "$ref" in schema:
            target = self._resolve_ref(spec, str(schema["$ref"]))
            merged = dict(target) if isinstance(target, Mapping) else {"value": target}
            for key, value in schema.items():
                if key != "$ref":
                    merged[key] = value
            return self._resolve_schema(spec, merged)

        resolved: dict[str, Any] = {}
        for key, value in schema.items():
            if isinstance(value, Mapping):
                resolved[key] = self._resolve_schema(spec, value)
            elif isinstance(value, list):
                resolved[key] = [
                    self._resolve_schema(spec, item) for item in value
                ]
            else:
                resolved[key] = value
        return resolved

    def _normalize_schema(self, schema: Any) -> Any:
        """Normalize non-standard schema details before validation.

        Zoom's published OpenAPI documents are close to standard JSON Schema,
        but they occasionally contain small inconsistencies such as capitalized
        type names like `Integer`. The contract tests already tolerate those
        quirks, so the production validator should do the same. Otherwise users
        can receive validation failures that are artifacts of the published
        schema rather than problems in the API response itself.

        We keep normalization intentionally narrow. The goal is to smooth over
        known documentation irregularities, not to silently reinterpret whole
        schemas or weaken response validation semantics.
        """

        if isinstance(schema, Mapping):
            normalized: dict[str, Any] = {}
            for key, value in schema.items():
                if key == "type" and isinstance(value, str):
                    normalized[key] = self._normalize_type_name(value)
                elif isinstance(value, Mapping):
                    normalized[key] = self._normalize_schema(value)
                elif isinstance(value, list):
                    normalized[key] = [
                        self._normalize_schema(item) for item in value
                    ]
                else:
                    normalized[key] = value
            return normalized

        if isinstance(schema, list):
            return [self._normalize_schema(item) for item in schema]
        return schema

    def _normalize_type_name(self, value: str) -> str:
        """Return a canonical JSON Schema type name when one is recognizable."""

        lowered = value.lower()
        known_types = {
            "array",
            "boolean",
            "integer",
            "number",
            "object",
            "string",
        }
        if lowered in known_types:
            return lowered
        return value
