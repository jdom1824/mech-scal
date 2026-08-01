from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mech_scal.classifier import OutputClassifier  # noqa: E402
from mech_scal.comparison import compare_baseline_mech_scal  # noqa: E402
from mech_scal.database import MechScalDatabase  # noqa: E402
from mech_scal.retrieval import MechScalRetriever  # noqa: E402


class MechScalLogicTests(unittest.TestCase):
    def setUp(self) -> None:
        self.classifier = OutputClassifier(24)

    def test_new_output_starts_in_mh(self) -> None:
        decision = self.classifier.classify_new_output()
        self.assertEqual(decision.to_class, "MH")

    def test_transition_exactly_at_t_min(self) -> None:
        decision = self.classifier.classify_temporal_transition("MH", 0, 24, False)
        self.assertIsNotNone(decision)
        self.assertEqual(decision.to_class, "ML")

    def test_no_transition_before_t_min(self) -> None:
        self.assertIsNone(self.classifier.classify_temporal_transition("MH", 0, 23, False))

    def test_spend_mh_to_im(self) -> None:
        decision = self.classifier.classify_spend("MH", 10, 20)
        self.assertEqual(decision.reason, "spent_from_mh")

    def test_spend_ml_to_im(self) -> None:
        decision = self.classifier.classify_spend("ML", 10, 40)
        self.assertEqual(decision.reason, "spent_from_ml")

    def test_same_block_spend(self) -> None:
        decision = self.classifier.classify_spend("MH", 10, 10)
        self.assertEqual(decision.reason, "same_block_spend")
        self.assertEqual(decision.age_blocks, 0)

    def test_reject_negative_age(self) -> None:
        with self.assertRaises(ValueError):
            self.classifier.classify_spend("MH", 20, 19)

    def test_im_is_terminal(self) -> None:
        with self.assertRaises(ValueError):
            self.classifier.classify_spend("IM", 10, 12)


class MechScalDatabaseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp.name) / "mech_scal.sqlite"
        self.db = MechScalDatabase(self.db_path)
        self.db.init_schema()
        self.db.insert_block({"height": 1, "blockhash": "b1", "time": 1, "tx_count": 1, "processed_at": "now"})
        self.db.insert_transaction({"txid": "tx1", "blockhash": "b1", "height": 1, "tx_index": 0, "is_coinbase": 0, "input_count": 0, "output_count": 1})
        self.db.insert_output({"txid": "tx1", "vout": 0, "creation_height": 1, "creation_blockhash": "b1", "value_sat": 1000, "script_type": "pubkeyhash", "address": None, "is_coinbase": 0, "is_spent": 0, "spend_txid": None, "spend_height": None, "spend_blockhash": None, "spend_age_blocks": None, "current_class": "MH", "class_updated_height": 1, "final_class": None})
        self.db.insert_transition({"txid": "tx1", "vout": 0, "from_class": None, "to_class": "MH", "transition_height": 1, "reason": "output_created", "age_blocks": 0, "executed_at": "now"})
        self.db.commit()

    def tearDown(self) -> None:
        self.db.close()
        self.tmp.cleanup()

    def test_no_duplicate_transition(self) -> None:
        self.db.insert_transition({"txid": "tx1", "vout": 0, "from_class": None, "to_class": "MH", "transition_height": 1, "reason": "output_created", "age_blocks": 0, "executed_at": "now"})
        self.db.commit()
        count = self.db.conn.execute("SELECT COUNT(*) FROM class_transitions").fetchone()[0]
        self.assertEqual(count, 1)

    def test_lookup_by_class_and_history(self) -> None:
        retriever = MechScalRetriever(self.db)
        self.assertTrue(retriever.by_class("MH").found)
        self.assertTrue(retriever.transition_history("tx1", 0).found)

    def test_snapshot_and_resume_primitives(self) -> None:
        self.db.replace_snapshot({"snapshot_height": 1, "mh_count": 1, "ml_count": 0, "im_count": 0, "total_classified_outputs": 1, "spent_count": 0, "unspent_count": 1, "created_at": "now"})
        row = self.db.conn.execute("SELECT * FROM class_snapshots WHERE snapshot_height = 1").fetchone()
        self.assertEqual(row["mh_count"], 1)

    def test_comparison_helper(self) -> None:
        baseline_db_path = Path(self.tmp.name) / "baseline.sqlite"
        import json
        import sqlite3
        conn = sqlite3.connect(baseline_db_path)
        conn.executescript(
            """
            CREATE TABLE blocks (height INTEGER);
            CREATE TABLE transactions (txid TEXT);
            CREATE TABLE outputs (txid TEXT, vout INTEGER);
            CREATE TABLE spends (spend_txid TEXT);
            INSERT INTO blocks VALUES (1);
            INSERT INTO transactions VALUES ('t');
            INSERT INTO outputs VALUES ('t', 0);
            INSERT INTO spends VALUES ('s');
            """
        )
        conn.commit()
        conn.close()
        baseline_summary = Path(self.tmp.name) / "baseline_summary.json"
        baseline_summary.write_text(json.dumps({"processing_metrics": {"total_seconds": 1.0, "sqlite_size_bytes": 10, "peak_rss_kib": 10, "rpc_reads": 10}, "lookup": {"phases": {"warm": {"p95": 1.0}}}}), encoding="utf-8")
        summary = compare_baseline_mech_scal(self.db, baseline_db_path, baseline_summary, {"processing_metrics": {"total_seconds": 2.0, "sqlite_size_bytes": 20, "peak_rss_kib": 20, "rpc_reads": 20}, "lookup": {"phases": {"warm": {"p95": 2.0}}}})
        self.assertEqual(summary["processing_overhead_percent"], 100.0)
