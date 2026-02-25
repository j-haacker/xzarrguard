# Conda-Forge Recipe Notes

This repo tracks a conda-forge v1 recipe in `recipe/recipe.yaml`.

## Publishing Checklist

1. Publish to PyPI first.
2. Update `recipe/recipe.yaml` for conda-forge submission:
   - set `context.version` to the PyPI release version
   - set `source.url` to the PyPI sdist URL
   - set `source.sha256` to the sdist hash
3. Submit:
   - first release: PR to `conda-forge/staged-recipes`
   - updates: PR to `conda-forge/xzarrguard-feedstock`
