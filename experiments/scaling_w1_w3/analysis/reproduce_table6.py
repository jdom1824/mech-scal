#!/usr/bin/env python3
"""Recompute the W1--W3 scaling table from the public CSV artifacts."""
from __future__ import annotations

import csv
import math
import sys
from collections import defaultdict
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
RESULTS = PACKAGE_ROOT / "results"
MIb = 1024.0 * 1024.0

EXPECTED = {
    "W1": {"blocks": 1000, "outputs": 3883, "pairs": 3, "processing_b": "24.20 [0.69]", "processing_m": "28.89 [1.77]", "overhead": "19.40 [10.52]", "rss_b": "30.21", "rss_m": "30.21", "db_b": "3.32", "db_m": "5.73", "lookup_b": "26.54", "lookup_m": "29.75", "index_b": "1.69", "index_m": "3.05"},
    "W2": {"blocks": 5001, "outputs": 20085, "pairs": 5, "processing_b": "128.24 [8.31]", "processing_m": "155.92 [1.84]", "overhead": "21.58 [9.05]", "rss_b": "47.28", "rss_m": "47.28", "db_b": "17.02", "db_m": "29.57", "lookup_b": "26.83", "lookup_m": "30.63", "index_b": "8.70", "index_m": "15.75"},
    "W3": {"blocks": 10001, "outputs": 40335, "pairs": 5, "processing_b": "262.78 [2.57]", "processing_m": "341.87 [14.79]", "overhead": "28.85 [3.18]", "rss_b": "83.54", "rss_m": "83.60", "db_b": "34.27", "db_m": "59.45", "lookup_b": "26.54", "lookup_m": "30.33", "index_b": "17.57", "index_m": "31.68"},
}


def fail(message: str) -> "NoReturn":
    raise SystemExit("FAIL: " + message)


def rows(name: str) -> list[dict[str, str]]:
    path = RESULTS / name
    if not path.is_file():
        fail(f"missing required input {path}")
    with path.open(newline="", encoding="utf-8") as handle:
        result = list(csv.DictReader(handle))
    if not result:
        fail(f"empty input {path}")
    return result


def number(row: dict[str, str], key: str) -> float:
    try:
        return float(row[key])
    except (KeyError, TypeError, ValueError) as exc:
        fail(f"invalid numeric value for {key}: {exc}")


def quantile(values: list[float], probability: float) -> float:
    """Linear quantile, matching pandas/NumPy method='linear'."""
    ordered = sorted(values)
    if not ordered:
        fail("quantile received no observations")
    position = (len(ordered) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] + fraction * (ordered[upper] - ordered[lower])


def summary(values: list[float]) -> tuple[float, float, float, float]:
    q1 = quantile(values, 0.25)
    median = quantile(values, 0.50)
    q3 = quantile(values, 0.75)
    return median, q1, q3, q3 - q1


def fmt(value: float) -> str:
    return str(Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def fmt_iqr(values: list[float]) -> str:
    median, _, _, iqr = summary(values)
    return f"{fmt(median)} [{fmt(iqr)}]"


def main() -> int:
    run_rows = rows("scaling_master_runs.csv")
    pair_rows = rows("scaling_master_pairs.csv")
    lookup_rows = rows("scaling_lookup_run_level.csv")
    dbstat_rows = rows("scaling_dbstat_per_run.csv")

    measured = [r for r in run_rows if r.get("warmup", "").lower() == "false" and r.get("status") == "PASS"]
    if len(measured) != 26:
        fail(f"expected 26 measured PASS run rows, found {len(measured)}")
    pairs = [r for r in pair_rows if r.get("status") == "PASS"]
    if len(pairs) != 13:
        fail(f"expected 13 PASS pair rows, found {len(pairs)}")

    out: list[dict[str, str]] = []
    grouped_runs: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    grouped_pairs: dict[str, list[dict[str, str]]] = defaultdict(list)
    grouped_lookup: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    grouped_dbstat: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for row in measured:
        grouped_runs[(row["workload"], row["system"])].append(row)
    for row in pairs:
        grouped_pairs[row["workload"]].append(row)
    for row in lookup_rows:
        if row.get("query_type") == "basic":
            grouped_lookup[(row["workload"], row["system"])].append(row)
    for row in dbstat_rows:
        grouped_dbstat[(row["workload"], row["system"])].append(row)

    for workload, expected in EXPECTED.items():
        workload_runs = [r for r in measured if r["workload"] == workload]
        if not workload_runs:
            fail(f"no measured rows for {workload}")
        if int(workload_runs[0]["blocks"]) != expected["blocks"] or int(workload_runs[0]["outputs"]) != expected["outputs"]:
            fail(f"workload dimensions changed for {workload}")
        if len(grouped_pairs[workload]) != expected["pairs"]:
            fail(f"pair count changed for {workload}")

        metrics: dict[str, str] = {
            "workload": workload,
            "blocks": str(expected["blocks"]),
            "reconstructed_outputs": str(expected["outputs"]),
            "n_pairs": str(expected["pairs"]),
        }
        for system, short in (("baseline", "b"), ("mech_scal", "m")):
            group = grouped_runs[(workload, system)]
            if len(group) != expected["pairs"]:
                fail(f"{workload}/{system} run count mismatch")
            processing = [number(r, "processing_seconds") for r in group]
            rss = [number(r, "peak_rss_kib") / 1024.0 for r in group]
            db = [number(r, "physical_db_bytes") / MIb for r in group]
            lookup_group = grouped_lookup[(workload, system)]
            if len(lookup_group) != expected["pairs"]:
                fail(f"{workload}/{system} basic lookup run count mismatch")
            lookup = [number(r, "median_us") for r in lookup_group]
            dbstat_group = grouped_dbstat[(workload, system)]
            if len(dbstat_group) != expected["pairs"]:
                fail(f"{workload}/{system} dbstat run count mismatch")
            index = []
            for r in dbstat_group:
                common = number(r, "common_indexes_bytes")
                extra = number(r, "mech_specific_indexes_bytes") if system == "mech_scal" else 0.0
                index.append((common + extra) / MIb)
            metrics.update({
                f"processing_{short}_s": fmt_iqr(processing),
                f"rss_{short}_mib": fmt(summary(rss)[0]),
                f"db_{short}_mib": fmt(summary(db)[0]),
                f"lookup_{short}_us": fmt(summary(lookup)[0]),
                f"index_{short}_mib": fmt(summary(index)[0]),
            })
        overhead = [number(r, "paired_overhead_percent") for r in grouped_pairs[workload]]
        metrics["paired_overhead_percent"] = fmt_iqr(overhead)
        expected_values = {
            "processing_b": metrics["processing_b_s"], "processing_m": metrics["processing_m_s"],
            "overhead": metrics["paired_overhead_percent"], "rss_b": metrics["rss_b_mib"],
            "rss_m": metrics["rss_m_mib"], "db_b": metrics["db_b_mib"], "db_m": metrics["db_m_mib"],
            "lookup_b": metrics["lookup_b_us"], "lookup_m": metrics["lookup_m_us"],
            "index_b": metrics["index_b_mib"], "index_m": metrics["index_m_mib"],
        }
        for key, value in expected_values.items():
            if value != expected[key]:
                fail(f"{workload} {key}: calculated {value!r}, expected {expected[key]!r}")
        out.append(metrics)

    output = RESULTS / "table6_reproduced.csv"
    fields = list(out[0])
    with output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(out)

    print("PASS: Table 6 reproduced from public frozen CSVs")
    print("| Workload | N | Blocks | Outputs | Processing B/M (s; median [IQR]) | Overhead (median [IQR], %) | RSS B/M (MiB) | DB B/M (MiB) | Lookup B/M (us) | Index B/M (MiB) |")
    print("| --- | ---: | ---: | ---: | --- | --- | --- | --- | --- | --- |")
    for row in out:
        print(f"| {row['workload']} | {row['n_pairs']} | {row['blocks']} | {row['reconstructed_outputs']} | {row['processing_b_s']} / {row['processing_m_s']} | {row['paired_overhead_percent']} | {row['rss_b_mib']} / {row['rss_m_mib']} | {row['db_b_mib']} / {row['db_m_mib']} | {row['lookup_b_us']} / {row['lookup_m_us']} | {row['index_b_mib']} / {row['index_m_mib']} |")
    print(f"Wrote {output}")
    return 0


if __name__ == "__main__":
    main()
