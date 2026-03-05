# xzarrguard

`xzarrguard` provides concise APIs and a CLI to validate completeness of local Zarr v3 stores, create stores with explicit no-data policy, and convert between manifest/materialized no-data representations.

## Install

**PyPI**: `pip install xzarrguard`  
**conda**: `conda install xzarrguard`  
**from source**: `pip install .`  

## Install-free CLI usage

**uv**: `uvx xzarrguard check /path/to/store.zarr`  
**pixi**: `pixi exec xzarrguard check /path/to/store.zarr`

## API quickstart

```python
from xzarrguard import check_store, create_store

report = check_store("store.zarr")
if report:
    print("store is complete")
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
