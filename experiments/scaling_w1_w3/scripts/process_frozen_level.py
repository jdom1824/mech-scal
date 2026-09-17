#!/usr/bin/env python3
"""Process one already generated scaling workload without regeneration."""
from __future__ import annotations

import csv
import json
import os
import shutil
import signal
import subprocess
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(os.environ["SOURCE_ROOT"])
SOURCE_ATTEMPT = os.environ["SOURCE_ATTEMPT"]
PROCESS_ATTEMPT = os.environ["PROCESS_ATTEMPT"]
SOURCE_OUT = ROOT / "results" / SOURCE_ATTEMPT
SOURCE_DATA = ROOT / ("regtest_" + SOURCE_ATTEMPT)
OUT = ROOT / "results" / PROCESS_ATTEMPT
WORK = OUT / "workload"
CODE = ROOT / "processing_code_" / PROCESS_ATTEMPT
BASE_CODE = ROOT / "campaign_code"
BITCOIN = Path(os.environ.get("BITCOIN_ROOT", str(ROOT / "bitcoin" / "bin")))
REQUIRED_WORKLOAD = ["block_hashes.json", "block_heights.json", "blocks.jsonl", "lookup_targets.json", "manifest.csv", "manifest.jsonl"]


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha(path: Path) -> str:
    import hashlib
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def save(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    if not rows:
        path.write_text("\n", encoding="utf-8")
        return
    fields: list[str] = []
    for row in rows:
        for field in row:
            if field not in fields:
                fields.append(field)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def prepare() -> dict[str, object]:
    source_summary = json.loads((SOURCE_OUT / "summary.json").read_text(encoding="utf-8"))
    assert source_summary["status"] == "PASS"
    assert sha(SOURCE_OUT / "workload/manifest.jsonl") == source_summary["manifest_sha256"]
    assert not OUT.exists(), f"processing output already exists: {OUT}"
    OUT.mkdir(parents=True)
    (OUT / "logs").mkdir()
    (OUT / "provenance").mkdir()
    WORK.mkdir()
    hashes: dict[str, str] = {}
    for relative in REQUIRED_WORKLOAD:
        source = SOURCE_OUT / "workload" / relative
        target = WORK / relative
        shutil.copy2(source, target)
        hashes["workload/" + relative] = sha(source)
        assert sha(target) == hashes["workload/" + relative]
    for relative in ["generator_configuration.json", "manifest_pin.json", "summary.json", "attempt_status.json"]:
        source = SOURCE_OUT / relative
        target = OUT / relative
        shutil.copy2(source, target)
        hashes[relative] = sha(source)
    audit = sorted((SOURCE_OUT / "audit").glob("*.jsonl"))
    for source in audit:
        target = OUT / "audit" / source.name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        hashes["audit/" + source.name] = sha(source)
    save(OUT / "workload_hashes.json", {key.removeprefix("workload/"): value for key, value in hashes.items() if key.startswith("workload/")})
    save(OUT / "provenance/frozen_artifact_hashes.json", {
        "source_attempt": SOURCE_ATTEMPT, "source_output": str(SOURCE_OUT),
        "source_and_copy_sha256": hashes, "created_at": now(),
    })
    (CODE / "campaign_scaling").mkdir(parents=True, exist_ok=True)
    shutil.copy2(BASE_CODE / "campaign_scaling/common.py", CODE / "campaign_scaling/common.py")
    shutil.copy2(BASE_CODE / "campaign_scaling/config.json", CODE / "campaign_scaling/config.json")
    for name in ["__init__.py", "worker.py", "harness.py"]:
        shutil.copy2(BASE_CODE / "campaign_scaling" / name, CODE / "campaign_scaling" / name)
    shutil.copytree(BASE_CODE / "src", CODE / "src")
    cli = CODE / "campaign_scaling/w1_cli.sh"
    cli.write_text("#!/usr/bin/env bash\nset -euo pipefail\n" f'exec "{BITCOIN / "bitcoin-cli"}" -regtest -datadir="{SOURCE_DATA}" -rpcport=19443 "$@"\n', encoding="utf-8")
    cli.chmod(0o755)
    refuse = CODE / "campaign_scaling/refuse_start.sh"
    refuse.write_text("#!/usr/bin/env bash\necho 'processor-only execution: startup/reset refused' >&2\nexit 1\n", encoding="utf-8")
    refuse.chmod(0o755)
    link = ROOT / ("regtest_" + PROCESS_ATTEMPT)
    assert not link.exists() and not link.is_symlink()
    link.symlink_to(SOURCE_DATA, target_is_directory=True)
    return {"summary": source_summary, "hashes": hashes, "link": str(link)}


def flatten(run: dict[str, object]) -> dict[str, object]:
    metrics = run.get("metrics", {})
    storage = run.get("storage", {})
    return {"run": run.get("run"), "system": run.get("system"), "warmup": run.get("warmup"),
            "processing_seconds": run.get("processing_seconds"), "whole_processor_wall_seconds": run.get("whole_processor_wall_seconds"),
            "initialization_seconds": run.get("initialization_seconds"), "legacy_sampled_peak_rss_kib": run.get("legacy_sampled_peak_rss_kib"),
            "process_peak_rss_kib": run.get("process_peak_rss_kib"), "vmhwm_at_processor_return_kib": run.get("vmhwm_at_processor_return_kib"),
            "seconds_per_block": run.get("seconds_per_block"), "seconds_per_transaction": run.get("seconds_per_transaction"),
            "seconds_per_output": run.get("seconds_per_output"), "physical_db_bytes": storage.get("physical_bytes"),
            "blocks_processed": metrics.get("blocks_processed"), "transactions_processed": metrics.get("transactions_processed"),
            "outputs_processed": metrics.get("outputs_processed"), "spends_processed": metrics.get("spends_processed"),
            "rpc_reads": metrics.get("rpc_reads"), "rpc_errors": metrics.get("error_count"), "retry_count": metrics.get("retry_count"),
            "validation_status": run.get("validation", {}).get("status")}


def consolidate() -> None:
    runs = [json.loads(path.read_text()) for path in sorted((OUT / "runs").glob("*/run.json"))]
    write_csv(OUT / "raw_processing_observations.csv", [flatten(run) for run in runs])
    lookups: list[dict[str, object]] = []
    plans: list[dict[str, object]] = []
    for run in runs:
        directory = OUT / "runs" / str(run["run"])
        with (directory / "lookup_raw.csv").open(newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                row.update({"run": run["run"], "system": run["system"], "warmup": run["warmup"]})
                lookups.append(row)
        for index, plan in enumerate(run.get("explain_query_plan", [])):
            plans.append({"run": run["run"], "system": run["system"], "plan_index": index, "plan": " | ".join(map(str, plan))})
    write_csv(OUT / "raw_lookup_observations.csv", lookups)
    write_csv(OUT / "explain_query_plan.csv", plans)


def main() -> int:
    node = None
    status: dict[str, object] = {"attempt": PROCESS_ATTEMPT, "status": "FAIL", "runs": [], "pairs": [], "started_at": now()}
    try:
        precheck = prepare()
        os.environ.update({"CAMPAIGN_CODE": str(CODE), "CAMPAIGN_ROOT": str(ROOT), "CAMPAIGN_ATTEMPT_ID": PROCESS_ATTEMPT})
        sys.path.insert(0, str(CODE))
        from campaign_scaling import common
        from campaign_scaling.harness import Gates, child, check_pair, free_ports, paired_row
        assert free_ports()
        assert subprocess.run(["pgrep", "-x", "bitcoind"], capture_output=True).returncode == 1
        gates = Gates()
        gates.check()
        log = (OUT / "logs/bitcoind.log").open("w", encoding="utf-8")
        args = [str(BITCOIN / "bitcoind"), "-regtest", f"-datadir={SOURCE_DATA}", "-server=1", "-listen=1", "-bind=127.0.0.1", "-rpcbind=127.0.0.1", "-rpcport=19443", "-port=19444", "-connect=0", "-dnsseed=0", "-discover=0", "-fallbackfee=0.0001"]
        node = subprocess.Popen(args, stdout=log, stderr=subprocess.STDOUT)
        save(OUT / "owned_node.json", {"pid": node.pid, "args": args, "started_at": now()})
        for _ in range(60):
            try:
                info = common.rpc("getblockchaininfo")
                break
            except Exception:
                if node.poll() is not None:
                    raise RuntimeError("bitcoind exited during startup")
                time.sleep(1)
        else:
            raise RuntimeError("RPC startup timeout")
        assert info["chain"] == "regtest" and info["blocks"] == common.CONFIG["end_height"]
        common.verify_frozen(live=True)
        status["precheck"] = {"chain": info["chain"], "blocks": info["blocks"], "manifest_sha256": precheck["summary"]["manifest_sha256"], "status": "PASS"}
        for system in ["baseline", "mech_scal"]:
            name = "warmup_" + system
            status["runs"].append({"run": name, "state": "RUNNING"})
            save(OUT / "pilot_status.json", status)
            child(["campaign_scaling.worker", system, name, "diagnostic"], name, gates, time.monotonic() + 1800)
            status["runs"][-1]["state"] = "PASS"
            common.verify_frozen(live=True)
        check_pair(json.loads((OUT / "runs/warmup_baseline/run.json").read_text()), json.loads((OUT / "runs/warmup_mech_scal/run.json").read_text()))
        status["warmups"] = "PASS"
        for pair, order in enumerate(common.CONFIG["pair_order"], 1):
            pair_start = time.monotonic()
            deadline = pair_start + common.CONFIG["pair_timeout_seconds"]
            current: dict[str, object] = {"pair": pair, "order": " -> ".join(order), "status": "RUNNING"}
            status["pairs"].append(current)
            results: dict[str, dict[str, object]] = {}
            for system in order:
                common.verify_frozen(live=True)
                name = f"pair{pair}_{system}"
                status["runs"].append({"run": name, "state": "RUNNING"})
                save(OUT / "pilot_status.json", status)
                child(["campaign_scaling.worker", system, name, "measured"], name, gates, deadline)
                results[system] = json.loads((OUT / "runs" / name / "run.json").read_text())
                status["runs"][-1]["state"] = "PASS"
            check_pair(results["baseline"], results["mech_scal"])
            common.verify_frozen(live=True)
            current.update(paired_row(pair, order, results["baseline"], results["mech_scal"], time.monotonic() - pair_start))
            current["status"] = "PASS"
            save(OUT / "pilot_status.json", status)
        write_csv(OUT / "paired_results.csv", [dict(row) for row in status["pairs"]])
        statistics_payload = {}
        for field in ["processing_difference_seconds", "processing_overhead_percent", "rss_difference_kib", "db_difference_bytes", "additional_bytes_per_created_output"]:
            statistics_payload[field] = common.stats([float(row[field]) for row in status["pairs"]])
        save(OUT / "pilot_statistics.json", statistics_payload)
        consolidate()
        status["status"] = "PASS"
        status["recommendation"] = "PROCEED_TO_NEXT_LEVEL"
        status["finished_at"] = now()
    except BaseException:
        status["error"] = traceback.format_exc()
        consolidate() if OUT.exists() else None
    finally:
        if node is not None and node.poll() is None:
            try:
                common.rpc("stop")
                node.wait(timeout=60)
            except Exception:
                if node.poll() is None:
                    node.send_signal(signal.SIGTERM)
                    node.wait(timeout=60)
        status["shutdown"] = {"owned_node_closed": node is None or node.poll() is not None,
                              "ports_free": subprocess.run(["ss", "-H", "-ltn", "( sport = :19443 or sport = :19444 )"], capture_output=True, text=True).stdout.strip() == ""}
        status["finished_at"] = status.get("finished_at", now())
        if OUT.exists():
            if "gates" in locals() and getattr(gates, "samples", None):
                write_csv(OUT / "resource_gates.csv", gates.samples)
            save(OUT / "pilot_status.json", status)
            if status.get("status") == "PASS":
                consolidate()
        print(json.dumps({"status": status.get("status"), "recommendation": status.get("recommendation"), "shutdown": status["shutdown"]}, sort_keys=True), flush=True)
    return 0 if status.get("status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
