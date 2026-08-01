from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from workload.config import load_profiles  # noqa: E402
from workload.validator import validate_manifest_rows  # noqa: E402


class WorkloadValidationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.profile = load_profiles(ROOT / "config" / "workload_profiles.json")["small"]

    def test_duplicate_logical_id_rejected(self) -> None:
        rows = [
            {"logical_output_id": "dup", "group": "same-block", "creation_txid": "a", "vout": 0, "actual_spend_age_blocks": 0, "is_spent": True},
            {"logical_output_id": "dup", "group": "one-block", "creation_txid": "b", "vout": 0, "actual_spend_age_blocks": 1, "is_spent": True},
        ]
        errors = validate_manifest_rows(rows, self.profile)
        self.assertTrue(any("duplicate logical_output_id" in error for error in errors))

    def test_negative_age_rejected(self) -> None:
        rows = []
        for group in self.profile.groups:
            for index in range(group.count):
                rows.append(
                    {
                        "logical_output_id": f"{group.name}-{index}",
                        "group": group.name,
                        "creation_txid": f"tx-{group.name}-{index}",
                        "vout": index,
                        "actual_spend_age_blocks": -1 if group.name == "short-lived" and index == 0 else group.spend_age_blocks,
                        "is_spent": group.expected_state_at_end == "spent",
                    }
                )
        errors = validate_manifest_rows(rows, self.profile)
        self.assertTrue(any("negative age" in error for error in errors))

    def test_expected_counts_pass(self) -> None:
        rows = []
        vout = 0
        for group in self.profile.groups:
            for index in range(group.count):
                rows.append(
                    {
                        "logical_output_id": f"{group.name}-{index}",
                        "group": group.name,
                        "creation_txid": f"tx-{group.name}-{index}",
                        "vout": vout,
                        "actual_spend_age_blocks": group.spend_age_blocks,
                        "is_spent": group.expected_state_at_end == "spent",
                    }
                )
                vout += 1
        errors = validate_manifest_rows(rows, self.profile)
        self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main()
