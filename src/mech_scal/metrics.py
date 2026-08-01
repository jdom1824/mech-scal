from __future__ import annotations

import random
import statistics
from collections import defaultdict

from baseline.metrics import compute_percentiles

from .database import MechScalDatabase
from .retrieval import MechScalRetriever


def benchmark_mech_scal_queries(
    database: MechScalDatabase,
    experimental_outpoints: list[str],
    missing_outpoints: list[str],
    repetitions: int,
    rng_seed: int = 20260731,
) -> dict[str, object]:
    retriever = MechScalRetriever(database)
    randomizer = random.Random(rng_seed)
    results: dict[str, list[dict[str, object]]] = defaultdict(list)

    for outpoint in experimental_outpoints:
        retriever.by_outpoint_text(outpoint)
        txid, vout_text = outpoint.split(":", 1)
        retriever.transition_history(txid, int(vout_text))

    phases = {"warm": experimental_outpoints + missing_outpoints, "cold-limited": experimental_outpoints + missing_outpoints}
    for phase, queries in phases.items():
        shuffled = queries[:]
        randomizer.shuffle(shuffled)
        for outpoint in shuffled:
            txid, vout_text = outpoint.split(":", 1)
            for query_type in ("basic", "class_current", "history"):
                for _ in range(repetitions):
                    if query_type == "basic":
                        result = retriever.by_outpoint_text(outpoint)
                    elif query_type == "class_current":
                        result = retriever.outpoint(txid, int(vout_text))
                    else:
                        result = retriever.transition_history(txid, int(vout_text))
                    database.insert_lookup_metric(
                        {
                            "phase": phase,
                            "query_type": query_type,
                            "target": outpoint,
                            "found": 1 if result.found else 0,
                            "latency_ms": result.latency_ms,
                            "error": None,
                        }
                    )
                    results[phase].append({"query_type": query_type, "found": result.found, "latency_ms": result.latency_ms, "error": None})
        database.commit()

    summary: dict[str, object] = {"phases": {}}
    for phase, rows in results.items():
        latencies = [float(row["latency_ms"]) for row in rows]
        found = sum(1 for row in rows if row["found"])
        not_found = sum(1 for row in rows if not row["found"])
        percentiles = compute_percentiles(latencies)
        summary["phases"][phase] = {
            "count": len(rows),
            "found": found,
            "not_found": not_found,
            "errors": 0,
            "success_rate": found / len(rows) if rows else 0.0,
            "not_found_rate": not_found / len(rows) if rows else 0.0,
            "mean_ms": statistics.fmean(latencies) if latencies else 0.0,
            "min_ms": min(latencies) if latencies else 0.0,
            "max_ms": max(latencies) if latencies else 0.0,
            **percentiles,
        }
    summary["limitation"] = "Cold cache is approximated only by query ordering; system caches were not cleared."
    return summary
