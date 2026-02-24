"""Store completeness checks for local Zarr v3 stores."""

from __future__ import annotations

from pathlib import Path

from .layout import chunk_key, chunk_path, coord_in_bounds, expected_chunk_coords, scan_array_specs
from .manifest import load_variable_manifest
from .models import ChunkRef, IntegrityReport, VariableIntegrity


def check_store(store_path: str | Path, *, strict_stale_manifest: bool = False) -> IntegrityReport:
    """Validate completeness of a Zarr v3 store."""

    store = Path(store_path)
    report = IntegrityReport(store_path=str(store), strict_stale_manifest=strict_stale_manifest)

    if not store.exists():
        report.ok = False
        report.errors.append(f"Store does not exist: {store}")
        return report
    if not store.is_dir():
        report.ok = False
        report.errors.append(f"Store path is not a directory: {store}")
        return report

    try:
        specs = scan_array_specs(store)
    except ValueError as exc:
        report.ok = False
        report.errors.append(str(exc))
        return report

    for spec in specs:
        has_manifest, manifest_refs = load_variable_manifest(store, spec.name)
        variable = VariableIntegrity(
            name=spec.name,
            expected_chunks=0,
            has_manifest=has_manifest,
        )

        valid_manifest: dict[tuple[int, ...], ChunkRef] = {}
        for ref in manifest_refs:
            if not coord_in_bounds(spec, ref.coord):
                variable.manifest_out_of_bounds.append(ref)
                continue
            expected_key = chunk_key(spec, ref.coord)
            if ref.key != expected_key:
                variable.manifest_key_mismatch.append(ref)
                continue
            valid_manifest[ref.coord] = ref

        for coord in expected_chunk_coords(spec):
            variable.expected_chunks += 1
            key = chunk_key(spec, coord)
            exists = chunk_path(spec, coord).exists()
            ref = ChunkRef(coord=coord, key=key)

            if not exists and coord in valid_manifest:
                variable.missing_allowed.append(ref)
            elif not exists:
                variable.missing_unexpected.append(ref)
            elif coord in valid_manifest:
                variable.stale_manifest.append(ref)

        variable.ok = not variable.missing_unexpected
        if variable.manifest_key_mismatch or variable.manifest_out_of_bounds:
            variable.ok = False
        if strict_stale_manifest and variable.stale_manifest:
            variable.ok = False

        report.variables[spec.name] = variable

    report.ok = not report.errors and all(variable.ok for variable in report.variables.values())
    return report
