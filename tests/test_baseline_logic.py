from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from baseline.database import BaselineDatabase  # noqa: E402
from baseline.metrics import compute_percentiles  # noqa: E402
from baseline.retrieval import BaselineRetriever  # noqa: E402


class BaselineLogicTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db = BaselineDatabase(Path(self.tmp.name) / "baseline.sqlite")
        self.db.init_schema()
        self.db.insert_block({"height": 1, "blockhash": "b1", "time": 1, "tx_count": 2, "processed_at": "now"})
        self.db.insert_transaction({"txid": "parent", "blockhash": "b1", "height": 1, "tx_index": 0, "is_coinbase": 0, "input_count": 0, "output_count": 1})
        self.db.insert_transaction({"txid": "child", "blockhash": "b1", "height": 1, "tx_index": 1, "is_coinbase": 0, "input_count": 1, "output_count": 1})
        self.db.insert_output({"txid": "parent", "vout": 0, "creation_height": 1, "creation_blockhash": "b1", "value_sat": 1000, "script_type": "pubkeyhash", "address": None, "is_coinbase": 0, "is_spent": 0, "spend_txid": None, "spend_height": None, "spend_blockhash": None})
        self.db.insert_spend({"spend_txid": "child", "vin_index": 0, "prev_txid": "parent", "prev_vout": 0, "spend_height": 1, "spend_blockhash": "b1"})
        self.db.mark_output_spent("parent", 0, "child", 1, "b1")
        self.db.commit()

    def tearDown(self) -> None:
        self.db.close()
        self.tmp.cleanup()

    def test_same_block_spend(self) -> None:
        row = self.db.get_output("parent", 0)
        self.assertEqual(row["creation_height"], row["spend_height"])

    def test_lookup_existing_and_missing(self) -> None:
        retriever = BaselineRetriever(self.db)
        self.assertTrue(retriever.by_outpoint("parent:0").found)
        self.assertFalse(retriever.by_outpoint("missing:0").found)

    def test_percentile_calculation(self) -> None:
        stats = compute_percentiles([1.0, 2.0, 3.0, 4.0, 5.0])
        self.assertAlmostEqual(stats["p50"], 3.0)
        self.assertGreater(stats["p95"], 4.0)

    def test_coinbase_style_flag_can_be_stored(self) -> None:
        self.db.insert_transaction({"txid": "coinbase_tx", "blockhash": "b1", "height": 1, "tx_index": 2, "is_coinbase": 1, "input_count": 0, "output_count": 1})
        self.db.insert_output({"txid": "coinbase_tx", "vout": 0, "creation_height": 1, "creation_blockhash": "b1", "value_sat": 5000000000, "script_type": "pubkey", "address": None, "is_coinbase": 1, "is_spent": 0, "spend_txid": None, "spend_height": None, "spend_blockhash": None})
        row = self.db.get_output("coinbase_tx", 0)
        self.assertEqual(row["is_coinbase"], 1)
