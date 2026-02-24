from __future__ import annotations

import inspect
from pathlib import Path

import numpy as np
import pytest
import xarray as xr

from xzarrguard import check_store, create_store
from xzarrguard.layout import chunk_key, chunk_path, scan_array_specs
from xzarrguard.manifest import load_no_data_chunks, write_variable_manifest
from xzarrguard.models import ChunkRef


def _dataset() -> xr.Dataset:
    ds = xr.Dataset(
        {
            "var": (("x", "y"), np.arange(16, dtype=np.float32).reshape(4, 4)),
        },
        coords={"x": np.arange(4), "y": np.arange(4)},
    )
    ds["var"].encoding["chunks"] = (2, 2)
    return ds


def _delete_chunk(store_path: Path, variable: str, coord: tuple[int, ...]) -> None:
    spec = next(item for item in scan_array_specs(store_path) if item.name == variable)
    path = chunk_path(spec, coord)
    path.unlink()


def _write_source_store(dataset: xr.Dataset, store_path: Path) -> None:
    params = inspect.signature(dataset.to_zarr).parameters
    kwargs: dict[str, object] = {"store": store_path, "mode": "w"}
    if "zarr_format" in params:
        kwargs["zarr_format"] = 3
    else:
        kwargs["zarr_version"] = 3
    if "write_empty_chunks" in params:
        kwargs["write_empty_chunks"] = True
    if "consolidated" in params:
        kwargs["consolidated"] = False
    dataset.to_zarr(**kwargs)


def test_check_passes_complete_store_without_manifest(tmp_path: Path) -> None:
    store = tmp_path / "store.zarr"
    create_store(_dataset(), store, no_data_strategy="empty_chunks")

    report = check_store(store)

    assert report.ok
    assert bool(report)


def test_check_fails_missing_chunk_without_manifest(tmp_path: Path) -> None:
    store = tmp_path / "store.zarr"
    create_store(_dataset(), store, no_data_strategy="empty_chunks")
    _delete_chunk(store, "var", (0, 0))

    report = check_store(store)

    assert not report.ok
    assert not bool(report)
    assert report.variables["var"].missing_unexpected


def test_check_passes_when_missing_is_manifested(tmp_path: Path) -> None:
    store = tmp_path / "store.zarr"
    create_store(_dataset(), store, no_data_chunks={"var": [(0, 0)]})

    report = check_store(store)

    assert report.ok
    assert len(report.variables["var"].missing_allowed) == 1


def test_check_fails_when_missing_not_manifested(tmp_path: Path) -> None:
    store = tmp_path / "store.zarr"
    create_store(_dataset(), store, no_data_chunks={"var": [(0, 0)]})
    _delete_chunk(store, "var", (1, 1))

    report = check_store(store)

    assert not report.ok
    assert any(item.coord == (1, 1) for item in report.variables["var"].missing_unexpected)


def test_stale_manifest_behavior_strict_and_non_strict(tmp_path: Path) -> None:
    store = tmp_path / "store.zarr"
    create_store(_dataset(), store, no_data_strategy="empty_chunks")

    spec = next(item for item in scan_array_specs(store) if item.name == "var")
    write_variable_manifest(
        store,
        "var",
        [ChunkRef(coord=(0, 0), key=chunk_key(spec, (0, 0)))],
    )

    loose = check_store(store)
    strict = check_store(store, strict_stale_manifest=True)

    assert loose.ok
    assert loose.variables["var"].stale_manifest
    assert not strict.ok


def test_create_manifest_strategy_roundtrip(tmp_path: Path) -> None:
    store = tmp_path / "store.zarr"

    report = create_store(_dataset(), store, no_data_chunks={"var": [(0, 1)]}, no_data_strategy="manifest")
    check = check_store(store)

    assert report.ok
    assert report.manifests_written
    assert check.ok


def test_create_empty_chunks_strategy_roundtrip(tmp_path: Path) -> None:
    store = tmp_path / "store.zarr"

    report = create_store(_dataset(), store, no_data_chunks={"var": [(0, 1)]}, no_data_strategy="empty_chunks")
    check = check_store(store)

    assert report.ok
    assert not report.manifests_written
    assert check.ok


def test_load_no_data_mapping_validation(tmp_path: Path) -> None:
    path = tmp_path / "bad.json"
    path.write_text("[]", encoding="utf-8")

    with pytest.raises(ValueError):
        load_no_data_chunks(path)


def test_create_unknown_variable_fails(tmp_path: Path) -> None:
    store = tmp_path / "store.zarr"

    with pytest.raises(ValueError):
        create_store(_dataset(), store, no_data_chunks={"missing": [(0, 0)]})


def test_helper_write_source_store(tmp_path: Path) -> None:
    source = tmp_path / "source.zarr"

    _write_source_store(_dataset(), source)

    assert source.exists()
