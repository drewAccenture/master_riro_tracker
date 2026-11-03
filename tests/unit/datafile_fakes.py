"""Helpers for the slice 8a data file tests (US-15, ADR-004, ADR-013). Synthetic data only."""

import json
from datetime import datetime
from pathlib import Path

NOW = datetime(2026, 11, 3, 9, 15, 42)
STAMP = "20261103-091542"
FILES_A = {"id-a": {"name": "Synthetic Joiner A.xlsx", "roll_on": "2026-10-01"}}
FILES_B = {"id-b": {"name": "Synthetic Joiner B.xlsx", "roll_on": "2026-10-15"}}


def paths(tmp_path):
    path = tmp_path / "data" / "tracker.json"
    return path, Path(str(path) + ".bak"), Path(str(path) + ".tmp")


def write_raw(path, data):
    """Write data as JSON in an unusual layout (so "byte-for-byte" means something) and return the bytes."""
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(data, indent=3, sort_keys=True).encode("utf-8") + b"\r\n"
    path.write_bytes(raw)
    return raw


def listing(folder):
    """{file name: bytes} for every file in the data folder."""
    return {p.name: p.read_bytes() for p in Path(folder).iterdir() if p.is_file()}


def version_copies(folder):
    return sorted(p.name for p in Path(folder).glob("tracker.json*.v*-*"))


def broken_copies(folder):
    return sorted(p.name for p in Path(folder).glob("tracker.json*.broken-*"))


class Steps:
    """Test-only upgrade steps n -> n+1. Each adds n to data["trail"] and records the copies on disk when it ran."""

    def __init__(self, folder, fail_at=None):
        self.folder = Path(folder)
        self.fail_at = fail_at
        self.calls = []
        self.copies_seen = []

    def step(self, n):
        def run(data):
            self.calls.append(n)
            self.copies_seen.append(version_copies(self.folder))
            if n == self.fail_at:
                raise ValueError(f"synthetic: step {n} cannot read this layout")
            return {
                **data,
                "trail": [*data.get("trail", []), n],
                "schema_version": n + 1,
            }

        return run

    def table(self, *versions):
        return {n: self.step(n) for n in versions}


def needs(key):
    """A validate function that only accepts data holding `key` (proves validate runs after the steps)."""

    def validate(data):
        if key not in data:
            raise ValueError(f"synthetic layout check: {key} missing")

    return validate
