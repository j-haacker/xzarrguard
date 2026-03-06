# API

## `check_store`

```python
from xzarrguard import check_store

report = check_store("/path/to/store.zarr")
if report:
    print("ok")
```

- Returns `IntegrityReport`.
- `report.ok` is the condition flag.
- `bool(report)` maps to `report.ok`.
- Supports Zarr v3 stores with either per-node `zarr.json` metadata or root
  `consolidated_metadata`.
- Remote stores can pass fsspec options via `storage_options`.

```python
report = check_store(
    "s3://example-bucket/path/to/store.zarr",
    storage_options={
        "profile": "example-profile",
        "client_kwargs": {"endpoint_url": "https://object-store.example.com"},
    },
)
```

## `create_store`

```python
from xzarrguard import create_store

create_store(
    dataset,
    "/path/to/store.zarr",
    no_data_chunks={"temperature": [(0, 0)]},
    no_data_strategy="manifest",
)
```

- `no_data_strategy="manifest"` (default): listed chunks may be absent and are documented.
- `no_data_strategy="empty_chunks"`: listed chunks must exist physically.
- `infer_no_data_from_store=True` is available for in-place metadata updates.

For distributed writes, prefer upstream `dataset.to_zarr(..., write_empty_chunks=True)` during the write phase, then run conversion as a finalization step.

### In-place metadata update

Use this mode to guard an existing store without rewriting chunk data. Listed
coordinates must already be missing.

```python
create_store(
    None,
    "/path/to/existing-store.zarr",
    no_data_chunks={"temperature": [(0, 0)]},
    in_place_metadata_only=True,
)
```

This performs a staged manifest update and swaps metadata only after validation
succeeds.

To treat the current store state as baseline and derive manifests from currently
missing chunks:

```python
create_store(
    None,
    "/path/to/existing-store.zarr",
    in_place_metadata_only=True,
    infer_no_data_from_store=True,
)
```

### `guarded_to_zarr`

Wrapper around `.to_zarr()` that writes the store and then guards it by writing
allowed-missing manifests.

```python
from xzarrguard import guarded_to_zarr

guarded_to_zarr(
    dataset,
    "/path/to/store.zarr",
    infer_no_data_from_store=True,
)
```

## `convert_store`

Convert between two no-data encodings:

- `materialized_to_manifest`: remove all-NaN chunk payloads and record them in manifests.
- `manifest_to_materialized`: re-materialize missing chunks from manifests and remove manifests.
- `auto` (default): pick based on whether manifests already exist.

```python
from xzarrguard import convert_store

report = convert_store("/path/to/store.zarr", direction="auto")
print(report.direction)
```
