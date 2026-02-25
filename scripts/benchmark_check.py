#!/usr/bin/env python3
"""Benchmark repeated `xzarrguard check` runs and optionally compare to baseline."""

from __future__ import annotations

import argparse
import json
import os
import statistics
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"


def _summary(values: list[float]) -> dict[str, float]:
    if not values:
        raise ValueError("No benchmark values were collected")
    p95 = values[0]
    if len(values) > 1:
        p95 = statistics.quantiles(values, n=20, method="inclusive")[18]
    payload: dict[str, float] = {
        "min": min(values),
        "max": max(values),
        "mean": statistics.fmean(values),
        "median": statistics.median(values),
        "p95": p95,
    }
    if len(values) > 1:
        payload["stdev"] = statistics.stdev(values)
    return payload


def _run_once(
    store_path: Path,
    *,
    python_bin: str,
    strict_stale: bool,
) -> dict[str, Any]:
    cmd = [
        python_bin,
        "-m",
        "xzarrguard.cli",
        "check",
        str(store_path),
        "--json",
        "--timing",
    ]
    if strict_stale:
        cmd.append("--strict-stale")

    env = os.environ.copy()
    existing = env.get("PYTHONPATH")
    env["PYTHONPATH"] = str(SRC_PATH) if not existing else f"{SRC_PATH}:{existing}"

    wall_start = perf_counter()
    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=PROJECT_ROOT,
        env=env,
        check=False,
    )
    wall_s = perf_counter() - wall_start
    if proc.returncode not in (0, 1):
        raise RuntimeError(
            "benchmark run failed with non-check exit code "
            f"{proc.returncode}\nstderr:\n{proc.stderr}\nstdout:\n{proc.stdout}"
        )

    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            "failed to parse JSON output from check command\n"
            f"stderr:\n{proc.stderr}\nstdout:\n{proc.stdout}"
        ) from exc

    timing = payload.get("timing")
    if not isinstance(timing, dict):
        raise RuntimeError("check output did not include timing payload")

    return {
        "exit_code": proc.returncode,
        "ok": bool(payload.get("ok", False)),
        "wall_s": wall_s,
        "reported_total_s": float(timing.get("total_s", wall_s)),
        "scan_specs_s": float(timing.get("scan_specs_s", 0.0)),
        "manifest_s": float(timing.get("manifest_s", 0.0)),
        "chunk_scan_s": float(timing.get("chunk_scan_s", 0.0)),
        "exists_calls": int(timing.get("exists_calls", 0)),
    }


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("store_path", type=Path, help="Zarr store path to benchmark")
    parser.add_argument(
        "--runs",
        type=int,
        default=5,
        help="Number of measured runs (default: 5)",
    )
    parser.add_argument(
        "--warmup",
        type=int,
        default=1,
        help="Number of warmup runs (default: 1)",
    )
    parser.add_argument(
        "--python",
        default=sys.executable,
        help="Python interpreter used for benchmark runs (default: current interpreter)",
    )
    parser.add_argument(
        "--strict-stale",
        action="store_true",
        help="Pass --strict-stale to check runs",
    )
    parser.add_argument(
        "--out",
        type=Path,
        help="Optional file path to write detailed benchmark JSON results",
    )
    parser.add_argument(
        "--baseline",
        type=Path,
        help="Optional benchmark JSON file to compare against",
    )
    args = parser.parse_args(argv)
    if args.runs < 1:
        parser.error("--runs must be >= 1")
    if args.warmup < 0:
        parser.error("--warmup must be >= 0")
    return args


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv or sys.argv[1:])
    store_path = args.store_path.resolve()
    if not store_path.exists():
        print(f"error: store does not exist: {store_path}", file=sys.stderr)
        return 2

    for index in range(args.warmup):
        _run_once(store_path, python_bin=args.python, strict_stale=args.strict_stale)
        print(f"warmup {index + 1}/{args.warmup} complete")

    runs: list[dict[str, Any]] = []
    for index in range(args.runs):
        result = _run_once(store_path, python_bin=args.python, strict_stale=args.strict_stale)
        runs.append(result)
        print(
            f"run {index + 1}/{args.runs}: "
            f"reported_total={result['reported_total_s']:.3f}s "
            f"wall={result['wall_s']:.3f}s"
        )

    reported = [float(run["reported_total_s"]) for run in runs]
    wall = [float(run["wall_s"]) for run in runs]
    summary = {
        "reported_total_s": _summary(reported),
        "wall_s": _summary(wall),
        "exists_calls": int(runs[0]["exists_calls"]) if runs else 0,
    }

    output: dict[str, Any] = {
        "schema_version": 1,
        "timestamp_utc": datetime.now(UTC).isoformat(),
        "store_path": str(store_path),
        "python": args.python,
        "runs": args.runs,
        "warmup": args.warmup,
        "strict_stale": bool(args.strict_stale),
        "summary": summary,
        "per_run": runs,
    }

    if args.baseline is not None:
        baseline = json.loads(args.baseline.read_text(encoding="utf-8"))
        baseline_mean = float(baseline["summary"]["reported_total_s"]["mean"])
        current_mean = float(summary["reported_total_s"]["mean"])
        delta_pct = ((current_mean - baseline_mean) / baseline_mean) * 100.0
        output["comparison"] = {
            "baseline": str(args.baseline.resolve()),
            "baseline_mean_reported_total_s": baseline_mean,
            "current_mean_reported_total_s": current_mean,
            "delta_mean_pct": delta_pct,
        }

    print(
        "summary: "
        f"mean={summary['reported_total_s']['mean']:.3f}s "
        f"median={summary['reported_total_s']['median']:.3f}s "
        f"p95={summary['reported_total_s']['p95']:.3f}s"
    )
    if "comparison" in output:
        comparison = output["comparison"]
        print(
            "vs baseline: "
            f"{comparison['delta_mean_pct']:+.2f}% "
            f"({comparison['baseline_mean_reported_total_s']:.3f}s -> "
            f"{comparison['current_mean_reported_total_s']:.3f}s)"
        )

    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"wrote benchmark results: {args.out}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
