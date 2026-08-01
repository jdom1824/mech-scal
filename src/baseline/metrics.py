from __future__ import annotations

import math
import random
import statistics
from collections import defaultdict

from .database import BaselineDatabase
from .retrieval import BaselineRetriever


def compute_percentiles(values: list[float]) -> dict[str, float]:
    if not values:
        return {"p50": 0.0, "p95": 0.0, "p99": 0.0}
    ordered = sorted(values)

    def percentile(target: float) -> float:
        if len(ordered) == 1:
            return ordered[0]
        rank = (len(ordered) - 1) * target
        low = math.floor(rank)
        high = math.ceil(rank)
        if low == high:
            return ordered[low]
        return ordered[low] + (ordered[high] - ordered[low]) * (rank - low)

    return {"p50": percentile(0.50), "p95": percentile(0.95), "p99": percentile(0.99)}


def benchmark_outpoint_queries(
    database: BaselineDatabase,
    experimental_outpoints: list[str],
    missing_outpoints: list[str],
    repetitions: int,
    rng_seed: int = 20260731,
) -> dict[str, object]:
    retriever = BaselineRetriever(database)
    randomizer = random.Random(rng_seed)
    results_by_phase: dict[str, list[dict[str, object]]] = defaultdict(list)

    warmup_queries = experimental_outpoints[:]
    randomizer.shuffle(warmup_queries)
    for outpoint in warmup_queries:
        retriever.by_outpoint(outpoint)

    phases = {
        "warm": experimental_outpoints + missing_outpoints,
        "cold-limited": experimental_outpoints + missing_outpoints,
    }
    for phase, queries in phases.items():
        shuffled = queries[:]
        randomizer.shuffle(shuffled)
        for outpoint in shuffled:
            for _ in range(repetitions):
                try:
                    result = retriever.by_outpoint(outpoint)
                    database.insert_lookup_metric(
                        {
                            "phase": phase,
                            "query_type": "outpoint",
                            "outpoint": outpoint,
                            "found": 1 if result.found else 0,
                            "latency_ms": result.latency_ms,
                            "error": None,
                        }
                    )
                    results_by_phase[phase].append(
                        {"outpoint": outpoint, "found": result.found, "latency_ms": result.latency_ms, "error": None}
                    )
                except Exception as exc:  # pragma: no cover - defensive
                    database.insert_lookup_metric(
                        {
                            "phase": phase,
                            "query_type": "outpoint",
                            "outpoint": outpoint,
                            "found": 0,
                            "latency_ms": 0.0,
                            "error": str(exc),
                        }
                    )
                    results_by_phase[phase].append({"outpoint": outpoint, "found": False, "latency_ms": 0.0, "error": str(exc)})
        database.commit()

    summary: dict[str, object] = {"phases": {}}
    for phase, rows in results_by_phase.items():
        latencies = [float(row["latency_ms"]) for row in rows if row["error"] is None]
        found = sum(1 for row in rows if row["found"])
        not_found = sum(1 for row in rows if not row["found"] and row["error"] is None)
        errors = sum(1 for row in rows if row["error"] is not None)
        percentiles = compute_percentiles(latencies)
        summary["phases"][phase] = {
            "count": len(rows),
            "found": found,
            "not_found": not_found,
            "errors": errors,
            "success_rate": found / len(rows) if rows else 0.0,
            "not_found_rate": not_found / len(rows) if rows else 0.0,
            "mean_ms": statistics.fmean(latencies) if latencies else 0.0,
            "min_ms": min(latencies) if latencies else 0.0,
            "max_ms": max(latencies) if latencies else 0.0,
            **percentiles,
        }
    summary["limitation"] = "Cold cache is approximated only by query ordering; no destructive cache clearing was performed."
    return summary
