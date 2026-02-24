# Manifest

Per-variable manifests are written to:

`<store>/.xzarrguard/manifests/<url-encoded-variable>.json`

Each entry contains both canonical coordinates and derived storage key:

```json
{
  "schema_version": 1,
  "zarr_format": 3,
  "variable": "temperature",
  "allowed_missing": [
    { "coord": [0, 1], "key": "temperature/c/0/1" }
  ]
}
```

## OS-level key checks (docs only)

Linux/macOS example:

```bash
test -f /path/to/store.zarr/temperature/c/0/1 && echo present || echo missing
```

PowerShell example:

```powershell
if (Test-Path "C:\path\to\store.zarr\temperature\c\0\1") { "present" } else { "missing" }
```
