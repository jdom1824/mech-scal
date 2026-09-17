"""W1-only runtime controller with bounded resource gates and owned shutdown."""
import hashlib
import json
import os
import shutil
import signal
import subprocess
import sys
import time
import traceback

from .common import CODE, CONFIG, DATA, HERE, OUT, ROOT, WORK, csvfile, rpc, save, stats, verify_frozen


def free_ports():
    r = subprocess.run(["ss", "-H", "-ltn", "( sport = :19443 or sport = :19444 )"],
                       capture_output=True, text=True, check=True)
    return not r.stdout.strip()


def unmounted(device):
    return subprocess.run(["findmnt", "-rn", "-S", device], capture_output=True).returncode == 1


class Gates:
    def __init__(self):
        self.high_since = None
        self.swap_since = None
        self.last_vm = None
        self.samples = []

    def check(self):
        from pathlib import Path
        now = time.monotonic()
        mem = {line.split(":")[0]: int(line.split()[1]) for line in Path("/proc/meminfo").read_text().splitlines()}
        vm = {line.split()[0]: int(line.split()[1]) for line in Path("/proc/vmstat").read_text().splitlines()}
        used = 1 - mem["MemAvailable"] / mem["MemTotal"]
        free = shutil.disk_usage(ROOT).free / 2**30
        swap_rate = 0.0
        if self.last_vm is not None:
            t, pages = self.last_vm
            swap_rate = max(0, vm["pswpin"] + vm["pswpout"] - pages) * os.sysconf("SC_PAGE_SIZE") / 2**20 / (now - t)
        self.last_vm = now, vm["pswpin"] + vm["pswpout"]
        self.high_since = (self.high_since or now) if used > CONFIG["ram_sustained_fraction"] else None
        self.swap_since = (self.swap_since or now) if swap_rate > CONFIG["swap_io_mib_per_second"] else None
        self.samples.append({"monotonic_seconds": now, "host_used_ram_fraction": used,
                             "free_disk_gib": free, "swap_io_mib_s": swap_rate})
        assert used <= CONFIG["ram_stop_fraction"], "RAM >85%"
        assert free >= CONFIG["free_disk_min_gib"], "Disk <20 GiB"
        assert self.high_since is None or now - self.high_since < CONFIG["ram_sustained_seconds"], "Sustained RAM >80%"
        assert self.swap_since is None or now - self.swap_since < CONFIG["swap_io_sustained_seconds"], "Swap thrashing gate"


def child(args, name, gates, deadline):
    env = os.environ.copy()
    env["PYTHONPATH"] = str(CODE)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    logpath = OUT / "logs" / (name + ".log")
    with logpath.open("x") as log:
        proc = subprocess.Popen([sys.executable, "-B", "-m"] + args, env=env, cwd=CODE,
                                stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
    try:
        while proc.poll() is None:
            gates.check()
            assert time.monotonic() < deadline, "Paired run/generation deadline exceeded"
            time.sleep(1)
        assert proc.returncode == 0, f"{name} failed; see {logpath}"
    except BaseException:
        if proc.poll() is None:
            os.killpg(proc.pid, signal.SIGTERM)
            try:
                proc.wait(timeout=30)
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid, signal.SIGKILL)
                proc.wait()
        raise


def owned(node, args, ticks):
    from pathlib import Path
    p = Path("/proc") / str(node.pid)
    assert (p / "cmdline").read_bytes().decode().strip("\0").split("\0") == args
    assert str((p / "exe").resolve()) == str(ROOT / "bitcoin/bin/bitcoind")
    assert (p / "stat").read_text().split(") ", 1)[1].split()[19] == ticks


def check_pair(b, m):
    assert b["validation"]["counts"] == m["validation"]["counts"], "Count mismatch"
    assert b["validation"]["sets"] == m["validation"]["sets"], "Functional set mismatch"
    assert m["validation"]["transition_invariants"] == "PASS"
    assert b["validation"]["quick_check"] == m["validation"]["quick_check"] == "ok"


def paired_row(pair, order, b, m, seconds):
    row = {"pair": pair, "order": " -> ".join(order), "status": "PASS",
           "baseline_processing_seconds": b["processing_seconds"], "mech_processing_seconds": m["processing_seconds"],
           "processing_difference_seconds": m["processing_seconds"] - b["processing_seconds"],
           "processing_overhead_percent": 100 * (m["processing_seconds"] / b["processing_seconds"] - 1),
           "baseline_peak_rss_kib": b["process_peak_rss_kib"], "mech_peak_rss_kib": m["process_peak_rss_kib"],
           "rss_difference_kib": m["process_peak_rss_kib"] - b["process_peak_rss_kib"],
           "baseline_db_bytes": b["storage"]["physical_bytes"], "mech_db_bytes": m["storage"]["physical_bytes"],
           "db_difference_bytes": m["storage"]["physical_bytes"] - b["storage"]["physical_bytes"],
           "baseline_basic_lookup_us": b["lookup_us"]["basic"]["median"],
           "mech_basic_lookup_us": m["lookup_us"]["basic"]["median"],
           "mech_current_lookup_us": m["lookup_us"]["current-layer"]["median"],
           "mech_history_lookup_us": m["lookup_us"]["history"]["median"],
           "basic_lookup_difference_us": m["lookup_us"]["basic"]["median"] - b["lookup_us"]["basic"]["median"],
           "current_vs_baseline_basic_difference_us": m["lookup_us"]["current-layer"]["median"] - b["lookup_us"]["basic"]["median"],
           "history_vs_baseline_basic_difference_us": m["lookup_us"]["history"]["median"] - b["lookup_us"]["basic"]["median"],
           "paired_run_wall_seconds": seconds}
    row["additional_bytes_per_created_output"] = row["db_difference_bytes"] / b["validation"]["counts"]["outputs"]
    lifecycle = sum(n for k, n in m["validation"]["transitions"].items() if not k.startswith("None"))
    row["lifecycle_transitions"] = lifecycle
    row["normalized_db_overhead_per_lifecycle_transition"] = row["db_difference_bytes"] / lifecycle
    return row


def main():
    node, args, ticks = None, None, None
    gates = Gates()
    status = {"status": "FAIL", "recommendation": "STOP", "runs": [], "pairs": []}
    try:
        assert CONFIG["authorization"] == "W1_PILOT_ONLY" and CONFIG["end_height"] == 999
        assert CONFIG["t_min"] == 24 and len(CONFIG["pair_order"]) == 3
        assert not OUT.exists() and not DATA.exists(), "Never rerun or replace this pilot"
        OUT.mkdir(parents=True)
        (OUT / "logs").mkdir()
        assert free_ports() and unmounted("/dev/nvme0n1p3") and unmounted("/dev/sda")
        assert subprocess.run(["pgrep", "-x", "bitcoind"], capture_output=True).returncode == 1
        gates.check()
        DATA.mkdir()
        shutil.copyfile(HERE / "bitcoin.conf", DATA / "bitcoin.conf")
        args = [str(ROOT / "bitcoin/bin/bitcoind"), "-regtest", f"-datadir={DATA}",
                f"-conf={DATA}/bitcoin.conf", "-bind=127.0.0.1:19444", "-connect=0", "-dnsseed=0", "-discover=0"]
        with (OUT / "logs/bitcoind.log").open("x") as log:
            node = subprocess.Popen(args, stdout=log, stderr=subprocess.STDOUT)
        from pathlib import Path
        ticks = (Path("/proc") / str(node.pid) / "stat").read_text().split(") ", 1)[1].split()[19]
        save(OUT / "owned_node.json", {"pid": node.pid, "args": args, "start_ticks": ticks})
        for _ in range(60):
            assert node.poll() is None
            try:
                info = rpc("getblockchaininfo")
                break
            except Exception:
                time.sleep(1)
        else:
            raise RuntimeError("RPC unavailable")
        owned(node, args, ticks)
        assert info["chain"] == "regtest" and info["blocks"] == 0 and rpc("getnetworkinfo")["connections"] == 0
        print("W1 owned regtest ready", flush=True)
        child(["campaign_scaling.generate"], "generation", gates, time.monotonic() + 1800)
        verify_frozen()
        for system in ["baseline", "mech_scal"]:
            name = "warmup_" + system
            status["runs"].append({"run": name, "state": "RUNNING"})
            save(OUT / "pilot_status.json", status)
            child(["campaign_scaling.worker", system, name, "diagnostic"], name, gates, time.monotonic() + 1800)
            status["runs"][-1]["state"] = "PASS"
            verify_frozen()
        b = json.loads((OUT / "runs/warmup_baseline/run.json").read_text())
        m = json.loads((OUT / "runs/warmup_mech_scal/run.json").read_text())
        check_pair(b, m)
        print("Both diagnostic warmups PASS", flush=True)
        for pair, order in enumerate(CONFIG["pair_order"], 1):
            pair_start = time.monotonic()
            deadline = pair_start + CONFIG["pair_timeout_seconds"]
            current = {"pair": pair, "order": order, "status": "RUNNING"}
            status["pairs"].append(current)
            results = {}
            for system in order:
                verify_frozen()
                assert time.monotonic() < deadline
                name = f"pair{pair}_" + system
                status["runs"].append({"run": name, "state": "RUNNING"})
                save(OUT / "pilot_status.json", status)
                child(["campaign_scaling.worker", system, name, "measured"], name, gates, deadline)
                results[system] = json.loads((OUT / "runs" / name / "run.json").read_text())
                status["runs"][-1]["state"] = "PASS"
            check_pair(results["baseline"], results["mech_scal"])
            verify_frozen()
            assert time.monotonic() < deadline
            current.update(paired_row(pair, order, results["baseline"], results["mech_scal"], time.monotonic() - pair_start))
            save(OUT / "pilot_status.json", status)
            print(f"Pair {pair} PASS", flush=True)
        csvfile(OUT / "paired_results.csv", [{k: v for k, v in row.items()} for row in status["pairs"]])
        fields = [k for k, v in status["pairs"][0].items() if isinstance(v, (int, float)) and k != "pair"]
        save(OUT / "pilot_statistics.json", {k: stats([p[k] for p in status["pairs"]]) for k in fields})
        status["status"] = "PASS"
        status["recommendation"] = "PENDING_PILOT_REVIEW"
    except BaseException:
        status["error"] = traceback.format_exc()
        for run in status["runs"]:
            if run["state"] == "RUNNING":
                run.update(state="FAIL", error=status["error"])
        for pair in status["pairs"]:
            if pair["status"] == "RUNNING":
                pair.update(status="FAIL", error=status["error"])
        print(status["error"], flush=True)
    finally:
        if node is not None and node.poll() is None:
            owned(node, args, ticks)
            try:
                rpc("stop")
                node.wait(timeout=60)
            except Exception:
                if node.poll() is None:
                    owned(node, args, ticks)
                    node.send_signal(signal.SIGTERM)
                    node.wait(timeout=60)
        status["shutdown"] = {"owned_node_closed": node is not None and node.poll() == 0,
                              "ports_free": free_ports(), "historical_unmounted": unmounted("/dev/nvme0n1p3"),
                              "sda_unmounted": unmounted("/dev/sda")}
        if not all(status["shutdown"].values()):
            status["status"], status["recommendation"] = "FAIL", "STOP"
        if OUT.exists():
            save(OUT / "pilot_status.json", status)
            if gates.samples:
                csvfile(OUT / "resource_gates.csv", gates.samples)
        print(json.dumps({"status": status["status"], "shutdown": status["shutdown"]}), flush=True)
    return 0 if status["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
