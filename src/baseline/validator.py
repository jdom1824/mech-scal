from __future__ import annotations

from pathlib import Path

from workload.manifest import read_manifest_jsonl, sha256_of_file

from .config import EXPECTED_MANIFEST_HASH
from .database import BaselineDatabase


class BaselineValidator:
    def __init__(self, database: BaselineDatabase):
        self.database = database

    def validate_against_manifest(self, manifest_path: Path, run_id: str) -> dict[str, object]:
        manifest_hash = sha256_of_file(manifest_path)
        rows = read_manifest_jsonl(manifest_path)
        mismatches: list[str] = []
        seen_outpoints: set[tuple[str, int]] = set()
        spent_count = 0
        unspent_count = 0
        same_block_count = 0
        negative_age_count = 0

        for row in rows:
            outpoint = (str(row["creation_txid"]), int(row["vout"]))
            if outpoint in seen_outpoints:
                mismatches.append(f"duplicate outpoint in manifest: {outpoint[0]}:{outpoint[1]}")
            seen_outpoints.add(outpoint)
            db_row = self.database.get_output(*outpoint)
            if db_row is None:
                mismatches.append(f"missing output in baseline DB: {outpoint[0]}:{outpoint[1]}")
                continue
            if int(db_row["creation_height"]) != int(row["creation_height"]):
                mismatches.append(f"creation height mismatch for {outpoint[0]}:{outpoint[1]}")
            if str(db_row["creation_blockhash"]) != str(row["creation_blockhash"]):
                mismatches.append(f"creation blockhash mismatch for {outpoint[0]}:{outpoint[1]}")

            db_is_spent = bool(db_row["is_spent"])
            manifest_is_spent = bool(row["is_spent"])
            if db_is_spent != manifest_is_spent:
                mismatches.append(f"spent state mismatch for {outpoint[0]}:{outpoint[1]}")
            if db_is_spent:
                spent_count += 1
                if str(db_row["spend_txid"]) != str(row["spend_txid"]):
                    mismatches.append(f"spend txid mismatch for {outpoint[0]}:{outpoint[1]}")
                if int(db_row["spend_height"]) != int(row["spend_height"]):
                    mismatches.append(f"spend height mismatch for {outpoint[0]}:{outpoint[1]}")
                if str(db_row["spend_blockhash"]) != str(row["spend_blockhash"]):
                    mismatches.append(f"spend blockhash mismatch for {outpoint[0]}:{outpoint[1]}")
                age = int(db_row["spend_height"]) - int(db_row["creation_height"])
                if age < 0:
                    negative_age_count += 1
                    mismatches.append(f"negative age for {outpoint[0]}:{outpoint[1]}")
                if row["group"] == "same-block":
                    if int(db_row["creation_height"]) != int(db_row["spend_height"]):
                        mismatches.append(f"same-block mismatch for {outpoint[0]}:{outpoint[1]}")
                    else:
                        same_block_count += 1
            else:
                unspent_count += 1

        spend_orphans = self.database.conn.execute(
            """
            SELECT s.spend_txid, s.vin_index, s.prev_txid, s.prev_vout
            FROM spends s
            LEFT JOIN outputs o ON o.txid = s.prev_txid AND o.vout = s.prev_vout
            WHERE o.txid IS NULL
            """
        ).fetchall()
        for orphan in spend_orphans:
            mismatches.append(
                f"spend without previous output: {orphan['spend_txid']} vin={orphan['vin_index']} prev={orphan['prev_txid']}:{orphan['prev_vout']}"
            )

        result = {
            "manifest_hash": manifest_hash,
            "expected_manifest_hash": EXPECTED_MANIFEST_HASH,
            "manifest_hash_matches": manifest_hash == EXPECTED_MANIFEST_HASH,
            "experimental_outputs": len(rows),
            "spent_outputs": spent_count,
            "unspent_outputs": unspent_count,
            "same_block_matches": same_block_count,
            "negative_age_count": negative_age_count,
            "duplicate_outpoints": len(rows) - len(seen_outpoints),
            "spend_orphans": len(spend_orphans),
            "mismatches": mismatches,
            "status": "PASS" if not mismatches and manifest_hash == EXPECTED_MANIFEST_HASH else "FAIL",
        }
        self.database.replace_validation_result(run_id, result["status"], result)
        self.database.commit()
        return result
