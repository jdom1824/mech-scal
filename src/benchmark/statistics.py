from __future__ import annotations

import math
import random
import statistics


def _percentile(sorted_values: list[float], q: float) -> float:
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
        return {key: 0.0 for key in ("n", "mean", "median", "stdev", "min", "max", "p5", "p25", "p50", "p75", "p95", "p99", "cv")}
    mean = statistics.fmean(ordered)
    stdev = statistics.stdev(ordered) if len(ordered) > 1 else 0.0
    return {
        "n": float(len(ordered)),
        "mean": mean,
        "median": statistics.median(ordered),
        "stdev": stdev,
        "min": ordered[0],
        "max": ordered[-1],
        "p5": _percentile(ordered, 0.05),
        "p25": _percentile(ordered, 0.25),
        "p50": _percentile(ordered, 0.50),
        "p75": _percentile(ordered, 0.75),
        "p95": _percentile(ordered, 0.95),
        "p99": _percentile(ordered, 0.99),
        "cv": stdev / mean if mean else 0.0,
    }


def summarize_paired(baseline_values: list[float], mech_values: list[float]) -> tuple[list[float], list[float], dict[str, float], dict[str, float]]:
    absolute = [m - b for b, m in zip(baseline_values, mech_values)]
    percent = [100.0 * (m - b) / b if b else 0.0 for b, m in zip(baseline_values, mech_values)]
    return absolute, percent, summarize_numeric(absolute), summarize_numeric(percent)


def bootstrap_paired_median_ci(baseline_values: list[float], mech_values: list[float], seed: int, resamples: int = 10000) -> dict[str, float]:
    randomizer = random.Random(seed)
    pairs = list(zip(baseline_values, mech_values))
    if not pairs:
        return {"median_difference": 0.0, "ci_low": 0.0, "ci_high": 0.0}
    medians: list[float] = []
    for _ in range(resamples):
        sample = [pairs[randomizer.randrange(len(pairs))] for _ in range(len(pairs))]
        diffs = [m - b for b, m in sample]
        medians.append(statistics.median(diffs))
    ordered = sorted(medians)
    return {
        "median_difference": statistics.median([m - b for b, m in pairs]),
        "ci_low": _percentile(ordered, 0.025),
        "ci_high": _percentile(ordered, 0.975),
    }


def iqr_outlier_mask(values: list[float]) -> list[bool]:
    ordered = sorted(values)
    if len(ordered) < 4:
        return [False for _ in values]
    q1 = _percentile(ordered, 0.25)
    q3 = _percentile(ordered, 0.75)
    iqr = q3 - q1
    lower = q1 - 1.5 * iqr
    upper = q3 + 1.5 * iqr
    return [value < lower or value > upper for value in values]
