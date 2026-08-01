from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from .config import REGTEST_CLI, WALLET_NAME, WorkloadProfile
from .manifest import read_manifest_jsonl, sha256_of_file
from .rpc import RegtestRPC


def validate_manifest_rows(rows: list[dict[str, object]], profile: WorkloadProfile) -> list[str]:
    errors: list[str] = []
    logical_ids = [str(row["logical_output_id"]) for row in rows]
    if len(logical_ids) != len(set(logical_ids)):
        errors.append("duplicate logical_output_id detected")
    outpoints = [(row.get("creation_txid"), row.get("vout")) for row in rows]
    if len(outpoints) != len(set(outpoints)):
        errors.append("duplicate creation outpoint detected")
    expected_counts = {group.name: group.count for group in profile.groups}
    actual_counts = Counter(str(row["group"]) for row in rows)
    if expected_counts != dict(actual_counts):
        errors.append(f"group counts mismatch: expected={expected_counts} actual={dict(actual_counts)}")
    for row in rows:
        age = row.get("actual_spend_age_blocks")
        if age is not None and int(age) < 0:
            errors.append(f"negative age for {row['logical_output_id']}")
        same_block_age = row.get("actual_spend_age_blocks")
        if str(row["group"]) == "same-block" and row.get("is_spent") and same_block_age is not None and int(same_block_age) != 0:
            errors.append(f"same-block output does not have age 0: {row['logical_output_id']}")
    return errors


class WorkloadValidator:
    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.rpc = RegtestRPC(REGTEST_CLI, project_root)

    def validate_output_dir(self, output_dir: Path, profile: WorkloadProfile) -> dict[str, object]:
        manifest_path = output_dir / "manifest.jsonl"
        summary_path = output_dir / "summary.json"
        rows = read_manifest_jsonl(manifest_path)
        errors = validate_manifest_rows(rows, profile)
        chain_info = self.rpc.ensure_chain()
        for row in rows:
            creation_txid = row["creation_txid"]
            if creation_txid is None:
                continue
            tx = self.rpc.tx(str(creation_txid))
            header = self.rpc.block_header(str(tx["blockhash"]))
            if int(row["creation_height"]) != int(header["height"]):
                errors.append(f"creation height mismatch for {row['logical_output_id']}")
            if row["creation_blockhash"] != tx["blockhash"]:
                errors.append(f"creation blockhash mismatch for {row['logical_output_id']}")
            txout_raw = self.rpc.cli("gettxout", str(creation_txid), str(row["vout"]), "true")
            txout = json.loads(txout_raw) if txout_raw else None
            is_spent = bool(row["is_spent"])
            if is_spent and txout is not None:
                errors.append(f"spent output still unspent according to gettxout: {row['logical_output_id']}")
            if not is_spent and txout is None:
                errors.append(f"expected unspent output is missing: {row['logical_output_id']}")
            spend_txid = row.get("spend_txid")
            if spend_txid:
                spend_tx = self.rpc.tx(str(spend_txid))
                spend_header = self.rpc.block_header(str(spend_tx["blockhash"]))
                if int(row["spend_height"]) != int(spend_header["height"]):
                    errors.append(f"spend height mismatch for {row['logical_output_id']}")
                if row["spend_blockhash"] != spend_tx["blockhash"]:
                    errors.append(f"spend blockhash mismatch for {row['logical_output_id']}")
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        manifest_hash = sha256_of_file(manifest_path)
        if summary.get("manifest_hash") != manifest_hash:
            errors.append("manifest hash mismatch")
        if int(summary.get("final_chain_height", -1)) != int(chain_info["blocks"]):
            errors.append("final chain height mismatch")
        result = {
            "chain": chain_info["chain"],
            "final_chain_height": chain_info["blocks"],
            "manifest_hash": manifest_hash,
            "errors": errors,
            "status": "PASS" if not errors else "FAIL",
            "wallet_name": WALLET_NAME,
        }
        (output_dir / "validation_results.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        return result
