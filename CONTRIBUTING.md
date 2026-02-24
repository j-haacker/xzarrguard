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

## Workflow

- Work on a feature branch.
- Keep functions and docs concise.
- Use focused commits with descriptive messages.
