# Conda-Forge Recipe Notes

This repo keeps a local CI-friendly recipe using `git_url` plus `GIT_DESCRIBE_*` metadata.

## Local CI behavior

- `source.git_url` points to this checkout (`FEEDSTOCK_ROOT`).
- `version` defaults to `untagged` unless `GIT_DESCRIBE_TAG` is provided.

## Publishing Checklist

1. Publish to PyPI first.
2. Update `recipe/meta.yaml` for conda-forge submission:
   - set a fixed `version` (from the PyPI release)
   - switch `source` to the PyPI sdist URL
   - add the sdist `sha256`
3. Submit:
   - first release: PR to `conda-forge/staged-recipes`
   - updates: PR to `conda-forge/xzarrguard-feedstock`
