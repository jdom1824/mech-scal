from __future__ import annotations

from pathlib import Path

from workload.manifest import read_manifest_jsonl, sha256_of_file

from .config import EXPECTED_MANIFEST_HASH
from .database import MechScalDatabase


class MechScalValidator:
    def __init__(self, database: MechScalDatabase, t_min: int):
        self.database = database
        self.t_min = t_min

    def validate(self, manifest_path: Path, run_id: str) -> dict[str, object]:
        rows = read_manifest_jsonl(manifest_path)
        manifest_hash = sha256_of_file(manifest_path)
        mismatches: list[str] = []
        seen_outpoints: set[tuple[str, int]] = set()
        spent_count = 0
        unspent_count = 0
        same_block_count = 0
        mh_to_ml = 0
        mh_to_im = 0
        ml_to_im = 0
        negative_age = 0

        for item in rows:
            outpoint = (str(item["creation_txid"]), int(item["vout"]))
            if outpoint in seen_outpoints:
                mismatches.append(f"duplicate outpoint in manifest: {outpoint[0]}:{outpoint[1]}")
            seen_outpoints.add(outpoint)
            db_row = self.database.get_output(*outpoint)
            if db_row is None:
                mismatches.append(f"missing output: {outpoint[0]}:{outpoint[1]}")
                continue
            if int(db_row["creation_height"]) != int(item["creation_height"]):
                mismatches.append(f"creation height mismatch: {outpoint[0]}:{outpoint[1]}")
            if bool(db_row["is_spent"]) != bool(item["is_spent"]):
                mismatches.append(f"spent state mismatch: {outpoint[0]}:{outpoint[1]}")
            if bool(db_row["is_spent"]):
                spent_count += 1
                age = int(db_row["spend_age_blocks"])
                if age < 0:
                    negative_age += 1
                    mismatches.append(f"negative age: {outpoint[0]}:{outpoint[1]}")
                if item["group"] == "same-block":
                    if age != 0:
                        mismatches.append(f"same-block age mismatch: {outpoint[0]}:{outpoint[1]}")
                    else:
                        same_block_count += 1
                if db_row["current_class"] != "IM" or db_row["final_class"] != "IM":
                    mismatches.append(f"spent output not terminal IM: {outpoint[0]}:{outpoint[1]}")
            else:
                unspent_count += 1
                if db_row["current_class"] == "IM":
                    mismatches.append(f"unspent output in IM: {outpoint[0]}:{outpoint[1]}")
            history = list(
                self.database.conn.execute(
                    "SELECT * FROM class_transitions WHERE txid = ? AND vout = ? ORDER BY transition_height, transition_id",
                    outpoint,
                )
            )
            seen_transition_keys = set()
            for transition in history:
                key = (
                    transition["from_class"],
                    transition["to_class"],
                    transition["transition_height"],
                    transition["reason"],
                )
                if key in seen_transition_keys:
                    mismatches.append(f"duplicate transition: {outpoint[0]}:{outpoint[1]}")
                seen_transition_keys.add(key)
                if transition["from_class"] == "IM" and transition["to_class"] in {"MH", "ML"}:
                    mismatches.append(f"IM transitioned backward: {outpoint[0]}:{outpoint[1]}")
                if transition["reason"] == "reached_t_min" and int(transition["age_blocks"]) < self.t_min:
                    mismatches.append(f"ML transition before t_min: {outpoint[0]}:{outpoint[1]}")
            mh_to_ml += sum(1 for transition in history if transition["from_class"] == "MH" and transition["to_class"] == "ML")
            mh_to_im += sum(1 for transition in history if transition["from_class"] == "MH" and transition["to_class"] == "IM")
            ml_to_im += sum(1 for transition in history if transition["from_class"] == "ML" and transition["to_class"] == "IM")

        spend_orphans = self.database.conn.execute(
            """
            SELECT s.spend_txid, s.prev_txid, s.prev_vout
            FROM spends s
            LEFT JOIN outputs o ON o.txid = s.prev_txid AND o.vout = s.prev_vout
            WHERE o.txid IS NULL
            """
        ).fetchall()
        if spend_orphans:
            mismatches.extend([f"spend orphan: {row['spend_txid']}->{row['prev_txid']}:{row['prev_vout']}" for row in spend_orphans])

        snapshots = [dict(row) for row in self.database.conn.execute("SELECT * FROM class_snapshots ORDER BY snapshot_height")]
        for snapshot in snapshots:
            if snapshot["mh_count"] + snapshot["ml_count"] + snapshot["im_count"] != snapshot["total_classified_outputs"]:
                mismatches.append(f"inconsistent snapshot at height {snapshot['snapshot_height']}")

        result = {
            "manifest_hash": manifest_hash,
            "expected_manifest_hash": EXPECTED_MANIFEST_HASH,
            "manifest_hash_matches": manifest_hash == EXPECTED_MANIFEST_HASH,
            "experimental_outputs": len(rows),
            "spent_outputs": spent_count,
            "unspent_outputs": unspent_count,
            "same_block_matches": same_block_count,
            "negative_age_count": negative_age,
            "mh_to_ml_count": mh_to_ml,
            "mh_to_im_count": mh_to_im,
            "ml_to_im_count": ml_to_im,
            "duplicate_outpoints": len(rows) - len(seen_outpoints),
            "spend_orphans": len(spend_orphans),
            "snapshots": snapshots,
            "mismatches": mismatches,
            "status": "PASS" if not mismatches and manifest_hash == EXPECTED_MANIFEST_HASH else "FAIL",
        }
        self.database.replace_validation_result(run_id, result["status"], result)
        self.database.commit()
        return result
