"""Companion API to create integrity-checkable stores."""

from __future__ import annotations

import inspect
import shutil
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any
from uuid import uuid4

import xarray as xr

from .integrity import check_store
from .layout import chunk_key, chunk_path, coord_in_bounds, expected_chunk_coords, scan_array_specs
from .manifest import MANIFEST_ROOT, load_variable_manifest, write_variable_manifest
from .models import ChunkRef, CreateReport, NoDataStrategy


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


def _to_zarr(
    dataset: xr.Dataset,
    store_path: Path,
    *,
    mode: str = "w",
    write_empty_chunks: bool = True,
    consolidated: bool = False,
    extra_kwargs: Mapping[str, Any] | None = None,
) -> None:
    params = inspect.signature(dataset.to_zarr).parameters
    kwargs: dict[str, Any] = {"store": store_path, "mode": mode}
    user_has_zarr_param = bool(
        extra_kwargs
        and ("zarr_format" in extra_kwargs or "zarr_version" in extra_kwargs)
    )
    if not user_has_zarr_param:
        if "zarr_format" in params:
            kwargs["zarr_format"] = 3
        elif "zarr_version" in params:
            kwargs["zarr_version"] = 3
        else:
            raise ValueError("xarray.to_zarr does not expose zarr_format/zarr_version")
    elif "zarr_format" not in params and "zarr_version" not in params:
        raise ValueError("xarray.to_zarr does not expose zarr_format/zarr_version")
    if "write_empty_chunks" in params and "write_empty_chunks" not in kwargs:
        kwargs["write_empty_chunks"] = write_empty_chunks
    if "consolidated" in params and "consolidated" not in kwargs:
        kwargs["consolidated"] = consolidated
    if extra_kwargs:
        for key, value in extra_kwargs.items():
            if key == "store":
                raise ValueError("'store' must not be provided in extra to_zarr kwargs")
            kwargs[key] = value
    dataset.to_zarr(**kwargs)


def _write_dataset(dataset: xr.Dataset, store_path: Path) -> None:
    _to_zarr(dataset, store_path)


def _delete_chunk_file(chunk_file: Path, array_root: Path) -> None:
    if not chunk_file.exists():
        return
    chunk_file.unlink()
    current = chunk_file.parent
    while current != array_root and current.exists() and not any(current.iterdir()):
        current.rmdir()
        current = current.parent


def _staging_manifest_root() -> Path:
    return MANIFEST_ROOT.parent / f"manifests.staging-{uuid4().hex}"


def _backup_manifest_root() -> Path:
    return MANIFEST_ROOT.parent / f"manifests.backup-{uuid4().hex}"


def _prepare_staged_manifests(store: Path, staged_root: Path) -> Path:
    staged_dir = store / staged_root
    source_dir = store / MANIFEST_ROOT
    if source_dir.exists():
        shutil.copytree(source_dir, staged_dir)
    else:
        staged_dir.mkdir(parents=True, exist_ok=True)
    return staged_dir


def _swap_staged_manifests(store: Path, staged_root: Path) -> None:
    active_dir = store / MANIFEST_ROOT
    staged_dir = store / staged_root
    backup_root = _backup_manifest_root()
    backup_dir = store / backup_root

    moved_active = False
    try:
        if active_dir.exists():
            active_dir.replace(backup_dir)
            moved_active = True
        staged_dir.replace(active_dir)
    except Exception:
        if moved_active and backup_dir.exists() and not active_dir.exists():
            backup_dir.replace(active_dir)
        if staged_dir.exists():
            shutil.rmtree(staged_dir, ignore_errors=True)
        raise
    finally:
        if backup_dir.exists():
            shutil.rmtree(backup_dir, ignore_errors=True)


def _update_store_metadata_in_place(
    store: Path,
    *,
    no_data_chunks: dict[str, list[tuple[int, ...]]],
    infer_no_data_from_store: bool = False,
) -> CreateReport:
    if infer_no_data_from_store and no_data_chunks:
        raise ValueError(
            "infer_no_data_from_store=True cannot be combined with explicit no_data_chunks"
        )

    specs = {spec.name: spec for spec in scan_array_specs(store)}
    if not infer_no_data_from_store:
        unknown = sorted(set(no_data_chunks) - set(specs))
        if unknown:
            raise ValueError(f"Unknown variables in no_data_chunks: {', '.join(unknown)}")

    report = CreateReport(store_path=str(store), no_data_strategy="manifest")
    staged_root = _staging_manifest_root()
    if infer_no_data_from_store:
        staged_dir = store / staged_root
        staged_dir.mkdir(parents=True, exist_ok=True)
    else:
        staged_dir = _prepare_staged_manifests(store, staged_root)

    try:
        if infer_no_data_from_store:
            for spec in specs.values():
                refs: list[ChunkRef] = []
                for coord in expected_chunk_coords(spec):
                    if chunk_path(spec, coord).exists():
                        continue
                    refs.append(ChunkRef(coord=coord, key=chunk_key(spec, coord)))
                if not refs:
                    continue
                staged_path = write_variable_manifest(
                    store,
                    spec.name,
                    refs,
                    manifest_root=staged_root,
                )
                report.manifests_written.append(str((store / MANIFEST_ROOT / staged_path.name)))
        else:
            for variable, coords in no_data_chunks.items():
                spec = specs[variable]
                _, existing_refs = load_variable_manifest(
                    store,
                    variable,
                    manifest_root=staged_root,
                )
                merged = {ref.coord: ref for ref in existing_refs}

                for coord in coords:
                    if not coord_in_bounds(spec, coord):
                        raise ValueError(f"Chunk coord {coord} out of bounds for variable {variable}")
                    ref = ChunkRef(coord=coord, key=chunk_key(spec, coord))
                    if chunk_path(spec, coord).exists():
                        raise ValueError(
                            "In-place manifest update only accepts currently missing chunks: "
                            f"{variable}:{coord}"
                        )
                    merged[coord] = ref

                merged_refs = [merged[coord] for coord in sorted(merged)]
                staged_path = write_variable_manifest(
                    store,
                    variable,
                    merged_refs,
                    manifest_root=staged_root,
                )
                report.manifests_written.append(str((store / MANIFEST_ROOT / staged_path.name)))

        integrity = check_store(store, _manifest_root=staged_root)
        if not integrity.ok:
            raise RuntimeError("In-place metadata update would fail integrity validation")

        _swap_staged_manifests(store, staged_root)
        return report
    except Exception:
        if staged_dir.exists():
            shutil.rmtree(staged_dir, ignore_errors=True)
        raise


def create_store(
    dataset: xr.Dataset | None,
    store_path: str | Path,
    *,
    no_data_chunks: Mapping[str, Iterable[Iterable[int]]] | None = None,
    no_data_strategy: NoDataStrategy = "manifest",
    overwrite: bool = False,
    in_place_metadata_only: bool = False,
    infer_no_data_from_store: bool = False,
) -> CreateReport:
    """Create a Zarr v3 store with explicit no-data policy."""

    if no_data_strategy not in {"manifest", "empty_chunks"}:
        raise ValueError("no_data_strategy must be 'manifest' or 'empty_chunks'")

    normalized = _normalize_chunks(no_data_chunks)
    store = Path(store_path)

    if in_place_metadata_only:
        if no_data_strategy != "manifest":
            raise ValueError("in_place_metadata_only requires no_data_strategy='manifest'")
        if overwrite:
            raise ValueError("in_place_metadata_only does not support overwrite")
        if not store.exists():
            raise FileNotFoundError(f"Store does not exist: {store}")
        if not store.is_dir():
            raise NotADirectoryError(f"Store path is not a directory: {store}")
        return _update_store_metadata_in_place(
            store,
            no_data_chunks=normalized,
            infer_no_data_from_store=infer_no_data_from_store,
        )

    if infer_no_data_from_store:
        raise ValueError("infer_no_data_from_store is only supported with in_place_metadata_only=True")

    if dataset is None:
        raise ValueError("dataset is required unless in_place_metadata_only=True")

    if store.exists():
        if not overwrite:
            raise FileExistsError(f"Store already exists: {store}")
        shutil.rmtree(store)

    store.parent.mkdir(parents=True, exist_ok=True)
    _write_dataset(dataset, store)

    specs = {spec.name: spec for spec in scan_array_specs(store)}
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


def guarded_to_zarr(
    dataset: xr.Dataset,
    store_path: str | Path,
    *,
    overwrite: bool = False,
    infer_no_data_from_store: bool = True,
    no_data_chunks: Mapping[str, Iterable[Iterable[int]]] | None = None,
    to_zarr_kwargs: Mapping[str, Any] | None = None,
) -> CreateReport:
    """Write a Zarr v3 store and immediately guard it with xzarrguard manifests.

    By default, this treats the freshly written store as ground truth and records
    all currently missing chunks as allowed-missing manifests.
    """

    store = Path(store_path)
    if store.exists():
        if not overwrite:
            raise FileExistsError(f"Store already exists: {store}")
        shutil.rmtree(store)

    store.parent.mkdir(parents=True, exist_ok=True)
    _to_zarr(dataset, store, extra_kwargs=to_zarr_kwargs)
    return create_store(
        None,
        store,
        no_data_chunks=no_data_chunks,
        in_place_metadata_only=True,
        infer_no_data_from_store=infer_no_data_from_store,
    )
