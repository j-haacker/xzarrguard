from __future__ import annotations

import json
from pathlib import Path

import pytest

from xzarrguard.layout import scan_array_specs


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _group_meta(*, metadata: dict[str, dict] | None = None) -> dict:
    payload: dict[str, object] = {"zarr_format": 3, "node_type": "group", "attributes": {}}
    if metadata is not None:
        payload["consolidated_metadata"] = {
            "kind": "inline",
            "must_understand": False,
            "metadata": metadata,
        }
    return payload


def _array_meta(shape: tuple[int, ...], chunk_shape: tuple[int, ...]) -> dict:
    return {
        "zarr_format": 3,
        "node_type": "array",
        "shape": list(shape),
        "chunk_grid": {"name": "regular", "configuration": {"chunk_shape": list(chunk_shape)}},
        "chunk_key_encoding": {"name": "default", "configuration": {"separator": "/"}},
    }


def test_scan_array_specs_discovers_nested_arrays_without_scanning_chunks(tmp_path: Path) -> None:
    store = tmp_path / "store.zarr"
    _write_json(store / "zarr.json", _group_meta())
    _write_json(store / "a" / "zarr.json", _array_meta((4, 4), (2, 2)))
    _write_json(store / "group" / "zarr.json", _group_meta())
    _write_json(store / "group" / "b" / "zarr.json", _array_meta((8,), (4,)))

    # If chunk directories were recursively scanned, this would trigger a format error.
    _write_json(store / "a" / "c" / "0" / "zarr.json", {"zarr_format": 2, "node_type": "array"})

    specs = scan_array_specs(store)
    assert [item.name for item in specs] == ["a", "group/b"]


def test_scan_array_specs_rejects_non_v3_root(tmp_path: Path) -> None:
    store = tmp_path / "store.zarr"
    _write_json(store / "zarr.json", {"zarr_format": 2, "node_type": "group"})

    with pytest.raises(ValueError, match="zarr_format=3"):
        scan_array_specs(store)


def test_scan_array_specs_supports_consolidated_metadata_without_child_files(
    tmp_path: Path,
) -> None:
    store = tmp_path / "store.zarr"
    _write_json(
        store / "zarr.json",
        _group_meta(
            metadata={
                "a": _array_meta((4, 4), (2, 2)),
                "nested/b": _array_meta((8,), (4,)),
            }
        ),
    )

    specs = scan_array_specs(store)

    assert [item.name for item in specs] == ["a", "nested/b"]
    assert specs[0].path == store / "a"
    assert specs[1].path == store / "nested" / "b"


def test_scan_array_specs_prefers_consolidated_metadata_when_available(tmp_path: Path) -> None:
    store = tmp_path / "store.zarr"
    _write_json(
        store / "zarr.json",
        _group_meta(
            metadata={
                "a": _array_meta((4, 4), (2, 2)),
            }
        ),
    )
    # Broken per-array metadata should not matter if consolidated metadata is present.
    _write_json(store / "a" / "zarr.json", {"zarr_format": 2, "node_type": "array"})

    specs = scan_array_specs(store)

    assert [item.name for item in specs] == ["a"]
