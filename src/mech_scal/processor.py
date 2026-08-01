from __future__ import annotations

import os
import statistics
import subprocess
import time
from datetime import datetime, timezone

from baseline.metrics import compute_percentiles
from workload.rpc import RegtestRPC

from .classifier import OutputClassifier
from .config import (
    PROJECT_ROOT,
    REGTEST_CLI,
    SNAPSHOT_HEIGHTS,
    START_SCRIPT,
    STOP_SCRIPT,
    MechScalRunConfig,
)
from .database import MechScalDatabase
from .transitions import persist_transition, utc_now


class MechScalProcessor:
    def __init__(self, config: MechScalRunConfig, database: MechScalDatabase):
        self.config = config
        self.database = database
        self.rpc = RegtestRPC(REGTEST_CLI, PROJECT_ROOT)
        self.classifier = OutputClassifier(config.t_min)
        self.run_id = f"mech_scal_{config.start_height}_{config.end_height}_{int(time.time())}"
        self.rpc_reads = 0
        self.retry_count = 0
        self.error_count = 0
        self.total_transactions = 0
        self.total_outputs = 0
        self.total_inputs = 0
        self.block_durations: list[float] = []
        self.unresolved_spends: list[dict[str, object]] = []
        self.peak_rss_kib = 0
        self.classification_seconds = 0.0
        self.transition_persistence_seconds = 0.0
        self.retrieval_seconds = 0.0
        self.mh_to_ml_count = 0
        self.mh_to_im_count = 0
        self.ml_to_im_count = 0
        self.same_block_spend_count = 0

    def process(self) -> dict[str, object]:
        self.database.init_schema()
        if self.config.reset_db:
            self.database.reset()
            self.database.init_schema()
        self._start_regtest_if_needed()
        chain_info = self._rpc_json("getblockchaininfo")
        if chain_info["chain"] != "regtest":
            raise RuntimeError(f"unexpected chain: {chain_info['chain']}")

        started = time.perf_counter()
        started_at = datetime.now(timezone.utc).isoformat()
        existing_max = self.database.max_processed_height()
        start_height = self.config.start_height if existing_max is None else max(self.config.start_height, existing_max + 1)
        self.database.upsert_run(
            {
                "run_id": self.run_id,
                "start_height": self.config.start_height,
                "end_height": self.config.end_height,
                "t_min": self.config.t_min,
                "status": "RUNNING",
                "started_at": started_at,
                "finished_at": None,
                "total_blocks": 0,
                "total_transactions": 0,
                "total_outputs": 0,
                "total_inputs": 0,
            }
        )
        self.database.commit()

        for height in range(start_height, self.config.end_height + 1):
            block_started = time.perf_counter()
            blockhash = self._rpc("getblockhash", str(height))
            block = self._rpc_json("getblock", blockhash, "2")
            self.database.begin()
            try:
                self.database.insert_block(
                    {"height": height, "blockhash": blockhash, "time": block.get("time"), "tx_count": len(block["tx"]), "processed_at": utc_now()}
                )
                for tx_index, tx in enumerate(block["tx"]):
                    self._ingest_transaction(height, blockhash, tx_index, tx)
                self._resolve_unresolved_spends()
                self._apply_temporal_transitions(height)
                if height in SNAPSHOT_HEIGHTS:
                    self._write_snapshot(height)
                self.database.commit()
            except Exception:
                self.error_count += 1
                self.database.rollback()
                raise
            self.block_durations.append(time.perf_counter() - block_started)
            self.peak_rss_kib = max(self.peak_rss_kib, self._rss_kib())

        self._resolve_unresolved_spends(final_pass=True)
        for height in SNAPSHOT_HEIGHTS:
            if height > self.config.end_height:
                continue
            if self.database.conn.execute("SELECT 1 FROM class_snapshots WHERE snapshot_height = ?", (height,)).fetchone() is None:
                self._write_snapshot(height)
        self._finalize_output_classes()

        total_seconds = time.perf_counter() - started
        sqlite_size_bytes = self.database.path.stat().st_size if self.database.path.exists() else 0
        percentiles = compute_percentiles(self.block_durations)
        average_block_seconds = statistics.fmean(self.block_durations) if self.block_durations else 0.0
        final_counts = self._class_counts()
        metrics = {
            "run_id": self.run_id,
            "total_seconds": total_seconds,
            "blocks_processed": max(0, self.config.end_height - self.config.start_height + 1),
            "transactions_processed": self.total_transactions,
            "outputs_processed": self.total_outputs,
            "inputs_processed": self.total_inputs,
            "outputs_per_second": self.total_outputs / total_seconds if total_seconds else 0.0,
            "transactions_per_second": self.total_transactions / total_seconds if total_seconds else 0.0,
            "average_block_seconds": average_block_seconds,
            "p50_block_seconds": percentiles["p50"],
            "p95_block_seconds": percentiles["p95"],
            "p99_block_seconds": percentiles["p99"],
            "classification_seconds": self.classification_seconds,
            "classification_seconds_per_output": self.classification_seconds / self.total_outputs if self.total_outputs else 0.0,
            "mh_to_ml_count": self.mh_to_ml_count,
            "mh_to_im_count": self.mh_to_im_count,
            "ml_to_im_count": self.ml_to_im_count,
            "same_block_spend_count": self.same_block_spend_count,
            "final_mh_count": final_counts["MH"],
            "final_ml_count": final_counts["ML"],
            "final_im_count": final_counts["IM"],
            "sqlite_size_bytes": sqlite_size_bytes,
            "peak_rss_kib": self.peak_rss_kib,
            "processor_cpu_percent": self._cpu_percent(),
            "rpc_reads": self.rpc_reads,
            "retry_count": self.retry_count,
            "error_count": self.error_count,
            "retrieval_seconds": self.retrieval_seconds,
            "transition_persistence_seconds": self.transition_persistence_seconds,
        }
        self.database.insert_processing_metrics(metrics)
        self.database.upsert_run(
            {
                "run_id": self.run_id,
                "start_height": self.config.start_height,
                "end_height": self.config.end_height,
                "t_min": self.config.t_min,
                "status": "COMPLETED",
                "started_at": started_at,
                "finished_at": utc_now(),
                "total_blocks": metrics["blocks_processed"],
                "total_transactions": self.total_transactions,
                "total_outputs": self.total_outputs,
                "total_inputs": self.total_inputs,
            }
        )
        self.database.commit()
        if not self.config.leave_running:
            subprocess.run([str(STOP_SCRIPT)], cwd=PROJECT_ROOT, check=False, text=True)
        return {"run_id": self.run_id, "metrics": metrics}

    def _ingest_transaction(self, height: int, blockhash: str, tx_index: int, tx: dict[str, object]) -> None:
        txid = str(tx["txid"])
        is_coinbase = 1 if self._is_coinbase(tx) else 0
        vin = tx.get("vin", [])
        vout = tx.get("vout", [])
        self.database.insert_transaction(
            {
                "txid": txid,
                "blockhash": blockhash,
                "height": height,
                "tx_index": tx_index,
                "is_coinbase": is_coinbase,
                "input_count": 0 if is_coinbase else len(vin),
                "output_count": len(vout),
            }
        )
        self.total_transactions += 1
        for output in vout:
            script = output.get("scriptPubKey", {})
            address = script.get("address")
            if address is None and script.get("addresses"):
                address = script["addresses"][0]
            self.database.insert_output(
                {
                    "txid": txid,
                    "vout": int(output["n"]),
                    "creation_height": height,
                    "creation_blockhash": blockhash,
                    "value_sat": int(round(float(output["value"]) * 100_000_000)),
                    "script_type": script.get("type"),
                    "address": address,
                    "is_coinbase": is_coinbase,
                    "is_spent": 0,
                    "spend_txid": None,
                    "spend_height": None,
                    "spend_blockhash": None,
                    "spend_age_blocks": None,
                    "current_class": "MH",
                    "class_updated_height": height,
                    "final_class": None,
                }
            )
            classify_started = time.perf_counter()
            decision = self.classifier.classify_new_output()
            self.classification_seconds += time.perf_counter() - classify_started
            transition_started = time.perf_counter()
            persist_transition(self.database, txid, int(output["n"]), decision.from_class, decision.to_class, height, decision.reason, decision.age_blocks)
            self.transition_persistence_seconds += time.perf_counter() - transition_started
            self.total_outputs += 1
        if not is_coinbase:
            for vin_index, item in enumerate(vin):
                spend_payload = {
                    "spend_txid": txid,
                    "vin_index": vin_index,
                    "prev_txid": str(item["txid"]),
                    "prev_vout": int(item["vout"]),
                    "spend_height": height,
                    "spend_blockhash": blockhash,
                }
                self.database.insert_spend(spend_payload)
                prev_row = self.database.get_output(spend_payload["prev_txid"], spend_payload["prev_vout"])
                if prev_row is None:
                    self.unresolved_spends.append(spend_payload)
                else:
                    self._apply_spend_transition(prev_row, spend_payload)
                self.total_inputs += 1

    def _apply_spend_transition(self, prev_row, spend_payload: dict[str, object]) -> None:
        age = int(spend_payload["spend_height"]) - int(prev_row["creation_height"])
        classify_started = time.perf_counter()
        decision = self.classifier.classify_spend(str(prev_row["current_class"]), int(prev_row["creation_height"]), int(spend_payload["spend_height"]))
        self.classification_seconds += time.perf_counter() - classify_started
        updated = self.database.mark_output_spent(
            str(spend_payload["prev_txid"]),
            int(spend_payload["prev_vout"]),
            str(spend_payload["spend_txid"]),
            int(spend_payload["spend_height"]),
            str(spend_payload["spend_blockhash"]),
            age,
        )
        if updated == 0:
            self.unresolved_spends.append(spend_payload)
            return
        self.database.update_output_class(str(prev_row["txid"]), int(prev_row["vout"]), "IM", int(spend_payload["spend_height"]), "IM")
        transition_started = time.perf_counter()
        persist_transition(
            self.database,
            str(prev_row["txid"]),
            int(prev_row["vout"]),
            decision.from_class,
            "IM",
            int(spend_payload["spend_height"]),
            decision.reason,
            decision.age_blocks,
        )
        self.transition_persistence_seconds += time.perf_counter() - transition_started
        if decision.reason == "same_block_spend":
            self.same_block_spend_count += 1
            self.mh_to_im_count += 1
        elif decision.reason == "spent_from_mh":
            self.mh_to_im_count += 1
        elif decision.reason == "spent_from_ml":
            self.ml_to_im_count += 1

    def _resolve_unresolved_spends(self, final_pass: bool = False) -> None:
        if not self.unresolved_spends:
            return
        remaining = []
        for spend_payload in self.unresolved_spends:
            prev_row = self.database.get_output(str(spend_payload["prev_txid"]), int(spend_payload["prev_vout"]))
            if prev_row is None:
                remaining.append(spend_payload)
            else:
                self._apply_spend_transition(prev_row, spend_payload)
        self.unresolved_spends = remaining
        if final_pass and remaining:
            raise RuntimeError(f"unresolved spends remain: {len(remaining)}")

    def _apply_temporal_transitions(self, height: int) -> None:
        rows = list(self.database.conn.execute("SELECT txid, vout, creation_height, current_class, is_spent FROM outputs WHERE is_spent = 0 AND current_class = 'MH'"))
        for row in rows:
            classify_started = time.perf_counter()
            decision = self.classifier.classify_temporal_transition(str(row["current_class"]), int(row["creation_height"]), height, bool(row["is_spent"]))
            self.classification_seconds += time.perf_counter() - classify_started
            if decision is None:
                continue
            self.database.update_output_class(str(row["txid"]), int(row["vout"]), "ML", height, None)
            transition_started = time.perf_counter()
            persist_transition(self.database, str(row["txid"]), int(row["vout"]), decision.from_class, decision.to_class, height, decision.reason, decision.age_blocks)
            self.transition_persistence_seconds += time.perf_counter() - transition_started
            self.mh_to_ml_count += 1

    def _write_snapshot(self, height: int) -> None:
        counts = self._class_counts(max_height=height)
        self.database.replace_snapshot(
            {
                "snapshot_height": height,
                "mh_count": counts["MH"],
                "ml_count": counts["ML"],
                "im_count": counts["IM"],
                "total_classified_outputs": counts["TOTAL"],
                "spent_count": counts["SPENT"],
                "unspent_count": counts["UNSPENT"],
                "created_at": utc_now(),
            }
        )

    def _class_counts(self, max_height: int | None = None) -> dict[str, int]:
        where = "WHERE creation_height <= ?" if max_height is not None else ""
        params = (max_height,) if max_height is not None else ()
        rows = list(self.database.conn.execute(f"SELECT current_class, is_spent FROM outputs {where}", params))
        mh = sum(1 for row in rows if row["current_class"] == "MH")
        ml = sum(1 for row in rows if row["current_class"] == "ML")
        im = sum(1 for row in rows if row["current_class"] == "IM")
        spent = sum(1 for row in rows if row["is_spent"])
        unspent = len(rows) - spent
        return {"MH": mh, "ML": ml, "IM": im, "TOTAL": len(rows), "SPENT": spent, "UNSPENT": unspent}

    def _finalize_output_classes(self) -> None:
        self.database.conn.execute("UPDATE outputs SET final_class = current_class WHERE final_class IS NULL")

    def _rpc(self, *args: str) -> str:
        self.rpc_reads += 1
        return self.rpc.cli(*args)

    def _rpc_json(self, *args: str) -> dict[str, object]:
        self.rpc_reads += 1
        return self.rpc.cli_json(*args)

    def _start_regtest_if_needed(self) -> None:
        try:
            info = self._rpc_json("getblockchaininfo")
            if info["chain"] == "regtest":
                return
        except Exception:
            subprocess.run([str(START_SCRIPT)], cwd=PROJECT_ROOT, check=True, text=True)

    @staticmethod
    def _is_coinbase(tx: dict[str, object]) -> bool:
        vin = tx.get("vin", [])
        return bool(vin and "coinbase" in vin[0])

    @staticmethod
    def _rss_kib() -> int:
        try:
            with open("/proc/self/status", encoding="utf-8") as handle:
                for line in handle:
                    if line.startswith("VmRSS:"):
                        return int(line.split()[1])
        except FileNotFoundError:
            return 0
        return 0

    @staticmethod
    def _cpu_percent() -> float:
        try:
            completed = subprocess.run(["ps", "-p", str(os.getpid()), "-o", "%cpu="], capture_output=True, text=True, check=False)
            return float(completed.stdout.strip()) if completed.returncode == 0 and completed.stdout.strip() else 0.0
        except Exception:
            return 0.0
