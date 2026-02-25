# xzarrguard

`xzarrguard` provides concise APIs and a CLI to validate completeness of local Zarr v3 stores and create stores with explicit no-data policy.

## Install

```bash
pip install .
```

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

## CLI quickstart

```bash
xzarrguard check store.zarr
xzarrguard create source.zarr target.zarr --no-data no_data.json
```

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
