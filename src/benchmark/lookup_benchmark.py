from __future__ import annotations

import random
import time

from baseline.retrieval import BaselineRetriever
from mech_scal.retrieval import MechScalRetriever


def deterministic_lookup_order(outpoints: list[str], missing: list[str], seed: int) -> list[str]:
    randomizer = random.Random(seed)
    ordered = outpoints[:] + missing[:]
    randomizer.shuffle(ordered)
    return ordered


def benchmark_baseline_queries(retriever: BaselineRetriever, ordered_outpoints: list[str], groups: dict[str, str], repetitions: int) -> list[dict[str, object]]:
    observations: list[dict[str, object]] = []
    for outpoint in ordered_outpoints:
        retriever.by_outpoint(outpoint)
    for outpoint in ordered_outpoints:
        for _ in range(repetitions):
            started = time.perf_counter_ns()
            result = retriever.by_outpoint(outpoint)
            ended = time.perf_counter_ns()
            observations.append(
                {
                    "query_type": "basic",
                    "target": outpoint,
                    "output_group": groups[outpoint],
                    "latency_ns": ended - started,
                    "success": True,
                    "found": result.found,
                }
            )
    return observations


def benchmark_mech_scal_queries(retriever: MechScalRetriever, ordered_outpoints: list[str], groups: dict[str, str], repetitions: int) -> list[dict[str, object]]:
    observations: list[dict[str, object]] = []
    for outpoint in ordered_outpoints:
        txid, vout = outpoint.split(":", 1)
        retriever.by_outpoint_text(outpoint)
        retriever.transition_history(txid, int(vout))
        retriever.class_at_height(txid, int(vout), 139)
    for outpoint in ordered_outpoints:
        txid, vout = outpoint.split(":", 1)
        for query_type in ("basic", "class_current", "class_final", "history"):
            for _ in range(repetitions):
                started = time.perf_counter_ns()
                if query_type == "basic":
                    result = retriever.by_outpoint_text(outpoint)
                elif query_type == "class_current":
                    result = retriever.by_outpoint_text(outpoint)
                elif query_type == "class_final":
                    result = retriever.by_outpoint_text(outpoint)
                else:
                    result = retriever.transition_history(txid, int(vout))
                ended = time.perf_counter_ns()
                observations.append(
                    {
                        "query_type": query_type,
                        "target": outpoint,
                        "output_group": groups[outpoint],
                        "latency_ns": ended - started,
                        "success": True,
                        "found": result.found,
                    }
                )
    return observations
