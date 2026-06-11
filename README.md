# xzarrguard

`xzarrguard` solves the ambiguity of interpreting missing chunk files as `NaN`, and provides concise APIs and a CLI to validate completeness of Zarr v3 stores, create local stores with explicit no-data policy, and convert between manifest/materialized no-data representations.

> [!NOTE]
> Since xarray v2025.09.1, no-data values are preserved during writing for floats. Zarr stores produced by this or newer versions will reliably translate missing chunks to NaN.

## Install

**PyPI**: `pip install xzarrguard`  
**PyPI + S3 support**: `pip install "xzarrguard[s3]"`  
**conda**: `conda install xzarrguard`  
**from source**: `pip install .`  

## Install-free CLI usage

**uv**: `uvx xzarrguard check /path/to/store.zarr`  
**pixi**: `pixi exec xzarrguard check /path/to/store.zarr`

Remote `check` uses fsspec backends. For S3-compatible stores:

```bash
xzarrguard check "s3://example-bucket/path/to/store.zarr" \
  --profile example-profile \
  --endpoint-url "https://object-store.example.com"
```

## API quickstart

```python
from xzarrguard import check_store, create_store

report = check_store("store.zarr")
if report:
    print("store is complete")
```

```python
remote_report = check_store(
    "s3://example-bucket/path/to/store.zarr",
    storage_options={
        "profile": "example-profile",
        "client_kwargs": {"endpoint_url": "https://object-store.example.com"},
    },
)
```

```python
create_store(
    dataset,
    "store.zarr",
    no_data_chunks={"temperature": [(0, 0)]},
    no_data_strategy="manifest",
)
```

Write and guard in one step (wrapper around `.to_zarr()`):

```python
from xzarrguard import guarded_to_zarr

guarded_to_zarr(dataset, "store.zarr")
```

Recommended distributed-write workflow:

1. Use upstream `xarray.Dataset.to_zarr(..., write_empty_chunks=True)` during the distributed write phase so workers materialize chunk keys deterministically.
2. Finalize with `xzarrguard` conversion to derive compact manifests from no-data chunks.

```python
from xzarrguard import convert_store

convert_store("store.zarr", direction="auto")
```

In-place metadata-only guard update (no chunk rewrite):

```python
create_store(
    None,
    "store.zarr",
    no_data_chunks={"temperature": [(0, 0)]},
    in_place_metadata_only=True,
)
```

Treat the current store as baseline and derive allowed-missing chunks from
what is currently missing:

```python
create_store(
    None,
    "store.zarr",
    in_place_metadata_only=True,
    infer_no_data_from_store=True,
)
```

## CLI quickstart

```bash
xzarrguard check store.zarr
xzarrguard check "s3://example-bucket/path/to/store.zarr" --profile example-profile --endpoint-url "https://object-store.example.com"
xzarrguard create source.zarr target.zarr --no-data no_data.json
xzarrguard create store.zarr --in-place-metadata-only --no-data no_data.json
xzarrguard create store.zarr --in-place-metadata-only --infer-no-data-from-store
xzarrguard convert store.zarr
xzarrguard convert store.zarr --direction manifest_to_materialized
```

Note: you may see `ZarrUserWarning: Object at .xzarrguard is not recognized as a component of a Zarr hierarchy.` when tooling walks the store hierarchy. This is expected: `.xzarrguard/` is xzarrguard sidecar metadata, not a Zarr array/group node.

## Coverage

```bash
pytest
```

`pytest` prints terminal coverage and writes `coverage.xml`.

## Documentation

https://j-haacker.github.io/xzarrguard/

```bash
zensical serve
zensical build --clean
```

## Channels

- PyPI: https://pypi.org/project/xzarrguard/
- Conda-forge: https://anaconda.org/conda-forge/xzarrguard
- GitHub: https://github.com/j-haacker/xzarrguard

## Release (maintainers)

```bash
# bump src/xzarrguard/_version.py first
python -m build
python -m twine check dist/*
python -m twine upload dist/*
```

Use a PyPI API token for upload (for example `TWINE_USERNAME=__token__`).
For conda-forge, update `recipe/recipe.yaml` after the PyPI release (fixed version + PyPI sdist URL + sha256), then submit a recipe/feedstock PR.

Acknowledgement: Initial scaffolding and implementation assistance by OpenAI Codex.
