"""Remote-store helpers for integrity checks."""

from __future__ import annotations

import json
import posixpath
from collections.abc import Mapping
from pathlib import PurePosixPath
from typing import Any
from urllib.parse import quote

from fsspec.core import url_to_fs

from .layout import ArraySpec, _parse_array_spec
from .manifest import MANIFEST_SCHEMA_VERSION
from .models import ChunkRef


def is_remote_store_path(store_path: str | PurePosixPath | Any) -> bool:
    """Return whether the supplied store path is an fsspec-style URI."""

    return isinstance(store_path, str) and "://" in store_path


def open_remote_store(
    store_path: str,
    *,
    storage_options: Mapping[str, Any] | None = None,
) -> tuple[Any, str]:
    """Return the filesystem and root key for a remote store URI."""

    fs, root = url_to_fs(store_path, **dict(storage_options or {}))
    return fs, _normalize_key(root)


def scan_remote_array_specs(fs: Any, root_key: str) -> list[ArraySpec]:
    """Return every array spec found in a remote Zarr v3 store."""

    specs = _scan_remote_from_consolidated_metadata(fs, root_key)
    if specs:
        specs.sort(key=lambda item: item.name)
        return specs

    zarr_json_key = _join_key(root_key, "zarr.json")
    zarr_json_suffix = "/zarr.json"
    specs = []
    for meta_key in sorted(fs.find(root_key)):
        normalized_key = _normalize_key(meta_key)
        if normalized_key != zarr_json_key and not normalized_key.endswith(zarr_json_suffix):
            continue

        node_dir = _normalize_key(posixpath.dirname(normalized_key))
        rel_dir = posixpath.relpath(node_dir, root_key)
        if rel_dir != "." and ".xzarrguard" in PurePosixPath(rel_dir).parts:
            continue

        payload = json.loads(_read_text(fs, normalized_key))
        spec = _parse_array_spec(
            store_path=PurePosixPath(root_key),
            array_name="",
            array_path=PurePosixPath(node_dir),
            payload=payload,
            source=normalized_key,
        )
        if spec is not None:
            specs.append(spec)

    specs.sort(key=lambda item: item.name)
    return specs


def load_remote_variable_manifest(
    fs: Any,
    root_key: str,
    variable: str,
    *,
    manifest_root: str | PurePosixPath,
) -> tuple[bool, list[ChunkRef]]:
    """Read a single manifest from a remote store."""

    manifest_key = _join_key(
        root_key,
        _manifest_root_text(manifest_root),
        f"{quote(variable, safe='')}.json",
    )
    if not fs.exists(manifest_key):
        return False, []

    payload = json.loads(_read_text(fs, manifest_key))
    if payload.get("schema_version") != MANIFEST_SCHEMA_VERSION:
        raise ValueError(f"Unsupported manifest schema in {manifest_key}")
    items = payload.get("allowed_missing", [])
    refs = [
        ChunkRef(
            coord=tuple(int(value) for value in item["coord"]),
            key=str(item["key"]),
        )
        for item in items
    ]
    return True, refs


def remote_existing_chunk_keys(fs: Any, spec: ArraySpec) -> set[str]:
    """Return the chunk keys currently materialized for one remote array."""

    array_root = _spec_path_text(spec)
    zarr_json_key = _join_key(array_root, "zarr.json")
    result: set[str] = set()
    for key in fs.find(array_root):
        normalized = _normalize_key(key)
        if normalized == zarr_json_key:
            continue
        rel = posixpath.relpath(normalized, array_root)
        if rel in {".", "zarr.json"}:
            continue
        result.add(rel)
    return result


def _scan_remote_from_consolidated_metadata(fs: Any, root_key: str) -> list[ArraySpec]:
    root_meta_key = _join_key(root_key, "zarr.json")
    if not fs.exists(root_meta_key):
        return []

    root_payload = json.loads(_read_text(fs, root_meta_key))
    if root_payload.get("zarr_format") != 3:
        raise ValueError(f"Only zarr_format=3 is supported: {root_meta_key}")

    consolidated = root_payload.get("consolidated_metadata")
    if not isinstance(consolidated, dict):
        return []
    metadata = consolidated.get("metadata")
    if not isinstance(metadata, dict):
        return []

    specs: list[ArraySpec] = []
    for name, payload in metadata.items():
        if not isinstance(name, str) or not isinstance(payload, dict):
            continue
        array_path = PurePosixPath(_join_key(root_key, name)) if name else PurePosixPath(root_key)
        spec = _parse_array_spec(
            store_path=PurePosixPath(root_key),
            array_name=name,
            array_path=array_path,
            payload=payload,
            source=f"{root_meta_key} consolidated_metadata[{name!r}]",
        )
        if spec is not None:
            specs.append(spec)
    return specs


def _manifest_root_text(manifest_root: str | PurePosixPath) -> str:
    if isinstance(manifest_root, PurePosixPath):
        return manifest_root.as_posix().strip("/")
    return str(manifest_root).replace("\\", "/").strip("/")


def _normalize_key(key: str) -> str:
    if key in {"", "."}:
        return ""
    normalized = posixpath.normpath(key)
    if normalized == ".":
        return ""
    return normalized


def _join_key(base: str, *parts: str) -> str:
    current = _normalize_key(base)
    for part in parts:
        cleaned = str(part).replace("\\", "/").strip("/")
        if not cleaned:
            continue
        if current in {"", "."}:
            current = cleaned
        elif current == "/":
            current = f"/{cleaned}"
        else:
            current = posixpath.join(current, cleaned)
    return current


def _read_text(fs: Any, key: str) -> str:
    with fs.open(key, "rb") as handle:
        payload = handle.read()
    if isinstance(payload, bytes):
        return payload.decode("utf-8")
    return str(payload)


def _spec_path_text(spec: ArraySpec) -> str:
    path = spec.path
    if isinstance(path, PurePosixPath):
        return path.as_posix()
    return str(path).replace("\\", "/")
