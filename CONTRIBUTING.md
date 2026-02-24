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
