# Contributing

## Setup

```bash
python -m venv .venv
. .venv/bin/activate
pip install -e .[dev]
pre-commit install
```

## Quality checks

```bash
pytest
tox
pre-commit run --all-files
```

`pytest` includes coverage output and writes `coverage.xml`.

## Workflow

- Work on a feature branch.
- Keep functions and docs concise.
- Use focused commits with descriptive messages.

## Benchmarking

Use the lightweight benchmark helper to compare `check` performance before and after changes.

```bash
python scripts/benchmark_check.py /path/to/store.zarr --runs 5 --warmup 1 --out bench-before.json
python scripts/benchmark_check.py /path/to/store.zarr --runs 5 --warmup 1 --out bench-after.json --baseline bench-before.json
```

This tool runs `xzarrguard check --json --timing`, reports summary stats, and writes comparable JSON results.

## Release (maintainers)

1. Update `src/xzarrguard/_version.py`.
2. Build artifacts:

```bash
python -m build
```

3. Validate package metadata:

```bash
python -m twine check dist/*
```

4. Publish to PyPI:

```bash
python -m twine upload dist/*
```
