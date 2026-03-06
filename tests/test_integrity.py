from __future__ import annotations

import inspect
import json
from pathlib import Path

import fsspec
import numpy as np
import pytest
import xarray as xr

from xzarrguard import (
    ConvertDirection,
    ConvertReport,
    NoDataStrategy,
    check_store,
    convert_store,
    create_store,
    guarded_to_zarr,
)
from xzarrguard.layout import chunk_key, chunk_path, scan_array_specs
from xzarrguard.manifest import (
    load_no_data_chunks,
    load_variable_manifest,
    manifest_path,
    write_variable_manifest,
)
from xzarrguard.models import (
    ChunkRef,
)
from xzarrguard.models import (
    ConvertDirection as ModelsConvertDirection,
)
from xzarrguard.models import (
    NoDataStrategy as ModelsNoDataStrategy,
)


def _dataset() -> xr.Dataset:
    ds = xr.Dataset(
        {
            "var": (("x", "y"), np.arange(16, dtype=np.float32).reshape(4, 4)),
        },
        coords={"x": np.arange(4), "y": np.arange(4)},
    )
    ds["var"].encoding["chunks"] = (2, 2)
    return ds


def _dataset_with_nan_chunk() -> xr.Dataset:
    ds = _dataset().copy(deep=True)
    ds["var"].values[0:2, 0:2] = np.nan
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


def _remote_group_meta(*, metadata: dict[str, dict] | None = None) -> dict:
    payload: dict[str, object] = {"zarr_format": 3, "node_type": "group", "attributes": {}}
    if metadata is not None:
        payload["consolidated_metadata"] = {
            "kind": "inline",
            "must_understand": False,
            "metadata": metadata,
        }
    return payload


def _remote_array_meta(shape: tuple[int, ...], chunk_shape: tuple[int, ...]) -> dict:
    return {
        "zarr_format": 3,
        "node_type": "array",
        "shape": list(shape),
        "chunk_grid": {"name": "regular", "configuration": {"chunk_shape": list(chunk_shape)}},
        "chunk_key_encoding": {"name": "default", "configuration": {"separator": "/"}},
    }


def _write_remote_memory_store(
    store_uri: str,
    *,
    missing_manifested: list[tuple[int, ...]] | None = None,
    missing_unexpected: list[tuple[int, ...]] | None = None,
) -> None:
    fs = fsspec.filesystem("memory")
    root = "/" + store_uri.split("://", 1)[1].lstrip("/")
    if fs.exists(root):
        fs.rm(root, recursive=True)

    with fs.open(f"{root}/zarr.json", "w") as handle:
        json.dump(
            _remote_group_meta(metadata={"var": _remote_array_meta((4, 4), (2, 2))}),
            handle,
        )

    missing_manifested = missing_manifested or []
    missing_unexpected = missing_unexpected or []
    for coord in ((0, 0), (0, 1), (1, 0), (1, 1)):
        if coord in missing_manifested or coord in missing_unexpected:
            continue
        with fs.open(f"{root}/var/c/{coord[0]}/{coord[1]}", "wb") as handle:
            handle.write(b"chunk")

    if missing_manifested:
        with fs.open(f"{root}/.xzarrguard/manifests/var.json", "w") as handle:
            json.dump(
                {
                    "schema_version": 1,
                    "zarr_format": 3,
                    "variable": "var",
                    "allowed_missing": [
                        {"coord": list(coord), "key": f"c/{coord[0]}/{coord[1]}"}
                        for coord in missing_manifested
                    ],
                },
                handle,
            )


def test_check_passes_complete_store_without_manifest(tmp_path: Path) -> None:
    store = tmp_path / "store.zarr"
    create_store(_dataset(), store, no_data_strategy="empty_chunks")

    report = check_store(store)

    assert report.ok
    assert bool(report)


def test_public_api_exports_convert_models() -> None:
    assert ConvertDirection is ModelsConvertDirection
    assert NoDataStrategy is ModelsNoDataStrategy
    assert ConvertReport(store_path="store.zarr", direction="materialized_to_manifest").ok


def test_check_with_timing_populates_timing_payload(tmp_path: Path) -> None:
    store = tmp_path / "store.zarr"
    create_store(_dataset(), store, no_data_strategy="empty_chunks")

    report = check_store(store, timing=True)

    assert report.timing is not None
    assert report.timing.total_s >= 0.0
    expected_exists_calls = sum(item.expected_chunks for item in report.variables.values())
    assert report.timing.exists_calls == expected_exists_calls
    assert "var" in report.timing.variables
    var_timing = report.timing.variables["var"]
    assert var_timing.expected_chunks == report.variables["var"].expected_chunks
    assert var_timing.chunk_scan_s >= 0.0
    payload = report.to_dict()
    assert payload["timing"]["exists_calls"] == expected_exists_calls


def test_check_without_timing_omits_timing_payload(tmp_path: Path) -> None:
    store = tmp_path / "store.zarr"
    create_store(_dataset(), store, no_data_strategy="empty_chunks")

    report = check_store(store)

    assert report.timing is None
    assert "timing" not in report.to_dict()


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


def test_check_remote_memory_store_passes_when_missing_is_manifested() -> None:
    store_uri = "memory://remote-guarded.zarr"
    _write_remote_memory_store(store_uri, missing_manifested=[(0, 0)])

    report = check_store(store_uri)

    assert report.ok
    assert len(report.variables["var"].missing_allowed) == 1


def test_check_remote_memory_store_fails_when_missing_is_unexpected() -> None:
    store_uri = "memory://remote-guarded.zarr"
    _write_remote_memory_store(store_uri, missing_unexpected=[(1, 1)])

    report = check_store(store_uri)

    assert not report.ok
    assert any(item.coord == (1, 1) for item in report.variables["var"].missing_unexpected)


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

    report = create_store(
        _dataset(),
        store,
        no_data_chunks={"var": [(0, 1)]},
        no_data_strategy="manifest",
    )
    check = check_store(store)

    assert report.ok
    assert report.manifests_written
    assert check.ok


def test_create_empty_chunks_strategy_roundtrip(tmp_path: Path) -> None:
    store = tmp_path / "store.zarr"

    report = create_store(
        _dataset(),
        store,
        no_data_chunks={"var": [(0, 1)]},
        no_data_strategy="empty_chunks",
    )
    check = check_store(store)

    assert report.ok
    assert not report.manifests_written
    assert check.ok


def test_guarded_to_zarr_roundtrip(tmp_path: Path) -> None:
    store = tmp_path / "store.zarr"

    report = guarded_to_zarr(_dataset(), store)
    check = check_store(store)

    assert report.ok
    assert check.ok


def test_guarded_to_zarr_rejects_store_kwarg(tmp_path: Path) -> None:
    store = tmp_path / "store.zarr"

    with pytest.raises(ValueError, match="must not be provided"):
        guarded_to_zarr(
            _dataset(),
            store,
            to_zarr_kwargs={"store": store},
        )


def test_convert_materialized_to_manifest_and_back(tmp_path: Path) -> None:
    store = tmp_path / "store.zarr"
    create_store(_dataset_with_nan_chunk(), store, no_data_strategy="empty_chunks")

    spec = next(item for item in scan_array_specs(store) if item.name == "var")
    nan_coord = (0, 0)
    assert chunk_path(spec, nan_coord).exists()

    to_manifest = convert_store(store, direction="materialized_to_manifest")
    assert to_manifest.ok
    assert to_manifest.direction == "materialized_to_manifest"
    assert any(ref.coord == nan_coord for ref in to_manifest.deleted_chunks.get("var", []))
    assert manifest_path(store, "var").exists()
    assert not chunk_path(spec, nan_coord).exists()
    assert check_store(store).ok

    to_materialized = convert_store(store, direction="manifest_to_materialized")
    assert to_materialized.ok
    assert to_materialized.direction == "manifest_to_materialized"
    assert to_materialized.manifests_removed
    assert any(
        ref.coord == nan_coord
        for ref in to_materialized.materialized_chunks.get("var", [])
    )
    assert not manifest_path(store, "var").exists()
    assert chunk_path(spec, nan_coord).exists()
    assert check_store(store, strict_stale_manifest=True).ok

    reopened = xr.open_zarr(store, consolidated=False)
    try:
        assert np.isnan(reopened["var"].isel(x=slice(0, 2), y=slice(0, 2)).values).all()
    finally:
        reopened.close()


def test_convert_auto_direction_switches_on_manifest_presence(tmp_path: Path) -> None:
    store = tmp_path / "store.zarr"
    create_store(_dataset_with_nan_chunk(), store, no_data_strategy="empty_chunks")

    first = convert_store(store)
    second = convert_store(store)

    assert first.direction == "materialized_to_manifest"
    assert second.direction == "manifest_to_materialized"
    assert check_store(store, strict_stale_manifest=True).ok


def test_create_in_place_metadata_roundtrip(tmp_path: Path) -> None:
    store = tmp_path / "store.zarr"
    create_store(_dataset(), store, no_data_strategy="empty_chunks")

    spec = next(item for item in scan_array_specs(store) if item.name == "var")
    missing_coord = (0, 0)
    chunk_path(spec, missing_coord).unlink()

    report = create_store(
        None,
        store,
        no_data_chunks={"var": [missing_coord]},
        in_place_metadata_only=True,
    )

    assert report.ok
    assert report.manifests_written
    assert not chunk_path(spec, missing_coord).exists()
    assert check_store(store).ok


def test_create_in_place_metadata_requires_missing_chunks(tmp_path: Path) -> None:
    store = tmp_path / "store.zarr"
    create_store(_dataset(), store, no_data_strategy="empty_chunks")

    with pytest.raises(ValueError, match="currently missing chunks"):
        create_store(
            None,
            store,
            no_data_chunks={"var": [(0, 0)]},
            in_place_metadata_only=True,
        )


def test_create_in_place_metadata_is_transactional(tmp_path: Path) -> None:
    store = tmp_path / "store.zarr"
    create_store(_dataset(), store, no_data_chunks={"var": [(0, 1)]}, no_data_strategy="manifest")

    manifest_file = manifest_path(store, "var")
    before = manifest_file.read_text(encoding="utf-8")

    with pytest.raises(ValueError, match="out of bounds"):
        create_store(
            None,
            store,
            no_data_chunks={"var": [(99, 99)]},
            in_place_metadata_only=True,
        )

    after = manifest_file.read_text(encoding="utf-8")
    assert before == after


def test_create_in_place_metadata_infers_missing_from_store(tmp_path: Path) -> None:
    store = tmp_path / "store.zarr"
    create_store(_dataset(), store, no_data_strategy="empty_chunks")

    spec = next(item for item in scan_array_specs(store) if item.name == "var")
    chunk_path(spec, (0, 0)).unlink()
    chunk_path(spec, (1, 1)).unlink()

    report = create_store(
        None,
        store,
        in_place_metadata_only=True,
        infer_no_data_from_store=True,
    )

    assert report.ok
    assert report.manifests_written
    has_manifest, refs = load_variable_manifest(store, "var")
    assert has_manifest
    assert sorted(ref.coord for ref in refs) == [(0, 0), (1, 1)]
    assert check_store(store).ok


def test_create_in_place_metadata_infer_replaces_stale_manifests(tmp_path: Path) -> None:
    store = tmp_path / "store.zarr"
    create_store(_dataset(), store, no_data_strategy="empty_chunks")

    spec = next(item for item in scan_array_specs(store) if item.name == "var")
    write_variable_manifest(
        store,
        "var",
        [ChunkRef(coord=(0, 0), key=chunk_key(spec, (0, 0)))],
    )
    assert manifest_path(store, "var").exists()

    report = create_store(
        None,
        store,
        in_place_metadata_only=True,
        infer_no_data_from_store=True,
    )

    assert report.ok
    assert not report.manifests_written
    assert not manifest_path(store, "var").exists()
    assert check_store(store, strict_stale_manifest=True).ok


def test_create_in_place_metadata_infer_rejects_explicit_no_data(tmp_path: Path) -> None:
    store = tmp_path / "store.zarr"
    create_store(_dataset(), store, no_data_strategy="empty_chunks")

    with pytest.raises(ValueError, match="cannot be combined with explicit no_data_chunks"):
        create_store(
            None,
            store,
            no_data_chunks={"var": [(0, 0)]},
            in_place_metadata_only=True,
            infer_no_data_from_store=True,
        )


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


def test_check_consolidated_metadata_without_child_metadata_files(tmp_path: Path) -> None:
    store = tmp_path / "store.zarr"
    (store / "var" / "c").mkdir(parents=True)
    root_payload = {
        "zarr_format": 3,
        "node_type": "group",
        "attributes": {},
        "consolidated_metadata": {
            "kind": "inline",
            "must_understand": False,
            "metadata": {
                "var": {
                    "zarr_format": 3,
                    "node_type": "array",
                    "shape": [2],
                    "chunk_grid": {"name": "regular", "configuration": {"chunk_shape": [1]}},
                    "chunk_key_encoding": {
                        "name": "default",
                        "configuration": {"separator": "/"},
                    },
                    "codecs": [],
                    "data_type": "int32",
                    "fill_value": 0,
                    "attributes": {},
                    "dimension_names": ["x"],
                    "storage_transformers": [],
                }
            },
        },
    }
    (store / "zarr.json").write_text(json.dumps(root_payload), encoding="utf-8")
    (store / "var" / "c" / "0").write_bytes(b"0")
    (store / "var" / "c" / "1").write_bytes(b"1")

    report_ok = check_store(store)
    assert report_ok.ok

    (store / "var" / "c" / "1").unlink()
    report_fail = check_store(store)
    assert not report_fail.ok
    assert len(report_fail.variables["var"].missing_unexpected) == 1
