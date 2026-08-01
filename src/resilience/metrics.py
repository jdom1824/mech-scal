from __future__ import annotations

import math
import statistics


def percentile(sorted_values: list[float], q: float) -> float:
    if not sorted_values:
        return 0.0
    if len(sorted_values) == 1:
        return sorted_values[0]
    rank = (len(sorted_values) - 1) * q
    low = math.floor(rank)
    high = math.ceil(rank)
    if low == high:
        return sorted_values[low]
    return sorted_values[low] + (sorted_values[high] - sorted_values[low]) * (rank - low)


def summarize_numeric(values: list[float]) -> dict[str, float]:
    ordered = sorted(values)
    if not ordered:
        return {key: 0.0 for key in ("n", "mean", "median", "stdev", "min", "max", "p50", "p95", "p99", "cv")}
    mean = statistics.fmean(ordered)
    stdev = statistics.stdev(ordered) if len(ordered) > 1 else 0.0
    return {
        "n": float(len(ordered)),
        "mean": mean,
        "median": statistics.median(ordered),
        "stdev": stdev,
        "min": ordered[0],
        "max": ordered[-1],
        "p50": percentile(ordered, 0.50),
        "p95": percentile(ordered, 0.95),
        "p99": percentile(ordered, 0.99),
        "cv": stdev / mean if mean else 0.0,
    }


def wilson_interval(successes: int, trials: int, z: float = 1.96) -> tuple[float, float]:
    if trials == 0:
        return (0.0, 0.0)
    phat = successes / trials
    denom = 1.0 + (z * z) / trials
    centre = phat + (z * z) / (2.0 * trials)
    margin = z * math.sqrt((phat * (1.0 - phat) + (z * z) / (4.0 * trials)) / trials)
    return ((centre - margin) / denom, (centre + margin) / denom)
