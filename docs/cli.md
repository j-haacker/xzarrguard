# CLI

## Check

```bash
xzarrguard check /path/to/store.zarr
xzarrguard check /path/to/store.zarr --json
xzarrguard check /path/to/store.zarr --strict-stale
```

Exit codes:

- `0`: integrity pass
- `1`: integrity fail
- `2`: runtime or usage error

## Create

```bash
xzarrguard create /path/to/source.zarr /path/to/target.zarr --no-data no_data.json
```

`no_data.json` maps variable names to chunk coordinates:

```json
{
  "temperature": [[0, 0], [1, 2]]
}
```
