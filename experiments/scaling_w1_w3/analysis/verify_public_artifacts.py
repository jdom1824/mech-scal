#!/usr/bin/env python3
"""Verify the public W1--W3 package without rerunning Bitcoin Core."""
from __future__ import annotations

import csv
import hashlib
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
RESULTS = PACKAGE_ROOT / "results"
REQUIRED = [
    "scaling_master_runs.csv",
    "scaling_master_pairs.csv",
    "scaling_summary_by_workload.csv",
    "scaling_lookup_run_level.csv",
    "scaling_dbstat_per_run.csv",
    "evidence_integrity_checks.csv",
    "table6_reproduced.csv",
]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    for name in REQUIRED:
        path = RESULTS / name
        if not path.is_file() or path.stat().st_size == 0:
            raise SystemExit(f"FAIL: missing or empty public artifact: {path}")
    manifest = PACKAGE_ROOT / "manifests" / "public_sha256sums.txt"
    if not manifest.is_file():
        raise SystemExit(f"FAIL: missing manifest: {manifest}")
    checked = 0
    for line in manifest.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        expected, relative = line.split("  ", 1)
        path = PACKAGE_ROOT / relative
        if not path.is_file() or sha256(path) != expected:
            raise SystemExit(f"FAIL: manifest mismatch: {relative}")
        checked += 1
    if checked == 0:
        raise SystemExit("FAIL: empty manifest")
    rows = list(csv.DictReader((RESULTS / "table6_reproduced.csv").open(newline="", encoding="utf-8")))
    if [row["workload"] for row in rows] != ["W1", "W2", "W3"]:
        raise SystemExit("FAIL: Table 6 output workload order mismatch")
    print(f"PASS: {checked} public file hashes verified")
    print("PASS: frozen result package is self-contained for lightweight verification")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
