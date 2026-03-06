# CLI

## Check

```bash
xzarrguard check /path/to/store.zarr
xzarrguard check /path/to/store.zarr --json
xzarrguard check /path/to/store.zarr --timing
xzarrguard check /path/to/store.zarr --strict-stale
xzarrguard check "s3://example-bucket/path/to/store.zarr" --profile example-profile --endpoint-url "https://object-store.example.com"
```

`--timing` adds coarse phase timings. With `--json`, timings are included in the JSON payload.
Remote `check` accepts `--profile`, `--endpoint-url`, and repeatable `--storage-option KEY=VALUE` flags which are forwarded as fsspec storage options.

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

For distributed write phases, prefer upstream `xarray.Dataset.to_zarr(..., write_empty_chunks=True)` and use `xzarrguard convert` as the finalization step.

`no_data.json` maps variable names to chunk coordinates:

```json
{
  "temperature": [[0, 0], [1, 2]]
}
```

## Convert

Finalize or re-materialize no-data representation in an existing store:

```bash
xzarrguard convert /path/to/store.zarr
xzarrguard convert /path/to/store.zarr --direction materialized_to_manifest
xzarrguard convert /path/to/store.zarr --direction manifest_to_materialized
```

Direction options:

- `auto` (default): if manifests exist, converts to materialized; otherwise converts to manifest.
- `materialized_to_manifest`: deletes all-NaN chunks and writes manifests.
- `manifest_to_materialized`: re-creates missing chunks and removes manifests.

Note: some Zarr operations may emit `ZarrUserWarning: Object at .xzarrguard is not recognized as a component of a Zarr hierarchy.` This is expected, because `.xzarrguard/` stores xzarrguard sidecar manifests and is not part of the Zarr hierarchy itself.
