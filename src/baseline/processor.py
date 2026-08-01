from __future__ import annotations

import os
import statistics
import subprocess
import time
from datetime import datetime, timezone

from workload.rpc import RegtestRPC

from .config import PROJECT_ROOT, REGTEST_CLI, START_SCRIPT, STOP_SCRIPT, BaselineRunConfig
from .database import BaselineDatabase
from .metrics import compute_percentiles


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class BaselineProcessor:
    def __init__(self, config: BaselineRunConfig, database: BaselineDatabase):
        self.config = config
        self.database = database
        self.rpc = RegtestRPC(REGTEST_CLI, PROJECT_ROOT)
        self.run_id = f"baseline_{config.start_height}_{config.end_height}_{int(time.time())}"
        self.rpc_reads = 0
        self.retry_count = 0
        self.error_count = 0
        self.block_durations: list[float] = []
        self.unresolved_spends: list[dict[str, object]] = []
        self.total_transactions = 0
        self.total_outputs = 0
        self.total_inputs = 0
        self.peak_rss_kib = 0

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
        started_at = _utc_now()
        existing_max = self.database.max_processed_height()
        start_height = self.config.start_height if existing_max is None else max(self.config.start_height, existing_max + 1)
        self.database.upsert_run(
            {
                "run_id": self.run_id,
                "start_height": self.config.start_height,
                "end_height": self.config.end_height,
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
                    {
                        "height": height,
                        "blockhash": blockhash,
                        "time": block.get("time"),
                        "tx_count": len(block["tx"]),
                        "processed_at": _utc_now(),
                    }
                )
                for tx_index, tx in enumerate(block["tx"]):
                    self._ingest_transaction(height, blockhash, tx_index, tx)
                self._resolve_unresolved_spends()
                self.database.commit()
            except Exception:
                self.error_count += 1
                self.database.rollback()
                raise
            self.block_durations.append(time.perf_counter() - block_started)
            self.peak_rss_kib = max(self.peak_rss_kib, self._rss_kib())

        self._resolve_unresolved_spends(final_pass=True)
        if self.unresolved_spends:
            raise RuntimeError(f"unresolved spends remain: {len(self.unresolved_spends)}")

        total_seconds = time.perf_counter() - started
        sqlite_size_bytes = self.database.path.stat().st_size if self.database.path.exists() else 0
        percentiles = compute_percentiles(self.block_durations)
        average_block_seconds = statistics.fmean(self.block_durations) if self.block_durations else 0.0
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
            "sqlite_size_bytes": sqlite_size_bytes,
            "peak_rss_kib": self.peak_rss_kib,
            "processor_cpu_percent": self._cpu_percent(),
            "rpc_reads": self.rpc_reads,
            "retry_count": self.retry_count,
            "error_count": self.error_count,
        }
        self.database.insert_processing_metrics(metrics)
        self.database.upsert_run(
            {
                "run_id": self.run_id,
                "start_height": self.config.start_height,
                "end_height": self.config.end_height,
                "status": "COMPLETED",
                "started_at": started_at,
                "finished_at": _utc_now(),
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
            address = None
            if "address" in script:
                address = script["address"]
            elif "addresses" in script and script["addresses"]:
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
                }
            )
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
                updated = self.database.mark_output_spent(
                    spend_payload["prev_txid"],
                    spend_payload["prev_vout"],
                    txid,
                    height,
                    blockhash,
                )
                if updated == 0:
                    self.unresolved_spends.append(spend_payload)
                self.total_inputs += 1

    def _resolve_unresolved_spends(self, final_pass: bool = False) -> None:
        if not self.unresolved_spends:
            return
        remaining: list[dict[str, object]] = []
        for item in self.unresolved_spends:
            updated = self.database.mark_output_spent(
                str(item["prev_txid"]),
                int(item["prev_vout"]),
                str(item["spend_txid"]),
                int(item["spend_height"]),
                str(item["spend_blockhash"]),
            )
            if updated == 0:
                remaining.append(item)
        self.unresolved_spends = remaining
        if final_pass and remaining:
            duplicates = [f"{item['prev_txid']}:{item['prev_vout']}" for item in remaining]
            raise RuntimeError(f"could not resolve spent outputs: {duplicates}")

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
            completed = subprocess.run(
                ["ps", "-p", str(os.getpid()), "-o", "%cpu="],
                capture_output=True,
                text=True,
                check=False,
            )
            return float(completed.stdout.strip()) if completed.returncode == 0 and completed.stdout.strip() else 0.0
        except Exception:
            return 0.0
