from __future__ import annotations

import inspect
import json
from pathlib import Path

import numpy as np
import pytest
import xarray as xr

from xzarrguard._version import __version__
from xzarrguard.cli import main
from xzarrguard.create import create_store
from xzarrguard.layout import chunk_path, scan_array_specs
from xzarrguard.manifest import dump_no_data_chunks, manifest_path


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


def test_cli_check_exit_code_success(tmp_path: Path, capsys) -> None:
    store = tmp_path / "store.zarr"
    create_store(_dataset(), store, no_data_strategy="empty_chunks")

    code = main(["check", str(store)])
    out = capsys.readouterr().out

    assert code == 0
    assert "PASS" in out


def test_cli_version_option(capsys) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["--version"])

    out = capsys.readouterr().out.strip()
    assert exc.value.code == 0
    assert out == f"xzarrguard {__version__}"


def test_cli_check_exit_code_failure(tmp_path: Path, capsys) -> None:
    store = tmp_path / "store.zarr"
    create_store(_dataset(), store, no_data_strategy="empty_chunks")

    spec = next(item for item in scan_array_specs(store) if item.name == "var")
    chunk_path(spec, (0, 0)).unlink()

    code = main(["check", str(store)])
    out = capsys.readouterr().out

    assert code == 1
    assert "FAIL" in out


def test_cli_check_json_output(tmp_path: Path, capsys) -> None:
    store = tmp_path / "store.zarr"
    create_store(_dataset(), store, no_data_strategy="empty_chunks")

    code = main(["check", str(store), "--json"])
    out = capsys.readouterr().out
    payload = json.loads(out)

    assert code == 0
    assert payload["ok"] is True


def test_cli_check_timing_output(tmp_path: Path, capsys) -> None:
    store = tmp_path / "store.zarr"
    create_store(_dataset(), store, no_data_strategy="empty_chunks")

    code = main(["check", str(store), "--timing"])
    out = capsys.readouterr().out

    assert code == 0
    assert "timing: total=" in out


def test_cli_check_json_output_with_timing(tmp_path: Path, capsys) -> None:
    store = tmp_path / "store.zarr"
    create_store(_dataset(), store, no_data_strategy="empty_chunks")

    code = main(["check", str(store), "--json", "--timing"])
    out = capsys.readouterr().out
    payload = json.loads(out)

    assert code == 0
    assert payload["ok"] is True
    assert payload["timing"]["exists_calls"] > 0


def test_cli_create_then_check_roundtrip(tmp_path: Path, capsys) -> None:
    source = tmp_path / "source.zarr"
    target = tmp_path / "target.zarr"
    no_data = tmp_path / "no_data.json"

    _write_source_store(_dataset(), source)
    dump_no_data_chunks(no_data, {"var": [(0, 0)]})

    create_code = main(["create", str(source), str(target), "--no-data", str(no_data)])
    _ = capsys.readouterr()
    check_code = main(["check", str(target)])

    assert create_code == 0
    assert check_code == 0


def test_cli_create_in_place_metadata_then_check(tmp_path: Path, capsys) -> None:
    store = tmp_path / "store.zarr"
    no_data = tmp_path / "no_data.json"
    create_store(_dataset(), store, no_data_strategy="empty_chunks")

    spec = next(item for item in scan_array_specs(store) if item.name == "var")
    chunk_path(spec, (0, 0)).unlink()
    dump_no_data_chunks(no_data, {"var": [(0, 0)]})

    create_code = main([
        "create",
        str(store),
        "--in-place-metadata-only",
        "--no-data",
        str(no_data),
    ])
    create_out = capsys.readouterr().out
    check_code = main(["check", str(store)])

    assert create_code == 0
    assert f"updated: {store}" in create_out
    assert check_code == 0


def test_cli_create_in_place_metadata_rejects_different_target(capsys) -> None:
    create_code = main([
        "create",
        "source.zarr",
        "target.zarr",
        "--in-place-metadata-only",
    ])
    err = capsys.readouterr().err

    assert create_code == 2
    assert "target_store must be omitted or equal to source_zarr" in err


def test_cli_create_in_place_metadata_infers_missing_from_store(tmp_path: Path, capsys) -> None:
    store = tmp_path / "store.zarr"
    create_store(_dataset(), store, no_data_strategy="empty_chunks")

    spec = next(item for item in scan_array_specs(store) if item.name == "var")
    chunk_path(spec, (0, 0)).unlink()

    create_code = main([
        "create",
        str(store),
        "--in-place-metadata-only",
        "--infer-no-data-from-store",
    ])
    create_out = capsys.readouterr().out
    check_code = main(["check", str(store)])

    assert create_code == 0
    assert f"updated: {store}" in create_out
    assert "manifests: 1" in create_out
    assert check_code == 0


def test_cli_create_in_place_metadata_rejects_infer_with_no_data(tmp_path: Path, capsys) -> None:
    store = tmp_path / "store.zarr"
    no_data = tmp_path / "no_data.json"
    create_store(_dataset(), store, no_data_strategy="empty_chunks")
    dump_no_data_chunks(no_data, {"var": [(0, 0)]})

    create_code = main([
        "create",
        str(store),
        "--in-place-metadata-only",
        "--infer-no-data-from-store",
        "--no-data",
        str(no_data),
    ])
    err = capsys.readouterr().err

    assert create_code == 2
    assert "--infer-no-data-from-store cannot be combined with --no-data" in err


def test_cli_convert_auto_to_manifest(tmp_path: Path, capsys) -> None:
    store = tmp_path / "store.zarr"
    create_store(_dataset_with_nan_chunk(), store, no_data_strategy="empty_chunks")

    convert_code = main(["convert", str(store)])
    convert_out = capsys.readouterr().out
    check_code = main(["check", str(store)])

    assert convert_code == 0
    assert "direction: materialized_to_manifest" in convert_out
    assert check_code == 0
    assert manifest_path(store, "var").exists()


def test_cli_convert_explicit_manifest_to_materialized(tmp_path: Path, capsys) -> None:
    store = tmp_path / "store.zarr"
    create_store(_dataset_with_nan_chunk(), store, no_data_strategy="empty_chunks")

    to_manifest_code = main(["convert", str(store)])
    _ = capsys.readouterr()
    to_materialized_code = main([
        "convert",
        str(store),
        "--direction",
        "manifest_to_materialized",
    ])
    to_materialized_out = capsys.readouterr().out
    strict_check_code = main(["check", str(store), "--strict-stale"])

    assert to_manifest_code == 0
    assert to_materialized_code == 0
    assert "direction: manifest_to_materialized" in to_materialized_out
    assert "manifests_removed: 1" in to_materialized_out
    assert strict_check_code == 0
    assert not manifest_path(store, "var").exists()
