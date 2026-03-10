"""OpenAPI schema loading and response validation for `zoompy`.

The client always validates JSON responses against the bundled OpenAPI schema
files. This module owns that behavior so request execution code stays focused on
HTTP mechanics rather than schema traversal.
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


class SchemaRegistry:
    """Index packaged OpenAPI schema files for fast operation lookup.

    The registry builds a small prefix index so we do not need to scan every
    single operation for every request. That said, correctness is more
    important than theoretical performance here, so the implementation stays
    intentionally straightforward and readable.
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

        resolved_schema = self._resolve_schema(operation.spec, schema)
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
