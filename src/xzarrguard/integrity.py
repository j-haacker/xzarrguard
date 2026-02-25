"""Store completeness checks for local Zarr v3 stores."""

from __future__ import annotations

from pathlib import Path
from time import perf_counter

from .layout import chunk_key, chunk_path, coord_in_bounds, expected_chunk_coords, scan_array_specs
from .manifest import load_variable_manifest
from .models import ChunkRef, IntegrityReport, IntegrityTiming, VariableIntegrity, VariableTiming


def check_store(
    store_path: str | Path,
    *,
    strict_stale_manifest: bool = False,
    timing: bool = False,
) -> IntegrityReport:
    """Validate completeness of a Zarr v3 store."""

    total_start = perf_counter() if timing else 0.0
    store = Path(store_path)
    report = IntegrityReport(store_path=str(store), strict_stale_manifest=strict_stale_manifest)
    timing_data = IntegrityTiming() if timing else None

    def _finish() -> IntegrityReport:
        if timing_data is not None:
            timing_data.total_s = perf_counter() - total_start
            report.timing = timing_data
        return report

    if not store.exists():
        report.ok = False
        report.errors.append(f"Store does not exist: {store}")
        return _finish()
    if not store.is_dir():
        report.ok = False
        report.errors.append(f"Store path is not a directory: {store}")
        return _finish()

    scan_start = perf_counter() if timing_data is not None else 0.0
    try:
        specs = scan_array_specs(store)
    except ValueError as exc:
        report.ok = False
        report.errors.append(str(exc))
        return _finish()
    if timing_data is not None:
        timing_data.scan_specs_s = perf_counter() - scan_start

    for spec in specs:
        var_timing = VariableTiming() if timing_data is not None else None

        manifest_load_start = perf_counter() if var_timing is not None else 0.0
        has_manifest, manifest_refs = load_variable_manifest(store, spec.name)
        if var_timing is not None:
            var_timing.manifest_load_s = perf_counter() - manifest_load_start

        variable = VariableIntegrity(
            name=spec.name,
            expected_chunks=0,
            has_manifest=has_manifest,
        )

        manifest_validate_start = perf_counter() if var_timing is not None else 0.0
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

        if var_timing is not None:
            var_timing.manifest_validate_s = perf_counter() - manifest_validate_start

        chunk_scan_start = perf_counter() if var_timing is not None else 0.0
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

        if var_timing is not None:
            var_timing.chunk_scan_s = perf_counter() - chunk_scan_start
            var_timing.expected_chunks = variable.expected_chunks
            var_timing.missing_chunks = len(variable.missing_allowed) + len(
                variable.missing_unexpected
            )

        variable.ok = not variable.missing_unexpected
        if variable.manifest_key_mismatch or variable.manifest_out_of_bounds:
            variable.ok = False
        if strict_stale_manifest and variable.stale_manifest:
            variable.ok = False

        report.variables[spec.name] = variable
        if timing_data is not None and var_timing is not None:
            timing_data.variables[spec.name] = var_timing
            timing_data.manifest_s += var_timing.manifest_load_s + var_timing.manifest_validate_s
            timing_data.chunk_scan_s += var_timing.chunk_scan_s
            timing_data.exists_calls += variable.expected_chunks

    report.ok = not report.errors and all(variable.ok for variable in report.variables.values())
    return _finish()
