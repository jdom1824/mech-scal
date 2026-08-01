from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from baseline.database import BaselineDatabase  # noqa: E402


class BaselineDatabaseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db = BaselineDatabase(Path(self.tmp.name) / "baseline.sqlite")
        self.db.init_schema()

    def tearDown(self) -> None:
        self.db.close()
        self.tmp.cleanup()

    def test_schema_creation(self) -> None:
        tables = {
            row["name"]
            for row in self.db.conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
            if not row["name"].startswith("sqlite_")
        }
        self.assertIn("outputs", tables)
        self.assertIn("spends", tables)

    def test_idempotent_output_insertion(self) -> None:
        payload = {
            "txid": "tx1",
            "blockhash": "b1",
            "height": 1,
            "tx_index": 0,
            "is_coinbase": 0,
            "input_count": 1,
            "output_count": 1,
        }
        self.db.insert_block({"height": 1, "blockhash": "b1", "time": 1, "tx_count": 1, "processed_at": "now"})
        self.db.insert_transaction(payload)
        output = {
            "txid": "tx1",
            "vout": 0,
            "creation_height": 1,
            "creation_blockhash": "b1",
            "value_sat": 1000,
            "script_type": "witness_v0_keyhash",
            "address": "addr",
            "is_coinbase": 0,
            "is_spent": 0,
            "spend_txid": None,
            "spend_height": None,
            "spend_blockhash": None,
        }
        self.db.insert_output(output)
        self.db.insert_output(output)
        self.db.commit()
        self.assertEqual(self.db.count_rows("outputs"), 1)

    def test_mark_output_spent(self) -> None:
        self.db.insert_block({"height": 1, "blockhash": "b1", "time": 1, "tx_count": 1, "processed_at": "now"})
        self.db.insert_transaction({"txid": "tx1", "blockhash": "b1", "height": 1, "tx_index": 0, "is_coinbase": 0, "input_count": 0, "output_count": 1})
        self.db.insert_output({"txid": "tx1", "vout": 0, "creation_height": 1, "creation_blockhash": "b1", "value_sat": 1000, "script_type": "pubkeyhash", "address": None, "is_coinbase": 0, "is_spent": 0, "spend_txid": None, "spend_height": None, "spend_blockhash": None})
        updated = self.db.mark_output_spent("tx1", 0, "spend1", 2, "b2")
        self.assertEqual(updated, 1)
        row = self.db.get_output("tx1", 0)
        self.assertEqual(row["spend_height"], 2)
