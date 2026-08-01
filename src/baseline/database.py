from __future__ import annotations

import json
import sqlite3
from pathlib import Path


class BaselineDatabase:
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
              sqlite_size_bytes INTEGER,
              peak_rss_kib INTEGER,
              processor_cpu_percent REAL,
              rpc_reads INTEGER,
              retry_count INTEGER,
              error_count INTEGER,
              FOREIGN KEY(run_id) REFERENCES runs(run_id)
            );

            CREATE TABLE IF NOT EXISTS lookup_metrics (
              lookup_id INTEGER PRIMARY KEY AUTOINCREMENT,
              phase TEXT NOT NULL,
              query_type TEXT NOT NULL,
              outpoint TEXT NOT NULL,
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

            CREATE INDEX IF NOT EXISTS idx_outputs_creation_height ON outputs (creation_height);
            CREATE INDEX IF NOT EXISTS idx_outputs_spend_height ON outputs (spend_height);
            CREATE INDEX IF NOT EXISTS idx_outputs_is_spent ON outputs (is_spent);
            CREATE INDEX IF NOT EXISTS idx_outputs_txid ON outputs (txid);
            CREATE INDEX IF NOT EXISTS idx_outputs_creation_blockhash ON outputs (creation_blockhash);
            CREATE INDEX IF NOT EXISTS idx_outputs_spend_blockhash ON outputs (spend_blockhash);
            CREATE INDEX IF NOT EXISTS idx_transactions_blockhash ON transactions (blockhash);
            CREATE INDEX IF NOT EXISTS idx_spends_prev_outpoint ON spends (prev_txid, prev_vout);
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
            INSERT INTO runs (run_id, start_height, end_height, status, started_at, finished_at, total_blocks, total_transactions, total_outputs, total_inputs)
            VALUES (:run_id, :start_height, :end_height, :status, :started_at, :finished_at, :total_blocks, :total_transactions, :total_outputs, :total_inputs)
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
            """
            INSERT OR IGNORE INTO blocks (height, blockhash, time, tx_count, processed_at)
            VALUES (:height, :blockhash, :time, :tx_count, :processed_at)
            """,
            payload,
        )

    def insert_transaction(self, payload: dict[str, object]) -> None:
        self.conn.execute(
            """
            INSERT OR IGNORE INTO transactions (txid, blockhash, height, tx_index, is_coinbase, input_count, output_count)
            VALUES (:txid, :blockhash, :height, :tx_index, :is_coinbase, :input_count, :output_count)
            """,
            payload,
        )

    def insert_output(self, payload: dict[str, object]) -> None:
        self.conn.execute(
            """
            INSERT INTO outputs (txid, vout, creation_height, creation_blockhash, value_sat, script_type, address, is_coinbase, is_spent, spend_txid, spend_height, spend_blockhash)
            VALUES (:txid, :vout, :creation_height, :creation_blockhash, :value_sat, :script_type, :address, :is_coinbase, :is_spent, :spend_txid, :spend_height, :spend_blockhash)
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
            """
            INSERT OR IGNORE INTO spends (spend_txid, vin_index, prev_txid, prev_vout, spend_height, spend_blockhash)
            VALUES (:spend_txid, :vin_index, :prev_txid, :prev_vout, :spend_height, :spend_blockhash)
            """,
            payload,
        )

    def mark_output_spent(self, prev_txid: str, prev_vout: int, spend_txid: str, spend_height: int, spend_blockhash: str) -> int:
        cur = self.conn.execute(
            """
            UPDATE outputs
            SET is_spent = 1,
                spend_txid = ?,
                spend_height = ?,
                spend_blockhash = ?
            WHERE txid = ? AND vout = ?
            """,
            (spend_txid, spend_height, spend_blockhash, prev_txid, prev_vout),
        )
        return cur.rowcount

    def output_exists(self, txid: str, vout: int) -> bool:
        row = self.conn.execute("SELECT 1 FROM outputs WHERE txid = ? AND vout = ?", (txid, vout)).fetchone()
        return row is not None

    def get_output(self, txid: str, vout: int) -> sqlite3.Row | None:
        return self.conn.execute("SELECT * FROM outputs WHERE txid = ? AND vout = ?", (txid, vout)).fetchone()

    def get_outputs_created_at(self, height: int) -> list[sqlite3.Row]:
        return list(self.conn.execute("SELECT * FROM outputs WHERE creation_height = ? ORDER BY txid, vout", (height,)))

    def get_spent_outputs(self) -> list[sqlite3.Row]:
        return list(self.conn.execute("SELECT * FROM outputs WHERE is_spent = 1 ORDER BY spend_height, txid, vout"))

    def get_unspent_outputs(self) -> list[sqlite3.Row]:
        return list(self.conn.execute("SELECT * FROM outputs WHERE is_spent = 0 ORDER BY creation_height, txid, vout"))

    def max_processed_height(self) -> int | None:
        row = self.conn.execute("SELECT MAX(height) AS max_height FROM blocks").fetchone()
        return None if row is None or row["max_height"] is None else int(row["max_height"])

    def insert_processing_metrics(self, payload: dict[str, object]) -> None:
        self.conn.execute(
            """
            INSERT OR REPLACE INTO processing_metrics (
              run_id, total_seconds, blocks_processed, transactions_processed, outputs_processed, inputs_processed,
              outputs_per_second, transactions_per_second, average_block_seconds, p50_block_seconds, p95_block_seconds, p99_block_seconds,
              sqlite_size_bytes, peak_rss_kib, processor_cpu_percent, rpc_reads, retry_count, error_count
            )
            VALUES (
              :run_id, :total_seconds, :blocks_processed, :transactions_processed, :outputs_processed, :inputs_processed,
              :outputs_per_second, :transactions_per_second, :average_block_seconds, :p50_block_seconds, :p95_block_seconds, :p99_block_seconds,
              :sqlite_size_bytes, :peak_rss_kib, :processor_cpu_percent, :rpc_reads, :retry_count, :error_count
            )
            """,
            payload,
        )

    def insert_lookup_metric(self, payload: dict[str, object]) -> None:
        self.conn.execute(
            """
            INSERT INTO lookup_metrics (phase, query_type, outpoint, found, latency_ms, error)
            VALUES (:phase, :query_type, :outpoint, :found, :latency_ms, :error)
            """,
            payload,
        )

    def replace_validation_result(self, run_id: str, status: str, summary: dict[str, object]) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO validation_results (run_id, status, summary_json) VALUES (?, ?, ?)",
            (run_id, status, json.dumps(summary, sort_keys=True)),
        )

    def count_rows(self, table: str) -> int:
        row = self.conn.execute(f"SELECT COUNT(*) AS count_value FROM {table}").fetchone()
        return int(row["count_value"])
