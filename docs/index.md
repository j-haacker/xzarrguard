# xzarrguard

`xzarrguard` checks whether local Zarr v3 stores are complete and can create stores with explicit no-data handling.

Use `manifest` mode (default) when missing chunks are intentional and should be documented.
Use `empty_chunks` mode when all chunk files must physically exist.
