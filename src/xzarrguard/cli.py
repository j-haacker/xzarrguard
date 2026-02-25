"""CLI for checking and creating integrity-aware stores."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence

import xarray as xr

from ._version import __version__
from .create import create_store
from .integrity import check_store
from .manifest import load_no_data_chunks


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="xzarrguard")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    check = subparsers.add_parser("check", help="Check store completeness")
    check.add_argument("store_path", help="Path to Zarr store")
    check.add_argument("--json", action="store_true", help="Print JSON report")
    check.add_argument("--timing", action="store_true", help="Print coarse timing details")
    check.add_argument(
        "--strict-stale",
        action="store_true",
        help="Fail when manifest contains entries for chunks that exist",
    )

    create = subparsers.add_parser("create", help="Create integrity-aware store")
    create.add_argument("source_zarr", help="Source Zarr store readable by xarray")
    create.add_argument("target_store", help="Target Zarr store path")
    create.add_argument("--no-data", help="JSON mapping of variable to no-data chunk coordinates")
    create.add_argument("--overwrite", action="store_true", help="Overwrite target if it exists")

    return parser


def _run_check(args: argparse.Namespace) -> int:
    try:
        report = check_store(
            args.store_path,
            strict_stale_manifest=args.strict_stale,
            timing=args.timing,
        )
    except Exception as exc:  # pragma: no cover - defensive CLI guard
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(report.to_dict(), indent=2, sort_keys=True))
    else:
        print("PASS" if report.ok else "FAIL")
        for name in sorted(report.variables):
            item = report.variables[name]
            details: list[str] = []
            if item.missing_unexpected:
                details.append(f"missing_unexpected={len(item.missing_unexpected)}")
            if item.stale_manifest:
                details.append(f"stale_manifest={len(item.stale_manifest)}")
            if item.manifest_key_mismatch:
                details.append(f"manifest_key_mismatch={len(item.manifest_key_mismatch)}")
            if item.manifest_out_of_bounds:
                details.append(f"manifest_out_of_bounds={len(item.manifest_out_of_bounds)}")
            if details:
                print(f"{name}: {', '.join(details)}")
        for error in report.errors:
            print(f"error: {error}")
        if args.timing and report.timing is not None:
            timing = report.timing
            print(
                "timing: "
                f"total={timing.total_s:.3f}s "
                f"scan_specs={timing.scan_specs_s:.3f}s "
                f"manifest={timing.manifest_s:.3f}s "
                f"chunk_scan={timing.chunk_scan_s:.3f}s "
                f"exists_calls={timing.exists_calls}"
            )

    return 0 if report.ok else 1


def _run_create(args: argparse.Namespace) -> int:
    no_data = load_no_data_chunks(args.no_data) if args.no_data else None

    dataset = xr.open_zarr(args.source_zarr, consolidated=False)
    try:
        report = create_store(
            dataset,
            args.target_store,
            no_data_chunks=no_data,
            overwrite=args.overwrite,
        )
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    finally:
        dataset.close()

    print(f"created: {report.store_path}")
    if report.manifests_written:
        print(f"manifests: {len(report.manifests_written)}")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entrypoint."""

    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "check":
        return _run_check(args)
    if args.command == "create":
        return _run_create(args)
    parser.error(f"unknown command: {args.command}")
    return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
