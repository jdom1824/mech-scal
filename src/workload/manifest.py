from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter
from pathlib import Path

from .models import OutputRecord

FIELDNAMES = [
    "run_id",
    "profile",
    "seed",
    "logical_output_id",
    "group",
    "creation_txid",
    "vout",
    "creation_height",
    "creation_blockhash",
    "value_btc",
    "address",
    "expected_spend_age_blocks",
    "spend_txid",
    "spend_height",
    "spend_blockhash",
    "actual_spend_age_blocks",
    "is_spent",
    "expected_state_at_end",
    "final_chain_height",
    "validation_status",
]


def write_manifest_jsonl(path: Path, records: list[OutputRecord]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record.to_dict(), sort_keys=True) + "\n")


def write_manifest_csv(path: Path, records: list[OutputRecord]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDNAMES)
        writer.writeheader()
        for record in records:
            writer.writerow(record.to_dict())


def read_manifest_jsonl(path: Path) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def sha256_of_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def summarize_records(records: list[OutputRecord]) -> dict[str, object]:
    counts = Counter(record.group for record in records)
    spent = [record for record in records if record.is_spent]
    ages = [record.actual_spend_age_blocks for record in spent if record.actual_spend_age_blocks is not None]
    logical_ids = [record.logical_output_id for record in records]
    outpoints = [(record.creation_txid, record.vout) for record in records]
    return {
        "total_experimental_outputs": len(records),
        "total_spent": len(spent),
        "total_unspent": len(records) - len(spent),
        "total_by_group": dict(counts),
        "minimum_age": min(ages) if ages else None,
        "maximum_age": max(ages) if ages else None,
        "same_block_spends": sum(1 for age in ages if age == 0),
        "invalid_negative_ages": sum(1 for age in ages if age < 0),
        "duplicate_logical_ids": len(logical_ids) - len(set(logical_ids)),
        "duplicate_outpoints": len(outpoints) - len(set(outpoints)),
    }
