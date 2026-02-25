# Conda-Forge Recipe Notes

This folder contains a starter recipe for conda-forge submissions.

## Update Checklist

1. Release to PyPI first.
2. Update `version` in `recipe/meta.yaml`.
3. Replace `sha256` with the hash of the PyPI sdist for that version.
4. For first publication, open a PR to `conda-forge/staged-recipes` with this recipe.
5. For updates, open a PR to `conda-forge/xzarrguard-feedstock`.

## SHA256 Helper

After building locally, you can compute a candidate hash with:

```bash
sha256sum dist/xzarrguard-<version>.tar.gz
```

Use the hash from the artifact you actually publish to PyPI.
