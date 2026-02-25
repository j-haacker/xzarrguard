"""Zarr v3 local-store layout helpers."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from itertools import product
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class ArraySpec:
    """Minimal metadata needed for chunk validation."""

    name: str
    path: Path
    shape: tuple[int, ...]
    chunk_shape: tuple[int, ...]
    chunk_key_encoding: str
    separator: str


def _parse_array_spec(
    *,
    store_path: Path,
    array_name: str,
    array_path: Path,
    payload: dict[str, Any],
    source: Path | str,
) -> ArraySpec | None:
    if payload.get("zarr_format") != 3:
        raise ValueError(f"Only zarr_format=3 is supported: {source}")
    if payload.get("node_type") != "array":
        return None

    shape = tuple(int(v) for v in payload["shape"])
    chunk_grid = payload.get("chunk_grid", {})
    if chunk_grid.get("name") != "regular":
        raise ValueError(f"Only regular chunk grids are supported: {source}")
    chunk_shape = tuple(int(v) for v in chunk_grid["configuration"]["chunk_shape"])

    encoding = payload.get("chunk_key_encoding") or {
        "name": "default",
        "configuration": {"separator": "/"},
    }
    encoding_name = str(encoding.get("name", "default"))
    config = encoding.get("configuration", {})
    default_separator = "/" if encoding_name == "default" else "."
    separator = str(config.get("separator", default_separator))

    if not array_name:
        rel_dir = array_path.relative_to(store_path)
        array_name = "/".join(rel_dir.parts)

    return ArraySpec(
        name=array_name,
        path=array_path,
        shape=shape,
        chunk_shape=chunk_shape,
        chunk_key_encoding=encoding_name,
        separator=separator,
    )


def _scan_from_consolidated_metadata(store_path: Path) -> list[ArraySpec]:
    root_meta_path = store_path / "zarr.json"
    if not root_meta_path.exists():
        return []

    root_payload = json.loads(root_meta_path.read_text(encoding="utf-8"))
    if root_payload.get("zarr_format") != 3:
        raise ValueError(f"Only zarr_format=3 is supported: {root_meta_path}")

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
        array_path = store_path / Path(name) if name else store_path
        spec = _parse_array_spec(
            store_path=store_path,
            array_name=name,
            array_path=array_path,
            payload=payload,
            source=f"{root_meta_path} consolidated_metadata[{name!r}]",
        )
        if spec is not None:
            specs.append(spec)
    return specs


def scan_array_specs(store_path: Path) -> list[ArraySpec]:
    """Return every array spec found in a local Zarr v3 store."""

    specs = _scan_from_consolidated_metadata(store_path)
    if specs:
        specs.sort(key=lambda item: item.name)
        return specs

    specs: list[ArraySpec] = []
    stack: list[Path] = [store_path]
    while stack:
        node_path = stack.pop()
        if ".xzarrguard" in node_path.parts:
            continue

        meta_path = node_path / "zarr.json"
        if not meta_path.exists():
            continue

        payload = json.loads(meta_path.read_text(encoding="utf-8"))
        node_type = payload.get("node_type")
        if node_type == "group":
            for child in sorted(node_path.iterdir(), reverse=True):
                if not child.is_dir() or child.name == ".xzarrguard":
                    continue
                child_meta = child / "zarr.json"
                if child_meta.exists():
                    stack.append(child)
            continue
        spec = _parse_array_spec(
            store_path=store_path,
            array_name="",
            array_path=meta_path.parent,
            payload=payload,
            source=meta_path,
        )
        if spec is not None:
            specs.append(spec)
    specs.sort(key=lambda item: item.name)
    return specs


def chunk_counts(spec: ArraySpec) -> tuple[int, ...]:
    """Return number of chunks per dimension."""

    if len(spec.shape) != len(spec.chunk_shape):
        raise ValueError(f"Shape/chunk rank mismatch for {spec.name}")
    return tuple(
        math.ceil(size / chunk) for size, chunk in zip(spec.shape, spec.chunk_shape, strict=True)
    )


def expected_chunk_coords(spec: ArraySpec):
    """Yield all expected chunk coordinates."""

    counts = chunk_counts(spec)
    if not counts:
        yield ()
        return
    for coord in product(*(range(n) for n in counts)):
        yield tuple(int(v) for v in coord)


def coord_in_bounds(spec: ArraySpec, coord: tuple[int, ...]) -> bool:
    """Check whether a chunk coordinate is valid for this array."""

    counts = chunk_counts(spec)
    if len(coord) != len(counts):
        return False
    return all(0 <= index < count for index, count in zip(coord, counts, strict=True))


def chunk_key(spec: ArraySpec, coord: tuple[int, ...]) -> str:
    """Encode chunk coordinates according to Zarr chunk_key_encoding."""

    if spec.chunk_key_encoding == "default":
        if not coord:
            return "c"
        return f"c{spec.separator}" + spec.separator.join(str(v) for v in coord)
    if spec.chunk_key_encoding == "v2":
        return "0" if not coord else spec.separator.join(str(v) for v in coord)
    raise ValueError(f"Unsupported chunk_key_encoding '{spec.chunk_key_encoding}' for {spec.name}")


def chunk_path(spec: ArraySpec, coord: tuple[int, ...]) -> Path:
    """Return the chunk file path for a coordinate."""

    return spec.path / chunk_key(spec, coord)
