"""Zarr v3 local-store layout helpers."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from itertools import product
from pathlib import Path


@dataclass(frozen=True, slots=True)
class ArraySpec:
    """Minimal metadata needed for chunk validation."""

    name: str
    path: Path
    shape: tuple[int, ...]
    chunk_shape: tuple[int, ...]
    chunk_key_encoding: str
    separator: str


def scan_array_specs(store_path: Path) -> list[ArraySpec]:
    """Return every array spec found in a local Zarr v3 store."""

    specs: list[ArraySpec] = []
    for meta_path in sorted(store_path.rglob("zarr.json")):
        if ".xzarrguard" in meta_path.parts:
            continue
        payload = json.loads(meta_path.read_text(encoding="utf-8"))
        if payload.get("zarr_format") != 3:
            raise ValueError(f"Only zarr_format=3 is supported: {meta_path}")
        if payload.get("node_type") != "array":
            continue

        shape = tuple(int(v) for v in payload["shape"])
        chunk_grid = payload.get("chunk_grid", {})
        if chunk_grid.get("name") != "regular":
            raise ValueError(f"Only regular chunk grids are supported: {meta_path}")
        chunk_shape = tuple(int(v) for v in chunk_grid["configuration"]["chunk_shape"])

        encoding = payload.get("chunk_key_encoding") or {
            "name": "default",
            "configuration": {"separator": "/"},
        }
        encoding_name = str(encoding.get("name", "default"))
        config = encoding.get("configuration", {})
        default_separator = "/" if encoding_name == "default" else "."
        separator = str(config.get("separator", default_separator))

        rel_dir = meta_path.parent.relative_to(store_path)
        array_name = "/".join(rel_dir.parts)
        specs.append(
            ArraySpec(
                name=array_name,
                path=meta_path.parent,
                shape=shape,
                chunk_shape=chunk_shape,
                chunk_key_encoding=encoding_name,
                separator=separator,
            )
        )
    return specs


def chunk_counts(spec: ArraySpec) -> tuple[int, ...]:
    """Return number of chunks per dimension."""

    if len(spec.shape) != len(spec.chunk_shape):
        raise ValueError(f"Shape/chunk rank mismatch for {spec.name}")
    return tuple(math.ceil(size / chunk) for size, chunk in zip(spec.shape, spec.chunk_shape, strict=True))


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
        return "c" if not coord else f"c{spec.separator}" + spec.separator.join(str(v) for v in coord)
    if spec.chunk_key_encoding == "v2":
        return "0" if not coord else spec.separator.join(str(v) for v in coord)
    raise ValueError(f"Unsupported chunk_key_encoding '{spec.chunk_key_encoding}' for {spec.name}")


def chunk_path(spec: ArraySpec, coord: tuple[int, ...]) -> Path:
    """Return the chunk file path for a coordinate."""

    return spec.path / chunk_key(spec, coord)
