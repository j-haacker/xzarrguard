"""Companion API to create integrity-checkable stores."""

from __future__ import annotations

import inspect
import shutil
from collections.abc import Iterable, Mapping
from pathlib import Path

import xarray as xr

from .integrity import check_store
from .layout import chunk_key, chunk_path, coord_in_bounds, scan_array_specs
from .manifest import write_variable_manifest
from .models import ChunkRef, CreateReport


def _normalize_chunks(
    chunks: Mapping[str, Iterable[Iterable[int]]] | None,
) -> dict[str, list[tuple[int, ...]]]:
    normalized: dict[str, list[tuple[int, ...]]] = {}
    if not chunks:
        return normalized
    for variable, coords in chunks.items():
        parsed = [tuple(int(value) for value in coord) for coord in coords]
        normalized[str(variable)] = sorted(set(parsed))
    return normalized


def _write_dataset(dataset: xr.Dataset, store_path: Path) -> None:
    params = inspect.signature(dataset.to_zarr).parameters
    kwargs: dict[str, object] = {"store": store_path, "mode": "w"}
    if "zarr_format" in params:
        kwargs["zarr_format"] = 3
    elif "zarr_version" in params:
        kwargs["zarr_version"] = 3
    else:
        raise ValueError("xarray.to_zarr does not expose zarr_format/zarr_version")
    if "write_empty_chunks" in params:
        kwargs["write_empty_chunks"] = True
    if "consolidated" in params:
        kwargs["consolidated"] = False
    dataset.to_zarr(**kwargs)


def _delete_chunk_file(chunk_file: Path, array_root: Path) -> None:
    if not chunk_file.exists():
        return
    chunk_file.unlink()
    current = chunk_file.parent
    while current != array_root and current.exists() and not any(current.iterdir()):
        current.rmdir()
        current = current.parent


def create_store(
    dataset: xr.Dataset,
    store_path: str | Path,
    *,
    no_data_chunks: Mapping[str, Iterable[Iterable[int]]] | None = None,
    no_data_strategy: str = "manifest",
    overwrite: bool = False,
) -> CreateReport:
    """Create a Zarr v3 store with explicit no-data policy."""

    if no_data_strategy not in {"manifest", "empty_chunks"}:
        raise ValueError("no_data_strategy must be 'manifest' or 'empty_chunks'")

    store = Path(store_path)
    if store.exists():
        if not overwrite:
            raise FileExistsError(f"Store already exists: {store}")
        shutil.rmtree(store)

    store.parent.mkdir(parents=True, exist_ok=True)
    _write_dataset(dataset, store)

    specs = {spec.name: spec for spec in scan_array_specs(store)}
    normalized = _normalize_chunks(no_data_chunks)

    unknown = sorted(set(normalized) - set(specs))
    if unknown:
        raise ValueError(f"Unknown variables in no_data_chunks: {', '.join(unknown)}")

    report = CreateReport(store_path=str(store), no_data_strategy=no_data_strategy)

    for variable, coords in normalized.items():
        spec = specs[variable]
        refs: list[ChunkRef] = []
        removed: list[ChunkRef] = []
        for coord in coords:
            if not coord_in_bounds(spec, coord):
                raise ValueError(f"Chunk coord {coord} out of bounds for variable {variable}")
            ref = ChunkRef(coord=coord, key=chunk_key(spec, coord))
            refs.append(ref)
            if no_data_strategy == "manifest":
                _delete_chunk_file(chunk_path(spec, coord), spec.path)
                removed.append(ref)
            elif not chunk_path(spec, coord).exists():
                raise RuntimeError(
                    "Expected chunk file missing after write_empty_chunks=True: "
                    f"{variable}:{coord}"
                )

        if no_data_strategy == "manifest":
            manifest_file = write_variable_manifest(store, variable, refs)
            report.manifests_written.append(str(manifest_file))
            report.removed_chunks[variable] = removed

    integrity = check_store(store)
    if not integrity.ok:
        raise RuntimeError("Created store failed integrity validation")

    return report
