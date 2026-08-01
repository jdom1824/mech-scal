from __future__ import annotations

from pathlib import Path

from workload.manifest import read_manifest_jsonl


def experimental_groups(manifest_path: Path) -> tuple[list[str], dict[str, str]]:
    rows = read_manifest_jsonl(manifest_path)
    outpoints = [f"{row['creation_txid']}:{row['vout']}" for row in rows]
    groups = {f"{row['creation_txid']}:{row['vout']}": str(row["group"]) for row in rows}
    return outpoints, groups
