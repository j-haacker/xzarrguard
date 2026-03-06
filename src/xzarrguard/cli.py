"""CLI for checking, creating, and converting integrity-aware stores."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import xarray as xr

from ._version import __version__
from .create import convert_store, create_store
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
    check.add_argument(
        "--profile",
        help="Credential profile for remote backends such as s3fs",
    )
    check.add_argument(
        "--endpoint-url",
        help="Custom endpoint URL for S3-compatible backends",
    )
    check.add_argument(
        "--storage-option",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help=(
            "Additional fsspec storage option. Use dotted keys for nesting, for example "
            "client_kwargs.endpoint_url=https://object-store.example.com"
        ),
    )

    create = subparsers.add_parser("create", help="Create integrity-aware store")
    create.add_argument("source_zarr", help="Source Zarr store readable by xarray")
    create.add_argument(
        "target_store",
        nargs="?",
        help="Target Zarr store path. Omit when using --in-place-metadata-only.",
    )
    create.add_argument("--no-data", help="JSON mapping of variable to no-data chunk coordinates")
    create.add_argument("--overwrite", action="store_true", help="Overwrite target if it exists")
    create.add_argument(
        "--in-place-metadata-only",
        action="store_true",
        help="Update manifests in an existing store without rewriting chunk data",
    )
    create.add_argument(
        "--infer-no-data-from-store",
        action="store_true",
        help="In in-place mode, derive allowed-missing chunks from currently missing chunks",
    )

    convert = subparsers.add_parser("convert", help="Convert store materialization mode")
    convert.add_argument("store_path", help="Path to existing Zarr store")
    convert.add_argument(
        "--direction",
        default="auto",
        choices=["auto", "materialized_to_manifest", "manifest_to_materialized"],
        help=(
            "Conversion direction. auto chooses based on whether manifests exist "
            "(default: %(default)s)"
        ),
    )

    return parser


def _run_check(args: argparse.Namespace) -> int:
    try:
        storage_options = _build_storage_options(args)
        report = check_store(
            args.store_path,
            strict_stale_manifest=args.strict_stale,
            timing=args.timing,
            storage_options=storage_options,
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

    if args.in_place_metadata_only:
        if args.overwrite:
            print(
                "error: --overwrite cannot be used with --in-place-metadata-only",
                file=sys.stderr,
            )
            return 2
        if args.infer_no_data_from_store and args.no_data:
            print(
                "error: --infer-no-data-from-store cannot be combined with --no-data",
                file=sys.stderr,
            )
            return 2

        if args.target_store is None:
            target_store = args.source_zarr
        else:
            source = Path(args.source_zarr)
            target = Path(args.target_store)
            if source != target:
                print(
                    "error: with --in-place-metadata-only, target_store must be omitted "
                    "or equal to source_zarr",
                    file=sys.stderr,
                )
                return 2
            target_store = args.target_store

        try:
            report = create_store(
                None,
                target_store,
                no_data_chunks=no_data,
                in_place_metadata_only=True,
                infer_no_data_from_store=args.infer_no_data_from_store,
            )
        except Exception as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2

        print(f"updated: {report.store_path}")
        if report.manifests_written:
            print(f"manifests: {len(report.manifests_written)}")
        elif args.infer_no_data_from_store:
            print("manifests: 0 (no missing chunks detected)")
        return 0

    if args.target_store is None:
        print(
            "error: target_store is required unless --in-place-metadata-only is used",
            file=sys.stderr,
        )
        return 2

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


def _run_convert(args: argparse.Namespace) -> int:
    try:
        report = convert_store(args.store_path, direction=args.direction)
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    print(f"converted: {report.store_path}")
    print(f"direction: {report.direction}")
    if report.manifests_written:
        print(f"manifests_written: {len(report.manifests_written)}")
    if report.manifests_removed:
        print(f"manifests_removed: {len(report.manifests_removed)}")
    deleted_count = sum(len(refs) for refs in report.deleted_chunks.values())
    materialized_count = sum(len(refs) for refs in report.materialized_chunks.values())
    if deleted_count:
        print(f"deleted_chunks: {deleted_count}")
    if materialized_count:
        print(f"materialized_chunks: {materialized_count}")
    return 0


def _build_storage_options(args: argparse.Namespace) -> dict[str, Any]:
    options = _parse_storage_options(args.storage_option)
    if args.profile:
        options.setdefault("profile", args.profile)
    if args.endpoint_url:
        client_kwargs = options.setdefault("client_kwargs", {})
        if not isinstance(client_kwargs, dict):
            raise ValueError("client_kwargs storage option must be a mapping")
        client_kwargs.setdefault("endpoint_url", args.endpoint_url)
    return options


def _parse_storage_options(items: Sequence[str]) -> dict[str, Any]:
    options: dict[str, Any] = {}
    for item in items:
        key, separator, raw_value = item.partition("=")
        if not separator or not key:
            raise ValueError(f"Invalid --storage-option value: {item!r}")
        _assign_nested_option(options, key.split("."), _coerce_storage_value(raw_value))
    return options


def _assign_nested_option(target: dict[str, Any], path: Sequence[str], value: Any) -> None:
    current = target
    for key in path[:-1]:
        existing = current.setdefault(key, {})
        if not isinstance(existing, dict):
            raise ValueError(f"Storage option path conflict at {'.'.join(path)}")
        current = existing
    current[path[-1]] = value


def _coerce_storage_value(value: str) -> Any:
    lowered = value.lower()
    if lowered in {"true", "false", "null"}:
        return json.loads(lowered)
    try:
        if value and value[0] in {"[", "{", "\""}:
            return json.loads(value)
        if value.isdigit() or (value.startswith("-") and value[1:].isdigit()):
            return json.loads(value)
        if "." in value:
            return json.loads(value)
    except json.JSONDecodeError:
        pass
    return value


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entrypoint."""

    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "check":
        return _run_check(args)
    if args.command == "create":
        return _run_create(args)
    if args.command == "convert":
        return _run_convert(args)
    parser.error(f"unknown command: {args.command}")
    return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
