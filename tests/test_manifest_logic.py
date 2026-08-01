from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from workload.manifest import (  # noqa: E402
    read_manifest_jsonl,
    summarize_records,
    write_manifest_csv,
    write_manifest_jsonl,
)
from workload.models import OutputRecord  # noqa: E402


class ManifestLogicTests(unittest.TestCase):
    def test_summary_counts_and_ages(self) -> None:
        records = [
            OutputRecord("r", "small", 1, "id-1", "same-block", actual_spend_age_blocks=0, is_spent=True),
            OutputRecord("r", "small", 1, "id-2", "long-lived-unspent", is_spent=False),
        ]
        summary = summarize_records(records)
        self.assertEqual(summary["total_experimental_outputs"], 2)
        self.assertEqual(summary["same_block_spends"], 1)
        self.assertEqual(summary["total_unspent"], 1)

    def test_jsonl_and_csv_roundtrip(self) -> None:
        record = OutputRecord("r", "small", 1, "id-1", "one-block", creation_txid="abc", vout=0, is_spent=True)
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            jsonl = tmp_path / "manifest.jsonl"
            csv_path = tmp_path / "manifest.csv"
            write_manifest_jsonl(jsonl, [record])
            write_manifest_csv(csv_path, [record])
            rows = read_manifest_jsonl(jsonl)
            self.assertEqual(rows[0]["logical_output_id"], "id-1")
            self.assertTrue(csv_path.exists())


if __name__ == "__main__":
    unittest.main()
