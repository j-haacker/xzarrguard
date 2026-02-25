# API

## `check_store`

```python
from xzarrguard import check_store

report = check_store("/path/to/store.zarr")
if report:
    print("ok")
```

- Returns `IntegrityReport`.
- `report.ok` is the condition flag.
- `bool(report)` maps to `report.ok`.
- Supports Zarr v3 stores with either per-node `zarr.json` metadata or root
  `consolidated_metadata`.

## `create_store`

```python
from xzarrguard import create_store

create_store(
    dataset,
    "/path/to/store.zarr",
    no_data_chunks={"temperature": [(0, 0)]},
    no_data_strategy="manifest",
)
```

- `no_data_strategy="manifest"` (default): listed chunks may be absent and are documented.
- `no_data_strategy="empty_chunks"`: listed chunks must exist physically.
