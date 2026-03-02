# CLI

## Check

```bash
xzarrguard check /path/to/store.zarr
xzarrguard check /path/to/store.zarr --json
xzarrguard check /path/to/store.zarr --timing
xzarrguard check /path/to/store.zarr --strict-stale
```

`--timing` adds coarse phase timings. With `--json`, timings are included in the JSON payload.

Exit codes:

- `0`: integrity pass
- `1`: integrity fail
- `2`: runtime or usage error

## Create

Write a new store from source:

```bash
xzarrguard create /path/to/source.zarr /path/to/target.zarr --no-data no_data.json
```

Update only metadata in an existing store (no data rewrite):

```bash
xzarrguard create /path/to/store.zarr --in-place-metadata-only --no-data no_data.json
```

Build manifests from the store's current missing chunks (treat current state as baseline):

```bash
xzarrguard create /path/to/store.zarr --in-place-metadata-only --infer-no-data-from-store
```

`--infer-no-data-from-store` cannot be combined with `--no-data`.

`no_data.json` maps variable names to chunk coordinates:

```json
{
  "temperature": [[0, 0], [1, 2]]
}
```
