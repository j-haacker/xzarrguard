"""Manifest read/write helpers."""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from pathlib import Path
from urllib.parse import quote

from .models import ChunkRef

MANIFEST_SCHEMA_VERSION = 1
MANIFEST_ROOT = Path(".xzarrguard") / "manifests"


def _normalize_coord(coord: Iterable[int]) -> tuple[int, ...]:
    return tuple(int(item) for item in coord)


def _normalize_mapping(
    mapping: Mapping[str, Iterable[Iterable[int]]] | None,
) -> dict[str, list[tuple[int, ...]]]:
    normalized: dict[str, list[tuple[int, ...]]] = {}
    if not mapping:
        return normalized

    for variable, coords in mapping.items():
        parsed = [_normalize_coord(coord) for coord in coords]
        unique = sorted(set(parsed))
        normalized[str(variable)] = unique
    return normalized


def load_no_data_chunks(path: str | Path) -> dict[str, list[tuple[int, ...]]]:
    """Load variable->chunk-coordinate mapping from JSON."""

    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("No-data mapping must be an object")
    mapping = {
        str(name): [tuple(int(v) for v in coord) for coord in coords]
        for name, coords in payload.items()
    }
    return _normalize_mapping(mapping)


def dump_no_data_chunks(
    path: str | Path,
    mapping: Mapping[str, Iterable[Iterable[int]]] | None,
) -> None:
    """Write variable->chunk-coordinate mapping to JSON."""

    normalized = _normalize_mapping(mapping)
    serializable = {
        variable: [list(coord) for coord in coords]
        for variable, coords in sorted(normalized.items(), key=lambda item: item[0])
    }
    Path(path).write_text(
        json.dumps(serializable, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def manifest_path(store_path: str | Path, variable: str) -> Path:
    """Return manifest path for one variable."""

    safe_name = quote(variable, safe="")
    return Path(store_path) / MANIFEST_ROOT / f"{safe_name}.json"


def load_variable_manifest(store_path: str | Path, variable: str) -> tuple[bool, list[ChunkRef]]:
    """Read a single variable manifest."""

    path = manifest_path(store_path, variable)
    if not path.exists():
        return False, []

    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != MANIFEST_SCHEMA_VERSION:
        raise ValueError(f"Unsupported manifest schema in {path}")

    items = payload.get("allowed_missing", [])
    refs = [ChunkRef(coord=_normalize_coord(item["coord"]), key=str(item["key"])) for item in items]
    return True, refs


def write_variable_manifest(
    store_path: str | Path,
    variable: str,
    refs: Iterable[ChunkRef],
    *,
    zarr_format: int = 3,
) -> Path:
    """Write a single variable manifest file."""

    path = manifest_path(store_path, variable)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "zarr_format": zarr_format,
        "variable": variable,
        "allowed_missing": [{"coord": list(ref.coord), "key": ref.key} for ref in refs],
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path
