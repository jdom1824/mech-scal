from __future__ import annotations

import json
import sqlite3
from pathlib import Path


class MechScalDatabase:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")

    def close(self) -> None:
        self.conn.close()

    def reset(self) -> None:
        self.close()
        if self.path.exists():
            self.path.unlink()
        self.__init__(self.path)

    def init_schema(self) -> None:
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS runs (
              run_id TEXT PRIMARY KEY,
              start_height INTEGER NOT NULL,
              end_height INTEGER NOT NULL,
              t_min INTEGER NOT NULL,
              status TEXT NOT NULL,
              started_at TEXT NOT NULL,
              finished_at TEXT,
              total_blocks INTEGER DEFAULT 0,
              total_transactions INTEGER DEFAULT 0,
              total_outputs INTEGER DEFAULT 0,
              total_inputs INTEGER DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS blocks (
              height INTEGER PRIMARY KEY,
              blockhash TEXT UNIQUE NOT NULL,
              time INTEGER,
              tx_count INTEGER NOT NULL,
              processed_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS transactions (
              txid TEXT PRIMARY KEY,
              blockhash TEXT NOT NULL,
              height INTEGER NOT NULL,
              tx_index INTEGER NOT NULL,
              is_coinbase INTEGER NOT NULL,
              input_count INTEGER NOT NULL,
              output_count INTEGER NOT NULL,
              FOREIGN KEY(height) REFERENCES blocks(height)
            );

            CREATE TABLE IF NOT EXISTS outputs (
              txid TEXT NOT NULL,
              vout INTEGER NOT NULL,
              creation_height INTEGER NOT NULL,
              creation_blockhash TEXT NOT NULL,
              value_sat INTEGER NOT NULL,
              script_type TEXT,
              address TEXT,
              is_coinbase INTEGER NOT NULL,
              is_spent INTEGER NOT NULL DEFAULT 0,
              spend_txid TEXT,
              spend_height INTEGER,
              spend_blockhash TEXT,
              spend_age_blocks INTEGER,
              current_class TEXT NOT NULL,
              class_updated_height INTEGER NOT NULL,
              final_class TEXT,
              PRIMARY KEY (txid, vout),
              FOREIGN KEY(txid) REFERENCES transactions(txid)
            );

            CREATE TABLE IF NOT EXISTS spends (
              spend_txid TEXT NOT NULL,
              vin_index INTEGER NOT NULL,
              prev_txid TEXT NOT NULL,
              prev_vout INTEGER NOT NULL,
              spend_height INTEGER NOT NULL,
              spend_blockhash TEXT NOT NULL,
              PRIMARY KEY (spend_txid, vin_index)
            );

            CREATE TABLE IF NOT EXISTS class_transitions (
              transition_id INTEGER PRIMARY KEY AUTOINCREMENT,
              txid TEXT NOT NULL,
              vout INTEGER NOT NULL,
              from_class TEXT,
              to_class TEXT NOT NULL,
              transition_height INTEGER NOT NULL,
              reason TEXT NOT NULL,
              age_blocks INTEGER NOT NULL,
              executed_at TEXT NOT NULL,
              UNIQUE(txid, vout, from_class, to_class, transition_height, reason)
            );

            CREATE TABLE IF NOT EXISTS class_snapshots (
              snapshot_height INTEGER PRIMARY KEY,
              mh_count INTEGER NOT NULL,
              ml_count INTEGER NOT NULL,
              im_count INTEGER NOT NULL,
              total_classified_outputs INTEGER NOT NULL,
              spent_count INTEGER NOT NULL,
              unspent_count INTEGER NOT NULL,
              created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS processing_metrics (
              run_id TEXT PRIMARY KEY,
              total_seconds REAL,
              blocks_processed INTEGER,
              transactions_processed INTEGER,
              outputs_processed INTEGER,
              inputs_processed INTEGER,
              outputs_per_second REAL,
              transactions_per_second REAL,
              average_block_seconds REAL,
              p50_block_seconds REAL,
              p95_block_seconds REAL,
              p99_block_seconds REAL,
              classification_seconds REAL,
              classification_seconds_per_output REAL,
              mh_to_ml_count INTEGER,
              mh_to_im_count INTEGER,
              ml_to_im_count INTEGER,
              same_block_spend_count INTEGER,
              final_mh_count INTEGER,
              final_ml_count INTEGER,
              final_im_count INTEGER,
              sqlite_size_bytes INTEGER,
              peak_rss_kib INTEGER,
              processor_cpu_percent REAL,
              rpc_reads INTEGER,
              retry_count INTEGER,
              error_count INTEGER,
              retrieval_seconds REAL,
              transition_persistence_seconds REAL,
              FOREIGN KEY(run_id) REFERENCES runs(run_id)
            );

            CREATE TABLE IF NOT EXISTS lookup_metrics (
              lookup_id INTEGER PRIMARY KEY AUTOINCREMENT,
              phase TEXT NOT NULL,
              query_type TEXT NOT NULL,
              target TEXT NOT NULL,
              found INTEGER NOT NULL,
              latency_ms REAL NOT NULL,
              error TEXT
            );

            CREATE TABLE IF NOT EXISTS validation_results (
              run_id TEXT PRIMARY KEY,
              status TEXT NOT NULL,
              summary_json TEXT NOT NULL,
              FOREIGN KEY(run_id) REFERENCES runs(run_id)
            );

            CREATE TABLE IF NOT EXISTS baseline_comparison (
              run_id TEXT PRIMARY KEY,
              summary_json TEXT NOT NULL,
              FOREIGN KEY(run_id) REFERENCES runs(run_id)
            );

            CREATE INDEX IF NOT EXISTS idx_outputs_txid_vout ON outputs (txid, vout);
            CREATE INDEX IF NOT EXISTS idx_outputs_creation_height ON outputs (creation_height);
            CREATE INDEX IF NOT EXISTS idx_outputs_spend_height ON outputs (spend_height);
            CREATE INDEX IF NOT EXISTS idx_outputs_is_spent ON outputs (is_spent);
            CREATE INDEX IF NOT EXISTS idx_outputs_current_class ON outputs (current_class);
            CREATE INDEX IF NOT EXISTS idx_outputs_final_class ON outputs (final_class);
            CREATE INDEX IF NOT EXISTS idx_outputs_class_updated_height ON outputs (class_updated_height);
            CREATE INDEX IF NOT EXISTS idx_blocks_blockhash ON blocks (blockhash);
            CREATE INDEX IF NOT EXISTS idx_spends_prev_outpoint ON spends (prev_txid, prev_vout);
            CREATE INDEX IF NOT EXISTS idx_transitions_outpoint ON class_transitions (txid, vout, transition_height);
            CREATE INDEX IF NOT EXISTS idx_transitions_to_class ON class_transitions (to_class);
            """
        )
        self.conn.commit()

    def begin(self) -> None:
        self.conn.execute("BEGIN")

    def commit(self) -> None:
        self.conn.commit()

    def rollback(self) -> None:
        self.conn.rollback()

    def upsert_run(self, payload: dict[str, object]) -> None:
        self.conn.execute(
            """
            INSERT INTO runs (run_id, start_height, end_height, t_min, status, started_at, finished_at, total_blocks, total_transactions, total_outputs, total_inputs)
            VALUES (:run_id, :start_height, :end_height, :t_min, :status, :started_at, :finished_at, :total_blocks, :total_transactions, :total_outputs, :total_inputs)
            ON CONFLICT(run_id) DO UPDATE SET
              status=excluded.status,
              finished_at=excluded.finished_at,
              total_blocks=excluded.total_blocks,
              total_transactions=excluded.total_transactions,
              total_outputs=excluded.total_outputs,
              total_inputs=excluded.total_inputs
            """,
            payload,
        )

    def insert_block(self, payload: dict[str, object]) -> None:
        self.conn.execute(
            "INSERT OR IGNORE INTO blocks (height, blockhash, time, tx_count, processed_at) VALUES (:height, :blockhash, :time, :tx_count, :processed_at)",
            payload,
        )

    def insert_transaction(self, payload: dict[str, object]) -> None:
        self.conn.execute(
            "INSERT OR IGNORE INTO transactions (txid, blockhash, height, tx_index, is_coinbase, input_count, output_count) VALUES (:txid, :blockhash, :height, :tx_index, :is_coinbase, :input_count, :output_count)",
            payload,
        )

    def insert_output(self, payload: dict[str, object]) -> None:
        self.conn.execute(
            """
            INSERT INTO outputs (
              txid, vout, creation_height, creation_blockhash, value_sat, script_type, address, is_coinbase,
              is_spent, spend_txid, spend_height, spend_blockhash, spend_age_blocks, current_class, class_updated_height, final_class
            )
            VALUES (
              :txid, :vout, :creation_height, :creation_blockhash, :value_sat, :script_type, :address, :is_coinbase,
              :is_spent, :spend_txid, :spend_height, :spend_blockhash, :spend_age_blocks, :current_class, :class_updated_height, :final_class
            )
            ON CONFLICT(txid, vout) DO UPDATE SET
              creation_height=excluded.creation_height,
              creation_blockhash=excluded.creation_blockhash,
              value_sat=excluded.value_sat,
              script_type=excluded.script_type,
              address=excluded.address,
              is_coinbase=excluded.is_coinbase
            """,
            payload,
        )

    def insert_spend(self, payload: dict[str, object]) -> None:
        self.conn.execute(
            "INSERT OR IGNORE INTO spends (spend_txid, vin_index, prev_txid, prev_vout, spend_height, spend_blockhash) VALUES (:spend_txid, :vin_index, :prev_txid, :prev_vout, :spend_height, :spend_blockhash)",
            payload,
        )

    def get_output(self, txid: str, vout: int) -> sqlite3.Row | None:
        return self.conn.execute("SELECT * FROM outputs WHERE txid = ? AND vout = ?", (txid, vout)).fetchone()

    def update_output_class(self, txid: str, vout: int, current_class: str, class_updated_height: int, final_class: str | None = None) -> None:
        self.conn.execute(
            "UPDATE outputs SET current_class = ?, class_updated_height = ?, final_class = COALESCE(?, final_class) WHERE txid = ? AND vout = ?",
            (current_class, class_updated_height, final_class, txid, vout),
        )

    def mark_output_spent(self, prev_txid: str, prev_vout: int, spend_txid: str, spend_height: int, spend_blockhash: str, spend_age_blocks: int) -> int:
        cur = self.conn.execute(
            """
            UPDATE outputs
            SET is_spent = 1,
                spend_txid = ?,
                spend_height = ?,
                spend_blockhash = ?,
                spend_age_blocks = ?,
                final_class = 'IM'
            WHERE txid = ? AND vout = ?
            """,
            (spend_txid, spend_height, spend_blockhash, spend_age_blocks, prev_txid, prev_vout),
        )
        return cur.rowcount

    def insert_transition(self, payload: dict[str, object]) -> None:
        existing = self.conn.execute(
            """
            SELECT 1
            FROM class_transitions
            WHERE txid = :txid
              AND vout = :vout
              AND COALESCE(from_class, '') = COALESCE(:from_class, '')
              AND to_class = :to_class
              AND transition_height = :transition_height
              AND reason = :reason
            """,
            payload,
        ).fetchone()
        if existing is None:
            self.conn.execute(
                """
                INSERT INTO class_transitions (txid, vout, from_class, to_class, transition_height, reason, age_blocks, executed_at)
                VALUES (:txid, :vout, :from_class, :to_class, :transition_height, :reason, :age_blocks, :executed_at)
                """,
                payload,
            )

    def replace_snapshot(self, payload: dict[str, object]) -> None:
        self.conn.execute(
            """
            INSERT OR REPLACE INTO class_snapshots (snapshot_height, mh_count, ml_count, im_count, total_classified_outputs, spent_count, unspent_count, created_at)
            VALUES (:snapshot_height, :mh_count, :ml_count, :im_count, :total_classified_outputs, :spent_count, :unspent_count, :created_at)
            """,
            payload,
        )

    def max_processed_height(self) -> int | None:
        row = self.conn.execute("SELECT MAX(height) AS max_height FROM blocks").fetchone()
        return None if row is None or row["max_height"] is None else int(row["max_height"])

    def insert_processing_metrics(self, payload: dict[str, object]) -> None:
        self.conn.execute(
            """
            INSERT OR REPLACE INTO processing_metrics (
              run_id, total_seconds, blocks_processed, transactions_processed, outputs_processed, inputs_processed,
              outputs_per_second, transactions_per_second, average_block_seconds, p50_block_seconds, p95_block_seconds, p99_block_seconds,
              classification_seconds, classification_seconds_per_output, mh_to_ml_count, mh_to_im_count, ml_to_im_count,
              same_block_spend_count, final_mh_count, final_ml_count, final_im_count, sqlite_size_bytes, peak_rss_kib,
              processor_cpu_percent, rpc_reads, retry_count, error_count, retrieval_seconds, transition_persistence_seconds
            ) VALUES (
              :run_id, :total_seconds, :blocks_processed, :transactions_processed, :outputs_processed, :inputs_processed,
              :outputs_per_second, :transactions_per_second, :average_block_seconds, :p50_block_seconds, :p95_block_seconds, :p99_block_seconds,
              :classification_seconds, :classification_seconds_per_output, :mh_to_ml_count, :mh_to_im_count, :ml_to_im_count,
              :same_block_spend_count, :final_mh_count, :final_ml_count, :final_im_count, :sqlite_size_bytes, :peak_rss_kib,
              :processor_cpu_percent, :rpc_reads, :retry_count, :error_count, :retrieval_seconds, :transition_persistence_seconds
            )
            """,
            payload,
        )

    def insert_lookup_metric(self, payload: dict[str, object]) -> None:
        self.conn.execute(
            "INSERT INTO lookup_metrics (phase, query_type, target, found, latency_ms, error) VALUES (:phase, :query_type, :target, :found, :latency_ms, :error)",
            payload,
        )

    def replace_validation_result(self, run_id: str, status: str, summary: dict[str, object]) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO validation_results (run_id, status, summary_json) VALUES (?, ?, ?)",
            (run_id, status, json.dumps(summary, sort_keys=True)),
        )

    def replace_baseline_comparison(self, run_id: str, summary: dict[str, object]) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO baseline_comparison (run_id, summary_json) VALUES (?, ?)",
            (run_id, json.dumps(summary, sort_keys=True)),
        )

    def count_rows(self, table: str) -> int:
        return int(self.conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
