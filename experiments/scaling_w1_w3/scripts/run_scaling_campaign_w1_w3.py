#!/usr/bin/env python3
"""Reproduce the W1--W3 scaling campaign in isolated regtest directories.

The script is intentionally opt-in and never uses a mainnet datadir. It
requires a caller-provided workspace and Bitcoin Core binary directory. The
included frozen CSVs are the publication evidence; this controller is the
heavier full-reproduction path and is not run by the verification command.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = PACKAGE_ROOT.parents[1]
CAMPAIGN_SOURCE = PACKAGE_ROOT / "scripts" / "campaign_scaling"
PROCESSOR_SOURCE = PACKAGE_ROOT / "scripts" / "process_frozen_level.py"
CONFIG_SOURCE = PACKAGE_ROOT / "configs" / "w1_w2_w3.json"
RPC_PORT = 19443
P2P_PORT = 19444


def run(command: list[str], *, cwd: Path, env: dict[str, str]) -> None:
    subprocess.run(command, cwd=cwd, env=env, check=True)


def start_node(bitcoin_bin: Path, datadir: Path, conf: Path) -> subprocess.Popen[bytes]:
    args = [
        str(bitcoin_bin / "bitcoind"), "-regtest", f"-datadir={datadir}", f"-conf={conf}",
        "-server=1", "-listen=1", "-bind=127.0.0.1", "-rpcbind=127.0.0.1",
        f"-rpcport={RPC_PORT}", f"-port={P2P_PORT}", "-connect=0", "-dnsseed=0",
        "-discover=0", "-fallbackfee=0.0001",
    ]
    log = (datadir.parent / "bitcoind.log").open("w", encoding="utf-8")
    node = subprocess.Popen(args, stdout=log, stderr=subprocess.STDOUT)
    cli = [str(bitcoin_bin / "bitcoin-cli"), "-regtest", f"-datadir={datadir}", f"-rpcport={RPC_PORT}"]
    try:
        for _ in range(90):
            if node.poll() is not None:
                raise RuntimeError("owned regtest node exited during startup")
            if subprocess.run(cli + ["getblockchaininfo"], capture_output=True).returncode == 0:
                return node
            time.sleep(1)
        raise RuntimeError("regtest RPC startup timeout")
    except BaseException:
        if node.poll() is None:
            node.terminate()
            node.wait(timeout=30)
        raise


def stop_node(bitcoin_bin: Path, datadir: Path, node: subprocess.Popen[bytes]) -> None:
    cli = [str(bitcoin_bin / "bitcoin-cli"), "-regtest", f"-datadir={datadir}", f"-rpcport={RPC_PORT}"]
    if node.poll() is None:
        subprocess.run(cli + ["stop"], capture_output=True, check=False)
        try:
            node.wait(timeout=60)
        except subprocess.TimeoutExpired:
            node.send_signal(signal.SIGTERM)
            node.wait(timeout=30)


def build_level(level_root: Path, workload: dict[str, object], config_base: dict[str, object]) -> Path:
    if level_root.exists():
        raise RuntimeError(f"refusing to reuse existing level directory: {level_root}")
    level_root.mkdir(parents=True)
    code = level_root / "campaign_code"
    (code / "src").mkdir(parents=True)
    shutil.copytree(CAMPAIGN_SOURCE, code / "campaign_scaling")
    shutil.copytree(REPO_ROOT / "src", code / "src", dirs_exist_ok=True)
    config = dict(config_base)
    config.update({
        "seed": config_base["seed"],
        "t_min": config_base["threshold_blocks"],
        "end_height": workload["target_height"],
        "pair_order": workload["pair_order"],
    })
    config.pop("threshold_blocks", None)
    config.pop("workloads", None)
    (code / "campaign_scaling" / "config.json").write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    (level_root / "level_design.json").write_text(json.dumps(workload, indent=2) + "\n", encoding="utf-8")
    shutil.copy2(PROCESSOR_SOURCE, level_root / "process_frozen_level.py")
    return code


def run_level(level_root: Path, code: Path, bitcoin_bin: Path) -> None:
    level_id = level_root.name
    datadir = level_root / ("regtest_" + level_id)
    datadir.mkdir()
    conf = code / "campaign_scaling" / "bitcoin.conf"
    env = os.environ.copy()
    env.update({
        "PYTHONPATH": str(code),
        "CAMPAIGN_CODE": str(code),
        "CAMPAIGN_ROOT": str(level_root),
        "CAMPAIGN_ATTEMPT_ID": level_id,
        "CAMPAIGN_WALLET": level_id + "_wallet",
    })
    node = start_node(bitcoin_bin, datadir, conf)
    try:
        run([sys.executable, "-B", "-m", "campaign_scaling.generate"], cwd=code, env=env)
        run([sys.executable, "-B", str(level_root / "process_frozen_level.py")], cwd=level_root,
            env={**env, "SOURCE_ROOT": str(level_root), "SOURCE_ATTEMPT": level_id,
                 "PROCESS_ATTEMPT": "processing_" + level_id, "BITCOIN_ROOT": str(bitcoin_bin)})
    finally:
        stop_node(bitcoin_bin, datadir, node)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-root", type=Path, required=True,
                        help="empty or new directory for generated W1-W3 level directories")
    parser.add_argument("--bitcoin-bin", type=Path, required=True,
                        help="directory containing bitcoind and bitcoin-cli")
    args = parser.parse_args()
    base_root = args.base_root.resolve()
    bitcoin_bin = args.bitcoin_bin.resolve()
    if base_root.exists() and any(base_root.iterdir()):
        raise SystemExit(f"refusing non-empty base root: {base_root}")
    if not (bitcoin_bin / "bitcoind").is_file() or not (bitcoin_bin / "bitcoin-cli").is_file():
        raise SystemExit("--bitcoin-bin must contain bitcoind and bitcoin-cli")
    config = json.loads(CONFIG_SOURCE.read_text(encoding="utf-8"))
    for workload in config["workloads"]:
        level_root = base_root / workload["id"]
        code = build_level(level_root, workload, config)
        run_level(level_root, code, bitcoin_bin)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
