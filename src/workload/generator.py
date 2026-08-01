from __future__ import annotations

import json
import os
import random
import sqlite3
import subprocess
import time
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from .config import (
    MIN_AVAILABLE_MEMORY_BYTES,
    REGTEST_CLI,
    REGTEST_DATADIR,
    RESET_SCRIPT,
    START_SCRIPT,
    STOP_SCRIPT,
    WALLET_NAME,
    WorkloadProfile,
)
from .manifest import sha256_of_file, summarize_records, write_manifest_csv, write_manifest_jsonl
from .models import OutputRecord, RunArtifacts, RunMetadata
from .rpc import RegtestRPC

DECIMAL_8 = Decimal("0.00000001")


class WorkloadGenerator:
    def __init__(
        self,
        project_root: Path,
        profile: WorkloadProfile,
        seed: int,
        output_dir: Path,
        config_hash: str,
        dry_run: bool = False,
        leave_running: bool = False,
        verbose: bool = False,
        reset: bool = False,
    ) -> None:
        self.project_root = project_root
        self.profile = profile
        self.seed = seed
        self.output_dir = output_dir
        self.config_hash = config_hash
        self.dry_run = dry_run
        self.leave_running = leave_running
        self.verbose = verbose
        self.reset = reset
        self.rpc = RegtestRPC(REGTEST_CLI, project_root)
        self.rng = random.Random(seed)
        self.run_id = f"{profile.name}_seed_{seed}_thr_{profile.threshold_blocks}_{int(time.time())}"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.artifacts = RunArtifacts(
            output_dir=output_dir,
            manifest_jsonl=output_dir / "manifest.jsonl",
            manifest_csv=output_dir / "manifest.csv",
            summary_json=output_dir / "summary.json",
            sqlite_db=output_dir / "workload.sqlite",
            validation_json=output_dir / "validation_results.json",
            log_path=output_dir / "generator_trace.log",
        )
        self.log_lines: list[str] = []
        self.records: list[OutputRecord] = []
        self.metadata = RunMetadata(
            run_id=self.run_id,
            profile=self.profile.name,
            seed=self.seed,
            threshold_blocks=self.profile.threshold_blocks,
            config_hash=self.config_hash,
            bitcoin_core_version="unknown",
            git_commit=self._git_commit(),
            dry_run=self.dry_run,
            started_at=self._now(),
        )
        self._lock_path = self.project_root / "data" / "workloads" / ".generation.lock"
        self._lock_held = False

    def run(self) -> dict[str, object]:
        started = time.time()
        self._acquire_lock()
        try:
            self._log(f"run_id={self.run_id}")
            self._log(f"profile={self.profile.name} seed={self.seed} dry_run={self.dry_run}")
            self._write_log()
            self._prepare_output_directories()
            if self.profile.requires_flag and os.environ.get("MECH_SCAL_ALLOW_LARGE") != "YES":
                raise RuntimeError("large profile requires MECH_SCAL_ALLOW_LARGE=YES")
            if self.reset and not self.dry_run:
                self._safe_reset()
            if self.dry_run:
                summary = self._run_dry()
            else:
                summary = self._run_live()
            self.metadata.finished_at = self._now()
            summary["run_duration_seconds"] = round(time.time() - started, 3)
            summary["metadata"] = self.metadata.to_dict()
            self.artifacts.summary_json.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
            self._write_log()
            return summary
        finally:
            self._release_lock()
            if not self.leave_running and not self.dry_run:
                self._safe_stop()

    def _run_dry(self) -> dict[str, object]:
        start_height = 101
        same_block_height = start_height + 1
        common_creation_height = same_block_height + 1
        final_height = common_creation_height + 36
        for group in self.profile.groups:
            for index in range(group.count):
                logical_id = self._logical_id(group.name, index + 1)
                creation_height = same_block_height if group.name == "same-block" else common_creation_height
                spend_height = None if group.spend_age_blocks is None else creation_height + group.spend_age_blocks
                record = OutputRecord(
                    run_id=self.run_id,
                    profile=self.profile.name,
                    seed=self.seed,
                    logical_output_id=logical_id,
                    group=group.name,
                    creation_txid=f"dry-{group.name}-{index+1:06d}",
                    vout=0,
                    creation_height=creation_height,
                    creation_blockhash=f"dry-block-{creation_height}",
                    value_btc=self._format_decimal(group.value_btc),
                    address=f"dry-address-{group.name}-{index+1:06d}",
                    expected_spend_age_blocks=group.spend_age_blocks,
                    spend_txid=None if spend_height is None else f"dry-spend-{group.name}-{index+1:06d}",
                    spend_height=spend_height,
                    spend_blockhash=None if spend_height is None else f"dry-block-{spend_height}",
                    actual_spend_age_blocks=group.spend_age_blocks,
                    is_spent=group.expected_state_at_end == "spent",
                    expected_state_at_end=group.expected_state_at_end,
                    final_chain_height=final_height,
                    validation_status="DRY_RUN",
                )
                self.records.append(record)
        return self._finalize_run(status="PASS", final_chain_height=final_height, warnings=["dry-run only"])

    def _run_live(self) -> dict[str, object]:
        self._call_script(START_SCRIPT)
        chain_info = self.rpc.ensure_chain()
        self.metadata.bitcoin_core_version = str(self.rpc.cli("getnetworkinfo")).splitlines()[0] if False else self._bitcoin_version()
        self._check_available_memory()
        self._ensure_wallet_loaded()
        mining_address = self.rpc.cli("-rpcwallet=" + WALLET_NAME, "getnewaddress", "", "bech32")
        if int(chain_info["blocks"]) < 101:
            self.rpc.cli("generatetoaddress", str(101 - int(chain_info["blocks"])), mining_address)
        if Decimal(self.rpc.cli("-rpcwallet=" + WALLET_NAME, "getbalance")) < Decimal("1.0"):
            self.rpc.cli("generatetoaddress", "101", mining_address)
        same_block_records = self._generate_same_block_group(mining_address)
        self.records.extend(same_block_records)
        common_records = self._generate_common_creation_groups(mining_address)
        self.records.extend(common_records)
        current_height = int(self.rpc.ensure_chain()["blocks"])
        common_creation_height = next(record.creation_height for record in common_records if record.creation_height is not None)
        spending_groups = [
            group for group in self.profile.groups if group.spend_age_blocks is not None and group.name != "same-block"
        ]
        for group in sorted(spending_groups, key=lambda item: int(item.spend_age_blocks or 0)):
            target_height = common_creation_height + int(group.spend_age_blocks or 0)
            while current_height < target_height - 1:
                self.rpc.cli("generatetoaddress", "1", mining_address)
                current_height += 1
                self._check_available_memory()
            group_records = [record for record in common_records if record.group == group.name]
            spend_txid = self._spend_records(group_records, mining_address)
            self.rpc.cli("generatetoaddress", "1", mining_address)
            current_height += 1
            spend_tx = self.rpc.tx(spend_txid)
            spend_header = self.rpc.block_header(str(spend_tx["blockhash"]))
            for record in group_records:
                record.spend_txid = spend_txid
                record.spend_blockhash = str(spend_tx["blockhash"])
                record.spend_height = int(spend_header["height"])
                record.is_spent = True
                record.validation_status = "CREATED"
        for record in self.records:
            record.final_chain_height = current_height
            if record.validation_status == "PENDING":
                record.validation_status = "CREATED"
            record.finalize_age()
        return self._finalize_run(status="PASS", final_chain_height=current_height, warnings=[])

    def _generate_same_block_group(self, mining_address: str) -> list[OutputRecord]:
        group = next(group for group in self.profile.groups if group.name == "same-block")
        payment_map: dict[str, str] = {}
        records: list[OutputRecord] = []
        for index in range(group.count):
            receive_address = self.rpc.cli("-rpcwallet=" + WALLET_NAME, "getnewaddress", f"same-block-{index+1}", "bech32")
            logical_id = self._logical_id(group.name, index + 1)
            payment_map[receive_address] = self._format_decimal(group.value_btc)
            records.append(
                OutputRecord(
                    run_id=self.run_id,
                    profile=self.profile.name,
                    seed=self.seed,
                    logical_output_id=logical_id,
                    group=group.name,
                    value_btc=self._format_decimal(group.value_btc),
                    address=receive_address,
                    expected_spend_age_blocks=0,
                    expected_state_at_end="spent",
                )
            )
        parent_txid = self.rpc.cli("-rpcwallet=" + WALLET_NAME, "sendmany", "", json.dumps(payment_map, sort_keys=True))
        parent_tx = self.rpc.tx(parent_txid)
        parent_outputs: list[dict[str, object]] = []
        for record in records:
            vout = self._find_vout(parent_tx, str(record.address))
            record.creation_txid = parent_txid
            record.vout = vout
            parent_outputs.append({"txid": parent_txid, "vout": vout, "amount": group.value_btc})
        spend_txid = self._spend_raw_inputs(parent_outputs, "same-block-sink")
        self.rpc.cli("generatetoaddress", "1", mining_address)
        for record in records:
            create_tx = self.rpc.tx(parent_txid)
            spend_tx = self.rpc.tx(spend_txid)
            create_header = self.rpc.block_header(str(create_tx["blockhash"]))
            spend_header = self.rpc.block_header(str(spend_tx["blockhash"]))
            record.creation_blockhash = str(create_tx["blockhash"])
            record.creation_height = int(create_header["height"])
            record.spend_txid = spend_txid
            record.spend_blockhash = str(spend_tx["blockhash"])
            record.spend_height = int(spend_header["height"])
            record.is_spent = True
            record.validation_status = "CREATED"
            record.finalize_age()
        return records

    def _generate_common_creation_groups(self, mining_address: str) -> list[OutputRecord]:
        payable_groups = [group for group in self.profile.groups if group.name != "same-block"]
        payment_map: dict[str, str] = {}
        records: list[OutputRecord] = []
        for group in payable_groups:
            for index in range(group.count):
                address = self.rpc.cli("-rpcwallet=" + WALLET_NAME, "getnewaddress", f"{group.name}-{index+1}", "bech32")
                payment_map[address] = self._format_decimal(group.value_btc)
                records.append(
                    OutputRecord(
                        run_id=self.run_id,
                        profile=self.profile.name,
                        seed=self.seed,
                        logical_output_id=self._logical_id(group.name, index + 1),
                        group=group.name,
                        value_btc=self._format_decimal(group.value_btc),
                        address=address,
                        expected_spend_age_blocks=group.spend_age_blocks,
                        expected_state_at_end=group.expected_state_at_end,
                    )
                )
        creation_txid = self.rpc.cli("-rpcwallet=" + WALLET_NAME, "sendmany", "", json.dumps(payment_map, sort_keys=True))
        self.rpc.cli("generatetoaddress", "1", mining_address)
        creation_tx = self.rpc.tx(creation_txid)
        header = self.rpc.block_header(str(creation_tx["blockhash"]))
        for record in records:
            record.creation_txid = creation_txid
            record.vout = self._find_vout(creation_tx, str(record.address))
            record.creation_blockhash = str(creation_tx["blockhash"])
            record.creation_height = int(header["height"])
        return records

    def _spend_records(self, records: list[OutputRecord], label: str) -> str:
        inputs = [
            {
                "txid": str(record.creation_txid),
                "vout": int(record.vout),
                "amount": Decimal(str(record.value_btc)),
            }
            for record in records
        ]
        return self._spend_raw_inputs(inputs, label)

    def _spend_raw_inputs(self, inputs: list[dict[str, object]], label: str) -> str:
        total = sum(Decimal(str(item["amount"])) for item in inputs)
        fee = Decimal("0.00010000")
        if total <= fee:
            raise RuntimeError("spend total is too small for fee")
        destination = self.rpc.cli("-rpcwallet=" + WALLET_NAME, "getnewaddress", label, "bech32")
        raw_inputs = [{"txid": str(item["txid"]), "vout": int(item["vout"])} for item in inputs]
        raw_outputs = {destination: self._format_decimal((total - fee).quantize(DECIMAL_8))}
        raw = self.rpc.cli("createrawtransaction", json.dumps(raw_inputs), json.dumps(raw_outputs, sort_keys=True))
        signed = json.loads(self.rpc.cli("-rpcwallet=" + WALLET_NAME, "signrawtransactionwithwallet", raw))
        if not signed.get("complete"):
            raise RuntimeError("raw transaction signing did not complete")
        return self.rpc.cli("sendrawtransaction", str(signed["hex"]))

    def _finalize_run(self, status: str, final_chain_height: int, warnings: list[str]) -> dict[str, object]:
        for record in self.records:
            record.final_chain_height = final_chain_height
            record.finalize_age()
        write_manifest_jsonl(self.artifacts.manifest_jsonl, self.records)
        write_manifest_csv(self.artifacts.manifest_csv, self.records)
        self.metadata.final_chain_height = final_chain_height
        self.metadata.manifest_hash = sha256_of_file(self.artifacts.manifest_jsonl)
        self.metadata.status = status
        self.metadata.warnings = warnings
        self._write_sqlite(final_chain_height)
        summary = summarize_records(self.records)
        summary.update(
            {
                "run_id": self.run_id,
                "seed": self.seed,
                "profile": self.profile.name,
                "threshold_blocks": self.profile.threshold_blocks,
                "config_hash": self.config_hash,
                "manifest_hash": self.metadata.manifest_hash,
                "bitcoin_core_version": self.metadata.bitcoin_core_version,
                "git_commit": self.metadata.git_commit,
                "final_chain_height": final_chain_height,
                "warnings": warnings,
                "status": status,
                "generator_resources": self._process_snapshot(os.getpid()),
                "regtest_resources": self._regtest_snapshot(),
                "disk_usage_human": self._disk_usage(),
            }
        )
        return summary

    def _write_sqlite(self, final_chain_height: int) -> None:
        conn = sqlite3.connect(self.artifacts.sqlite_db)
        try:
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute(
                "CREATE TABLE IF NOT EXISTS runs (run_id TEXT PRIMARY KEY, profile TEXT, seed INTEGER, threshold_blocks INTEGER, config_hash TEXT, manifest_hash TEXT, final_chain_height INTEGER, status TEXT)"
            )
            conn.execute(
                "CREATE TABLE IF NOT EXISTS outputs (logical_output_id TEXT PRIMARY KEY, run_id TEXT, output_group TEXT, creation_txid TEXT, vout INTEGER, creation_height INTEGER, value_btc TEXT, address TEXT, expected_spend_age_blocks INTEGER, expected_state_at_end TEXT, FOREIGN KEY(run_id) REFERENCES runs(run_id))"
            )
            conn.execute(
                "CREATE TABLE IF NOT EXISTS spends (logical_output_id TEXT PRIMARY KEY, spend_txid TEXT, spend_height INTEGER, actual_spend_age_blocks INTEGER, is_spent INTEGER, FOREIGN KEY(logical_output_id) REFERENCES outputs(logical_output_id))"
            )
            conn.execute(
                "CREATE TABLE IF NOT EXISTS blocks (blockhash TEXT PRIMARY KEY, height INTEGER, run_id TEXT, role TEXT, FOREIGN KEY(run_id) REFERENCES runs(run_id))"
            )
            conn.execute(
                "CREATE TABLE IF NOT EXISTS validation_results (run_id TEXT PRIMARY KEY, validation_status TEXT, final_chain_height INTEGER, FOREIGN KEY(run_id) REFERENCES runs(run_id))"
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_outputs_txid_vout ON outputs (creation_txid, vout)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_outputs_group ON outputs (output_group)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_outputs_run_id ON outputs (run_id)")
            conn.execute(
                "INSERT OR REPLACE INTO runs VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    self.run_id,
                    self.profile.name,
                    self.seed,
                    self.profile.threshold_blocks,
                    self.config_hash,
                    self.metadata.manifest_hash,
                    final_chain_height,
                    self.metadata.status,
                ),
            )
            for record in self.records:
                conn.execute(
                    "INSERT OR REPLACE INTO outputs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        record.logical_output_id,
                        self.run_id,
                        record.group,
                        record.creation_txid,
                        record.vout,
                        record.creation_height,
                        record.value_btc,
                        record.address,
                        record.expected_spend_age_blocks,
                        record.expected_state_at_end,
                    ),
                )
                conn.execute(
                    "INSERT OR REPLACE INTO spends VALUES (?, ?, ?, ?, ?)",
                    (
                        record.logical_output_id,
                        record.spend_txid,
                        record.spend_height,
                        record.actual_spend_age_blocks,
                        1 if record.is_spent else 0,
                    ),
                )
                if record.creation_blockhash:
                    conn.execute(
                        "INSERT OR IGNORE INTO blocks VALUES (?, ?, ?, ?)",
                        (record.creation_blockhash, record.creation_height, self.run_id, "creation"),
                    )
                if record.spend_blockhash:
                    conn.execute(
                        "INSERT OR IGNORE INTO blocks VALUES (?, ?, ?, ?)",
                        (record.spend_blockhash, record.spend_height, self.run_id, "spend"),
                    )
            conn.execute(
                "INSERT OR REPLACE INTO validation_results VALUES (?, ?, ?)",
                (self.run_id, self.metadata.status, final_chain_height),
            )
            conn.commit()
        finally:
            conn.close()

    def _ensure_wallet_loaded(self) -> None:
        loaded = set(json.loads(self.rpc.cli("listwallets")))
        if WALLET_NAME not in loaded:
            wallet_dirs = json.loads(self.rpc.cli("listwalletdir"))["wallets"]
            available = {item["name"] for item in wallet_dirs}
            if WALLET_NAME in available:
                self.rpc.cli("loadwallet", WALLET_NAME)
            else:
                self.rpc.cli(
                    "-named",
                    "createwallet",
                    f"wallet_name={WALLET_NAME}",
                    "descriptors=true",
                    "load_on_startup=false",
                )

    def _safe_reset(self) -> None:
        env = os.environ.copy()
        env["MECH_SCAL_ALLOW_RESET"] = "YES"
        subprocess.run([str(RESET_SCRIPT)], cwd=self.project_root, env=env, text=True, check=True)

    def _safe_stop(self) -> None:
        subprocess.run([str(STOP_SCRIPT)], cwd=self.project_root, text=True, check=False)

    def _call_script(self, path: Path) -> None:
        subprocess.run([str(path)], cwd=self.project_root, text=True, check=True)

    def _prepare_output_directories(self) -> None:
        (self.project_root / "data" / "workloads").mkdir(parents=True, exist_ok=True)
        (self.project_root / "results" / "workloads").mkdir(parents=True, exist_ok=True)
        (self.project_root / "logs").mkdir(parents=True, exist_ok=True)

    def _find_vout(self, tx: dict[str, object], address: str) -> int:
        for entry in tx["vout"]:
            script = entry.get("scriptPubKey", {})
            if script.get("address") == address:
                return int(entry["n"])
        raise RuntimeError(f"address {address} not found in transaction {tx['txid']}")

    def _logical_id(self, group_name: str, ordinal: int) -> str:
        return f"profile-{self.profile.name}/group-{group_name}/output-{ordinal:06d}"

    def _disk_usage(self) -> str:
        completed = subprocess.run(["du", "-sh", str(REGTEST_DATADIR)], text=True, capture_output=True, check=False)
        return completed.stdout.strip().split()[0] if completed.returncode == 0 and completed.stdout.strip() else "unknown"

    def _process_snapshot(self, pid: int) -> dict[str, object]:
        try:
            completed = subprocess.run(
                ["ps", "-p", str(pid), "-o", "pid=,rss=,vsz=,%mem=,%cpu=,comm="],
                text=True,
                capture_output=True,
                check=False,
            )
        except (FileNotFoundError, PermissionError):
            return {"pid": pid, "status": "unavailable"}
        if completed.returncode != 0 or not completed.stdout.strip():
            return {"pid": pid, "status": "unavailable"}
        raw = completed.stdout.strip().split(None, 5)
        return {"pid": int(raw[0]), "rss_kib": raw[1], "vsz_kib": raw[2], "mem_percent": raw[3], "cpu_percent": raw[4], "command": raw[5]}

    def _regtest_snapshot(self) -> dict[str, object]:
        try:
            completed = subprocess.run(
                ["pgrep", "-af", "bitcoind"],
                text=True,
                capture_output=True,
                check=False,
            )
        except (FileNotFoundError, PermissionError):
            return {"status": "unavailable"}
        for line in completed.stdout.splitlines():
            if "-regtest" in line and f"-datadir={REGTEST_DATADIR}" in line:
                pid = int(line.split(None, 1)[0])
                return self._process_snapshot(pid)
        return {"status": "not-running"}

    def _check_available_memory(self) -> None:
        meminfo = {}
        with open("/proc/meminfo", encoding="utf-8") as handle:
            for line in handle:
                key, value = line.split(":", 1)
                meminfo[key] = value.strip()
        available_kib = int(meminfo["MemAvailable"].split()[0])
        if available_kib * 1024 < MIN_AVAILABLE_MEMORY_BYTES:
            raise RuntimeError("available memory dropped below 1.5 GiB")

    def _bitcoin_version(self) -> str:
        info = json.loads(self.rpc.cli("getnetworkinfo"))
        return str(info["subversion"])

    def _git_commit(self) -> str | None:
        completed = subprocess.run(["git", "rev-parse", "HEAD"], cwd=self.project_root, text=True, capture_output=True, check=False)
        if completed.returncode == 0:
            return completed.stdout.strip()
        return None

    def _write_log(self) -> None:
        self.artifacts.log_path.write_text("\n".join(self.log_lines) + ("\n" if self.log_lines else ""), encoding="utf-8")

    def _log(self, message: str) -> None:
        timestamp = self._now()
        self.log_lines.append(f"{timestamp} {message}")
        if self.verbose:
            print(message)

    def _format_decimal(self, value: Decimal) -> str:
        return str(value.quantize(DECIMAL_8))

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _acquire_lock(self) -> None:
        self._lock_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            fd = os.open(self._lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError as exc:
            raise RuntimeError("another workload generation process appears to be running") from exc
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(json.dumps({"pid": os.getpid(), "run_id": self.run_id}) + "\n")
        self._lock_held = True

    def _release_lock(self) -> None:
        if self._lock_held and self._lock_path.exists():
            self._lock_path.unlink()
        self._lock_held = False
