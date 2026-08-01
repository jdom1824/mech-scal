from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from benchmark.config import Phase6Config  # noqa: E402
from benchmark.lookup_benchmark import deterministic_lookup_order  # noqa: E402
from benchmark.runner import Phase6Runner  # noqa: E402
from benchmark.statistics import (  # noqa: E402
    bootstrap_paired_median_ci,
    iqr_outlier_mask,
    summarize_numeric,
    summarize_paired,
)


class BenchmarkLogicTests(unittest.TestCase):
    def test_deterministic_lookup_order(self) -> None:
        first = deterministic_lookup_order(["a:0", "b:0"], ["x:0"], 20260731)
        second = deterministic_lookup_order(["a:0", "b:0"], ["x:0"], 20260731)
        self.assertEqual(first, second)

    def test_numeric_summary(self) -> None:
        summary = summarize_numeric([1.0, 2.0, 3.0, 4.0])
        self.assertEqual(summary["median"], 2.5)

    def test_paired_summary_and_bootstrap(self) -> None:
        _, _, _, overhead = summarize_paired([1.0, 2.0], [2.0, 4.0])
        self.assertEqual(overhead["median"], 100.0)
        ci = bootstrap_paired_median_ci([1.0, 2.0], [2.0, 4.0], 20260731, resamples=100)
        self.assertGreaterEqual(ci["median_difference"], 1.0)

    def test_outlier_mask(self) -> None:
        mask = iqr_outlier_mask([1.0, 1.1, 1.2, 10.0])
        self.assertEqual(mask[-1], True)

    def test_estimates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = Phase6Config(data_dir=Path(tmp) / "data", results_dir=Path(tmp) / "results", logs_dir=Path(tmp) / "logs")
            runner = Phase6Runner(config)
            self.assertGreater(runner.estimate_duration_seconds(), 0.0)
            self.assertGreater(runner.estimate_storage_bytes(), 0)
