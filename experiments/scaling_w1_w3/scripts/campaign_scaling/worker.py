"""CAMPAIGN_INSTRUMENTATION: unmodified processors, isolated worker per run."""
import json
import resource
import sqlite3
import sys
import time

from .common import CONFIG, OUT, WORK, QUERY, configure_historical, csvfile, digest, save, stats, verify_frozen


def instrument(proc, db, system):
    rows = {}
    original_block = db.insert_block
    original_commit = db.commit
    active = [None]
    def block(payload):
        active[0] = payload["height"]
        return original_block(payload)
    def commit():
        result = original_commit()
        if active[0] is not None:
            r = rows.setdefault(active[0], {"height": active[0]})
            r.update(outputs_reconstructed=proc.total_outputs, current_utxo_count=proc.total_outputs - proc.total_inputs)
        return result
    db.insert_block, db.commit = block, commit
    if system == "mech_scal":
        class ConnectionObserver:
            def __init__(self, conn):
                self.conn = conn
                self.candidates = 0
            def __getattr__(self, name):
                return getattr(self.conn, name)
            def execute(self, sql, *args, **kwargs):
                cursor = self.conn.execute(sql, *args, **kwargs)
                if sql == QUERY:
                    self.candidates = 0
                    def count_rows():
                        for row in cursor:
                            self.candidates += 1
                            yield row
                    return count_rows()
                return cursor
        observer = ConnectionObserver(db.conn)
        db.conn = observer
        examined = [0]
        classify = proc.classifier.classify_temporal_transition
        def examined_classify(*args, **kwargs):
            examined[0] += 1
            return classify(*args, **kwargs)
        proc.classifier.classify_temporal_transition = examined_classify
        temporal = proc._apply_temporal_transitions
        def observed_temporal(height):
            examined[0] = 0
            before = proc.mh_to_ml_count
            temporal(height)
            assert observer.candidates == examined[0]
            rows.setdefault(height, {"height": height}).update(
                mh_before_temporal_check=observer.candidates,
                mh_candidates_returned=observer.candidates, mh_examined_python=examined[0],
                temporal_transitions_performed=proc.mh_to_ml_count - before)
        proc._apply_temporal_transitions = observed_temporal
    return rows


def validate(db, system, run_id):
    from baseline.validator import BaselineValidator
    from mech_scal.validator import MechScalValidator
    result = (BaselineValidator(db).validate_against_manifest(WORK / "manifest.jsonl", run_id)
              if system == "baseline" else MechScalValidator(db, 24).validate(WORK / "manifest.jsonl", run_id))
    assert result["status"] == "PASS", result
    conn = db.conn
    assert conn.execute("PRAGMA quick_check").fetchone()[0] == "ok"
    assert not conn.execute("PRAGMA foreign_key_check").fetchall()
    outputs = [tuple(r) for r in conn.execute("SELECT txid,vout,creation_height,creation_blockhash,value_sat,script_type,address,is_coinbase,is_spent,spend_txid,spend_height,spend_blockhash FROM outputs ORDER BY txid,vout")]
    txs = [tuple(r) for r in conn.execute("SELECT txid,blockhash,height,tx_index,is_coinbase,input_count,output_count FROM transactions ORDER BY txid")]
    spends = [tuple(r) for r in conn.execute("SELECT spend_txid,vin_index,prev_txid,prev_vout,spend_height,spend_blockhash FROM spends ORDER BY spend_txid,vin_index")]
    blocks = [tuple(r) for r in conn.execute("SELECT height,blockhash FROM blocks ORDER BY height")]
    expected_outputs, expected_txs, expected_spends, expected_blocks = {}, [], [], []
    for line in (WORK / "blocks.jsonl").open():
        b = json.loads(line)
        height, bh = b["height"], b["hash"]
        expected_blocks.append((height, bh))
        for index, tx in enumerate(b["tx"]):
            coinbase = "coinbase" in tx["vin"][0]
            expected_txs.append((tx["txid"], bh, height, index, int(coinbase), 0 if coinbase else len(tx["vin"]), len(tx["vout"])))
            for v in tx["vout"]:
                script = v["scriptPubKey"]
                expected_outputs[(tx["txid"], v["n"])] = [
                    tx["txid"], v["n"], height, bh, int(round(v["value"] * 100000000)),
                    script.get("type"), script.get("address"), int(coinbase), 0, None, None, None]
            if not coinbase:
                for i, vin in enumerate(tx["vin"]):
                    o = expected_outputs[(vin["txid"], vin["vout"])]
                    assert not o[8]
                    o[8:] = [1, tx["txid"], height, bh]
                    expected_spends.append((tx["txid"], i, vin["txid"], vin["vout"], height, bh))
    assert outputs == sorted(tuple(o) for o in expected_outputs.values())
    assert txs == sorted(expected_txs) and spends == sorted(expected_spends) and blocks == expected_blocks
    assert len(set((o[0], o[1]) for o in outputs)) == len(outputs)
    assert all(o[10] is None or o[10] >= o[2] for o in outputs)
    counts = {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in ["blocks", "transactions", "outputs", "spends"]}
    counts["unspent"] = sum(not o[8] for o in outputs)
    counts["same_block_spends"] = sum(o[8] and o[10] == o[2] for o in outputs)
    invariants, classes, transitions = "not_applicable", {}, {}
    if system == "mech_scal":
        classes = dict(conn.execute("SELECT current_class,COUNT(*) FROM outputs GROUP BY current_class"))
        state, seen = {}, set()
        by_key = {(o[0], o[1]): o for o in outputs}
        for tr in conn.execute("SELECT * FROM class_transitions ORDER BY transition_height,transition_id"):
            k = tr["txid"], tr["vout"]
            o = by_key[k]
            src, dst, age, h, reason = (tr[n] for n in ["from_class", "to_class", "age_blocks", "transition_height", "reason"])
            sig = k, src, dst, h, reason
            assert sig not in seen and src == state.get(k) and src != "IM"
            seen.add(sig)
            assert age == h - o[2] >= 0
            if src is None:
                assert dst == "MH" and age == 0 and reason == "output_created"
            elif dst == "ML":
                assert src == "MH" and age >= 24 and reason == "reached_t_min"
            else:
                assert dst == "IM" and src in {"MH", "ML"} and o[8] and h == o[10]
                assert reason == ("same_block_spend" if age == 0 else "spent_from_" + src.lower())
            state[k] = dst
            label = str(src) + "->" + dst
            transitions[label] = transitions.get(label, 0) + 1
        for o in conn.execute("SELECT * FROM outputs"):
            assert state[(o["txid"], o["vout"])] == o["current_class"] == o["final_class"]
            assert (o["current_class"] == "IM") == bool(o["is_spent"])
            if not o["is_spent"]:
                assert o["current_class"] == ("ML" if CONFIG["end_height"] - o["creation_height"] >= 24 else "MH")
        assert sum(classes.values()) == len(outputs)
        assert classes.get("IM", 0) == counts["spends"]
        assert classes.get("MH", 0) + classes.get("ML", 0) == counts["unspent"]
        invariants = "PASS"
    return {"status": "PASS", "legacy_validator": result, "counts": counts, "classes": classes,
            "transitions": transitions, "transition_invariants": invariants, "quick_check": "ok",
            "sets": {k: digest(v) for k, v in {"outputs": outputs, "transactions": txs, "spends": spends,
                       "blocks": blocks, "utxo": [o for o in outputs if not o[8]]}.items()},
            "scripts": "Exact common script_type/address fields and identical raw-block txids; full script hex resides in frozen blocks.jsonl."}


def storage(path, live_pragmas):
    with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as conn:
        pragmas = {p: conn.execute("PRAGMA " + p).fetchone()[0] for p in [
            "page_size", "page_count", "freelist_count", "journal_mode", "synchronous", "cache_size"]}
        objects = {r[0]: (r[1], r[2]) for r in conn.execute("SELECT name,type,tbl_name FROM sqlite_schema")}
        rows = []
        for name, allocated, payload, unused, pages in conn.execute(
            "SELECT name,SUM(pgsize),SUM(payload),SUM(unused),COUNT(*) FROM dbstat GROUP BY name ORDER BY name"):
            typ, table = objects.get(name, ("table", name))
            group = ("INDEXES" if typ == "index" else "COMMON RECONSTRUCTION" if name in [
                "blocks", "transactions", "outputs", "spends"] else "MECH-SCAL STRUCTURES" if name in [
                "class_transitions", "class_snapshots", "runs", "processing_metrics", "lookup_metrics",
                "validation_results", "baseline_comparison"] else "OTHER/UNALLOCATED")
            rows.append({"name": name, "type": typ, "table": table, "group": group,
                         "allocated_bytes": allocated, "payload_bytes": payload,
                         "unused_bytes": unused, "page_count": pages})
    physical = path.stat().st_size
    allocated = sum(r["allocated_bytes"] for r in rows)
    free = pragmas["freelist_count"] * pragmas["page_size"]
    assert physical == pragmas["page_count"] * pragmas["page_size"]
    assert physical == allocated + free
    if free:
        rows.append({"name": "freelist", "type": "unallocated", "table": "", "group": "OTHER/UNALLOCATED",
                     "allocated_bytes": free, "payload_bytes": 0, "unused_bytes": free, "page_count": pragmas["freelist_count"]})
    return {"physical_bytes": physical, "post_close_pragmas": pragmas, "live_connection_pragmas": live_pragmas,
            "sqlite_version": sqlite3.sqlite_version, "objects": rows, "reconciliation": "PASS"}


def lookup(db, system):
    from baseline.retrieval import BaselineRetriever
    from mech_scal.retrieval import MechScalRetriever
    retriever = BaselineRetriever(db) if system == "baseline" else MechScalRetriever(db)
    targets = json.loads((WORK / "lookup_targets.json").read_text())
    calls = {"basic": lambda target: retriever.by_outpoint(target)} if system == "baseline" else {
        "basic": lambda target: retriever.by_outpoint_text(target),
        "current-layer": lambda target: retriever.by_outpoint_text(target),
        "history": lambda target: retriever.transition_history(target.split(":")[0], int(target.split(":")[1]))}
    observations, summary = [], {}
    for query, call in calls.items():
        for target in targets:
            assert call(target).found
        times = []
        for target in targets:
            for rep in range(CONFIG["lookup_repetitions"]):
                t = time.perf_counter_ns()
                result = call(target)
                elapsed = time.perf_counter_ns() - t
                assert result.found
                times.append(elapsed / 1000)
                observations.append({"query_type": query, "target": target, "repetition": rep,
                                     "latency_ns": elapsed, "found": result.found})
        summary[query] = stats(times)
    return summary, observations


def run(system, run_name, diagnostic):
    verify_frozen(live=False)
    configure_historical()
    from baseline.config import BaselineRunConfig
    from baseline.database import BaselineDatabase
    from baseline.processor import BaselineProcessor
    from mech_scal.config import MechScalRunConfig
    from mech_scal.database import MechScalDatabase
    from mech_scal.processor import MechScalProcessor
    directory = OUT / "runs" / run_name
    directory.mkdir(parents=True, exist_ok=False)
    path = directory / "processor.sqlite"
    wall_start = time.perf_counter()
    db = BaselineDatabase(path) if system == "baseline" else MechScalDatabase(path)
    config = (BaselineRunConfig(0, CONFIG["end_height"], path, leave_running=True) if system == "baseline" else
              MechScalRunConfig(0, CONFIG["end_height"], path, t_min=24, leave_running=True))
    proc = BaselineProcessor(config, db) if system == "baseline" else MechScalProcessor(config, db)
    diagnostic_rows = instrument(proc, db, system) if diagnostic else {}
    init_seconds = time.perf_counter() - wall_start
    result = proc.process()
    wall = time.perf_counter() - wall_start
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    vmhwm = next(int(l.split()[1]) for l in open("/proc/self/status") if l.startswith("VmHWM:"))
    metrics = result["metrics"]
    live_pragmas = {p: db.conn.execute("PRAGMA " + p).fetchone()[0] for p in [
        "page_size", "page_count", "freelist_count", "journal_mode", "synchronous", "cache_size"]}
    plan = [tuple(r) for r in db.conn.execute("EXPLAIN QUERY PLAN " + QUERY)] if system == "mech_scal" else []
    validation = validate(db, system, result["run_id"])
    lookups, raw_lookup = lookup(db, system)
    save(directory / "validation.json", validation)
    csvfile(directory / "lookup_raw.csv", raw_lookup)
    if diagnostic:
        rows = [diagnostic_rows[h] for h in sorted(diagnostic_rows)]
        assert len(rows) == CONFIG["end_height"] + 1
        for row, duration in zip(rows, proc.block_durations):
            row["diagnostic_block_seconds"] = duration
        csvfile(directory / "block_diagnostics.csv", rows)
    db.close()
    layout = storage(path, live_pragmas)
    csvfile(directory / "dbstat.csv", layout["objects"])
    output = {"status": "PASS", "system": system, "run": run_name, "warmup": diagnostic,
              "processing_seconds": metrics["total_seconds"], "whole_processor_wall_seconds": wall,
              "initialization_seconds": init_seconds, "initialization_scope": "DB object and processor construction only; historical schema/RPC prelude stays in whole wall",
              "legacy_sampled_peak_rss_kib": metrics["peak_rss_kib"],
              "process_peak_rss_kib": peak, "vmhwm_at_processor_return_kib": vmhwm,
              "worker_lifetime_peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
              "seconds_per_block": metrics["total_seconds"] / validation["counts"]["blocks"],
              "seconds_per_transaction": metrics["total_seconds"] / validation["counts"]["transactions"],
              "seconds_per_output": metrics["total_seconds"] / validation["counts"]["outputs"],
              "metrics": metrics, "validation": validation, "storage": layout, "explain_query_plan": plan,
              "lookup_us": lookups, "lookup_semantics": "basic=current-layer=class_final call path for Mech-Scal; class_final not separately measured"}
    save(directory / "run.json", output)
    print(json.dumps({k: output[k] for k in ["status", "run", "processing_seconds", "process_peak_rss_kib"]}), flush=True)


if __name__ == "__main__":
    run(sys.argv[1], sys.argv[2], sys.argv[3] == "diagnostic")
