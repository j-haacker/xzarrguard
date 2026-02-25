"""Public report models for xzarrguard."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class ChunkRef:
    """Reference to one logical chunk."""

    coord: tuple[int, ...]
    key: str

    def to_dict(self) -> dict[str, Any]:
        return {"coord": list(self.coord), "key": self.key}


@dataclass(slots=True)
class VariableIntegrity:
    """Per-variable integrity results."""

    name: str
    expected_chunks: int
    has_manifest: bool
    missing_unexpected: list[ChunkRef] = field(default_factory=list)
    missing_allowed: list[ChunkRef] = field(default_factory=list)
    stale_manifest: list[ChunkRef] = field(default_factory=list)
    manifest_key_mismatch: list[ChunkRef] = field(default_factory=list)
    manifest_out_of_bounds: list[ChunkRef] = field(default_factory=list)
    ok: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "ok": self.ok,
            "has_manifest": self.has_manifest,
            "expected_chunks": self.expected_chunks,
            "missing_unexpected": [item.to_dict() for item in self.missing_unexpected],
            "missing_allowed": [item.to_dict() for item in self.missing_allowed],
            "stale_manifest": [item.to_dict() for item in self.stale_manifest],
            "manifest_key_mismatch": [item.to_dict() for item in self.manifest_key_mismatch],
            "manifest_out_of_bounds": [item.to_dict() for item in self.manifest_out_of_bounds],
        }


@dataclass(slots=True)
class IntegrityReport:
    """Integrity report for a store."""

    store_path: str
    strict_stale_manifest: bool
    variables: dict[str, VariableIntegrity] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    timing: IntegrityTiming | None = None
    ok: bool = True

    def __bool__(self) -> bool:
        return self.ok

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "store_path": self.store_path,
            "strict_stale_manifest": self.strict_stale_manifest,
            "ok": self.ok,
            "errors": list(self.errors),
            "variables": {name: report.to_dict() for name, report in self.variables.items()},
        }
        if self.timing is not None:
            payload["timing"] = self.timing.to_dict()
        return payload


@dataclass(slots=True)
class VariableTiming:
    """Timing details for one variable check."""

    manifest_load_s: float = 0.0
    manifest_validate_s: float = 0.0
    chunk_scan_s: float = 0.0
    expected_chunks: int = 0
    missing_chunks: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "manifest_load_s": self.manifest_load_s,
            "manifest_validate_s": self.manifest_validate_s,
            "chunk_scan_s": self.chunk_scan_s,
            "expected_chunks": self.expected_chunks,
            "missing_chunks": self.missing_chunks,
        }


@dataclass(slots=True)
class IntegrityTiming:
    """Optional coarse-grained timing information for `check_store`."""

    total_s: float = 0.0
    scan_specs_s: float = 0.0
    manifest_s: float = 0.0
    chunk_scan_s: float = 0.0
    exists_calls: int = 0
    variables: dict[str, VariableTiming] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_s": self.total_s,
            "scan_specs_s": self.scan_specs_s,
            "manifest_s": self.manifest_s,
            "chunk_scan_s": self.chunk_scan_s,
            "exists_calls": self.exists_calls,
            "variables": {name: item.to_dict() for name, item in self.variables.items()},
        }


@dataclass(slots=True)
class CreateReport:
    """Result of creating a store with optional no-data policy."""

    store_path: str
    no_data_strategy: str
    manifests_written: list[str] = field(default_factory=list)
    removed_chunks: dict[str, list[ChunkRef]] = field(default_factory=dict)
    ok: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "store_path": self.store_path,
            "no_data_strategy": self.no_data_strategy,
            "ok": self.ok,
            "manifests_written": list(self.manifests_written),
            "removed_chunks": {
                name: [item.to_dict() for item in refs]
                for name, refs in self.removed_chunks.items()
            },
        }
