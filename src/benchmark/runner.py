from __future__ import annotations

import json
import os
import statistics
import subprocess
import time
from pathlib import Path

from baseline.database import BaselineDatabase
from baseline.retrieval import BaselineRetriever
from benchmark.lookup_benchmark import (
    benchmark_baseline_queries,
    benchmark_mech_scal_queries,
    deterministic_lookup_order,
)
from benchmark.reporter import write_csv, write_json, write_latex_table
from benchmark.resource_monitor import (
    approximate_cpu_percent,
    process_cpu_seconds,
    read_load_average,
    read_mem_available_kib,
    read_temperature_c,
    sqlite_page_info,
)
from benchmark.statistics import (
    bootstrap_paired_median_ci,
    iqr_outlier_mask,
    summarize_numeric,
    summarize_paired,
)
from benchmark.validator import experimental_groups
from mech_scal.database import MechScalDatabase
from mech_scal.retrieval import MechScalRetriever
from workload.rpc import RegtestRPC

from .config import (
    MIN_AVAILABLE_MEMORY_BYTES,
    PROJECT_ROOT,
    REGTEST_CLI,
    START_SCRIPT,
    STOP_SCRIPT,
    Phase6Config,
)


class Phase6Runner:
    def __init__(self, config: Phase6Config):
        self.config = config
        self.rpc = RegtestRPC(REGTEST_CLI, PROJECT_ROOT)
        self.logs: list[str] = []

    def estimate_storage_bytes(self) -> int:
        baseline_ref = self.config.data_dir.parent.parent / "baseline" / "small_seed_20260731" / "baseline.sqlite"
        mech_ref = self.config.data_dir.parent.parent / "mech_scal" / "small_seed_20260731" / "mech_scal.sqlite"
        baseline_size = baseline_ref.stat().st_size if baseline_ref.exists() else 401408
        mech_size = mech_ref.stat().st_size if mech_ref.exists() else 634880
        projected = (baseline_size + mech_size) * self.config.projected_run_count
        return projected

    def estimate_duration_seconds(self) -> float:
        return self.config.measured_pairs * (4.0 + 4.0 + 5.0) + self.config.warmup_runs * 2 * 4.0

    def run(self, recover_existing: bool = False) -> dict[str, object]:
        outpoints, group_map = experimental_groups(PROJECT_ROOT / "data" / "workloads" / "small_seed_20260731" / "manifest.jsonl")
        missing = [f"deadbeef{idx:056x}:{idx % 3}" for idx in range(20)]
        ordered_outpoints = deterministic_lookup_order(outpoints, missing, self.config.seed)
        raw_processing_runs: list[dict[str, object]] = []
        raw_block_metrics: list[dict[str, object]] = []
        raw_lookup_observations: list[dict[str, object]] = []
        valid_pairs = 0
        invalid_pairs = 0

        if recover_existing:
            return self._recover_existing_runs(ordered_outpoints, group_map, missing)

        self._ensure_regtest()

        for warmup_index in range(1, self.config.warmup_runs + 1):
            self._run_single("baseline", warmup_index, measured=False, ordered_outpoints=ordered_outpoints, group_map=group_map, missing=missing)
            time.sleep(5)
            self._run_single("mech_scal", warmup_index, measured=False, ordered_outpoints=ordered_outpoints, group_map=group_map, missing=missing)
            time.sleep(5)

        for run_number in range(1, self.config.measured_pairs + 1):
            baseline_result = self._run_single("baseline", run_number, measured=True, ordered_outpoints=ordered_outpoints, group_map=group_map, missing=missing)
            raw_processing_runs.append(baseline_result["processing"])
            raw_block_metrics.extend(baseline_result["blocks"])
            raw_lookup_observations.extend(baseline_result["lookups"])
            time.sleep(5)
            mech_result = self._run_single("mech_scal", run_number, measured=True, ordered_outpoints=ordered_outpoints, group_map=group_map, missing=missing)
            raw_processing_runs.append(mech_result["processing"])
            raw_block_metrics.extend(mech_result["blocks"])
            raw_lookup_observations.extend(mech_result["lookups"])
            if baseline_result["processing"]["validation_status"] == "PASS" and mech_result["processing"]["validation_status"] == "PASS":
                valid_pairs += 1
            else:
                invalid_pairs += 1
            time.sleep(5)

        subprocess.run([str(STOP_SCRIPT)], cwd=PROJECT_ROOT, text=True, check=False)

        summary = self._aggregate(raw_processing_runs, raw_lookup_observations, valid_pairs, invalid_pairs)
        self._write_outputs(raw_processing_runs, raw_block_metrics, raw_lookup_observations, summary)
        return summary

    def _recover_existing_runs(self, ordered_outpoints: list[str], group_map: dict[str, str], missing: list[str]) -> dict[str, object]:
        raw_processing_runs: list[dict[str, object]] = []
        raw_block_metrics: list[dict[str, object]] = []
        raw_lookup_observations: list[dict[str, object]] = []
        valid_pairs = 0
        invalid_pairs = 0
        for run_number in range(1, self.config.measured_pairs + 1):
            baseline_result = self._collect_existing_run("baseline", run_number, ordered_outpoints, group_map, missing)
            mech_result = self._collect_existing_run("mech_scal", run_number, ordered_outpoints, group_map, missing)
            raw_processing_runs.append(baseline_result["processing"])
            raw_processing_runs.append(mech_result["processing"])
            raw_block_metrics.extend(baseline_result["blocks"])
            raw_block_metrics.extend(mech_result["blocks"])
            raw_lookup_observations.extend(baseline_result["lookups"])
            raw_lookup_observations.extend(mech_result["lookups"])
            if baseline_result["processing"]["validation_status"] == "PASS" and mech_result["processing"]["validation_status"] == "PASS":
                valid_pairs += 1
            else:
                invalid_pairs += 1

        summary = self._aggregate(raw_processing_runs, raw_lookup_observations, valid_pairs, invalid_pairs)
        self._write_outputs(raw_processing_runs, raw_block_metrics, raw_lookup_observations, summary)
        return summary

    def _run_single(self, system: str, run_number: int, measured: bool, ordered_outpoints: list[str], group_map: dict[str, str], missing: list[str]) -> dict[str, object]:
        self._ensure_regtest()
        available_start = read_mem_available_kib()
        if available_start * 1024 < MIN_AVAILABLE_MEMORY_BYTES:
            raise RuntimeError("available memory dropped below 1.5 GiB")
        start_iso = time.strftime("%Y-%m-%dT%H:%M:%S%z")
        temperature_start = read_temperature_c()
        load_start = read_load_average()
        db_dir = self.config.data_dir / f"{system}_run_{run_number:02d}"
        db_dir.mkdir(parents=True, exist_ok=True)
        db_path = db_dir / f"{system}.sqlite"
        result_dir = self.config.results_dir / "per_run" / f"{system}_run_{run_number:02d}"
        result_dir.mkdir(parents=True, exist_ok=True)
        command = self._command_for(system, db_path)
        proc = subprocess.run(command, cwd=PROJECT_ROOT, capture_output=True, text=True, check=True)
        stdout = proc.stdout
        json_start = stdout.find("{")
        payload = json.loads(stdout[json_start:])
        return self._collect_run_artifacts(
            system=system,
            run_number=run_number,
            measured=measured,
            ordered_outpoints=ordered_outpoints,
            group_map=group_map,
            missing=missing,
            db_path=db_path,
            start_iso=start_iso,
            end_iso=time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            available_start=available_start,
            available_end=read_mem_available_kib(),
            load_start=load_start,
            load_end=read_load_average(),
            temperature_start=temperature_start,
            temperature_end=read_temperature_c(),
            run_id_hint=str(payload.get("run_id", "")),
        )

    def _collect_existing_run(self, system: str, run_number: int, ordered_outpoints: list[str], group_map: dict[str, str], missing: list[str]) -> dict[str, object]:
        db_path = self.config.data_dir / f"{system}_run_{run_number:02d}" / f"{system}.sqlite"
        if not db_path.exists():
            raise FileNotFoundError(f"missing benchmark database: {db_path}")
        now_iso = time.strftime("%Y-%m-%dT%H:%M:%S%z")
        available = read_mem_available_kib()
        load = read_load_average()
        temperature = read_temperature_c()
        return self._collect_run_artifacts(
            system=system,
            run_number=run_number,
            measured=True,
            ordered_outpoints=ordered_outpoints,
            group_map=group_map,
            missing=missing,
            db_path=db_path,
            start_iso=now_iso,
            end_iso=now_iso,
            available_start=available,
            available_end=available,
            load_start=load,
            load_end=load,
            temperature_start=temperature,
            temperature_end=temperature,
            run_id_hint="",
        )

    def _collect_run_artifacts(
        self,
        system: str,
        run_number: int,
        measured: bool,
        ordered_outpoints: list[str],
        group_map: dict[str, str],
        missing: list[str],
        db_path: Path,
        start_iso: str,
        end_iso: str,
        available_start: int,
        available_end: int,
        load_start: float,
        load_end: float,
        temperature_start: float | None,
        temperature_end: float | None,
        run_id_hint: str,
    ) -> dict[str, object]:
        pid = os.getpid()
        if system == "baseline":
            db = BaselineDatabase(db_path)
            try:
                metrics_row = dict(db.conn.execute("SELECT * FROM processing_metrics").fetchone())
                run_id = run_id_hint or str(metrics_row.get("run_id", f"{system}_run_{run_number:02d}"))
                validation_status = self._validate_baseline(db_path, run_id)
                lookup_obs = benchmark_baseline_queries(BaselineRetriever(db), ordered_outpoints, {**group_map, **{item: "nonexistent" for item in missing}}, self.config.lookup_repetitions) if measured else []
                counts = {
                    "spends_processed": db.count_rows("spends"),
                    "blocks": db.count_rows("blocks"),
                    "transactions": db.count_rows("transactions"),
                    "outputs": db.count_rows("outputs"),
                }
            finally:
                db.close()
        else:
            db = MechScalDatabase(db_path)
            try:
                metrics_row = dict(db.conn.execute("SELECT * FROM processing_metrics").fetchone())
                run_id = run_id_hint or str(metrics_row.get("run_id", f"{system}_run_{run_number:02d}"))
                validation_status = self._validate_mech_scal(db_path, run_id)
                lookup_obs = benchmark_mech_scal_queries(MechScalRetriever(db), ordered_outpoints, {**group_map, **{item: "nonexistent" for item in missing}}, self.config.lookup_repetitions) if measured else []
                counts = {
                    "spends_processed": db.count_rows("spends"),
                    "blocks": db.count_rows("blocks"),
                    "transactions": db.count_rows("transactions"),
                    "outputs": db.count_rows("outputs"),
                }
            finally:
                db.close()
        page_count, page_size = sqlite_page_info(db_path)
        processing_row = {
            "run_number": run_number,
            "system": system,
            "start_timestamp": start_iso,
            "end_timestamp": end_iso,
            "duration_seconds": float(metrics_row["total_seconds"]),
            "blocks_processed": metrics_row["blocks_processed"],
            "transactions_processed": metrics_row["transactions_processed"],
            "inputs_processed": metrics_row["inputs_processed"],
            "outputs_processed": metrics_row["outputs_processed"],
            "spends_processed": counts["spends_processed"],
            "blocks_per_second": metrics_row["blocks_processed"] / metrics_row["total_seconds"] if metrics_row["total_seconds"] else 0.0,
            "transactions_per_second": metrics_row["transactions_processed"] / metrics_row["total_seconds"] if metrics_row["total_seconds"] else 0.0,
            "outputs_per_second": metrics_row["outputs_processed"] / metrics_row["total_seconds"] if metrics_row["total_seconds"] else 0.0,
            "mean_block_time_ms": float(metrics_row["average_block_seconds"]) * 1000.0,
            "median_block_time_ms": float(metrics_row["p50_block_seconds"]) * 1000.0,
            "p95_block_time_ms": float(metrics_row["p95_block_seconds"]) * 1000.0,
            "p99_block_time_ms": float(metrics_row["p99_block_seconds"]) * 1000.0,
            "minimum_block_time_ms": 0.0,
            "maximum_block_time_ms": 0.0,
            "rpc_reads": metrics_row["rpc_reads"],
            "rpc_errors": metrics_row["error_count"],
            "retries": metrics_row["retry_count"],
            "sqlite_size_bytes": db_path.stat().st_size,
            "sqlite_pages": page_count,
            "sqlite_page_size": page_size,
            "peak_rss_kib": metrics_row["peak_rss_kib"],
            "mean_rss_kib": metrics_row["peak_rss_kib"],
            "process_cpu_seconds": process_cpu_seconds(pid),
            "approximate_cpu_percent": approximate_cpu_percent(pid),
            "system_load_start": load_start,
            "system_load_end": load_end,
            "available_memory_start_kib": available_start,
            "available_memory_end_kib": available_end,
            "temperature_start_c": temperature_start if temperature_start is not None else "",
            "temperature_end_c": temperature_end if temperature_end is not None else "",
            "validation_status": validation_status,
            "classification_time_seconds": metrics_row.get("classification_seconds", 0.0),
            "transition_persistence_time_seconds": metrics_row.get("transition_persistence_seconds", 0.0),
            "classification_time_per_output_us": float(metrics_row.get("classification_seconds_per_output", 0.0)) * 1_000_000.0,
            "MH_to_ML_transitions": metrics_row.get("mh_to_ml_count", 0),
            "MH_to_IM_transitions": metrics_row.get("mh_to_im_count", 0),
            "ML_to_IM_transitions": metrics_row.get("ml_to_im_count", 0),
            "same_block_spends": metrics_row.get("same_block_spend_count", 0),
            "final_MH": metrics_row.get("final_mh_count", 0),
            "final_ML": metrics_row.get("final_ml_count", 0),
            "final_IM": metrics_row.get("final_im_count", 0),
            "transition_rows": 0,
            "snapshot_rows": 0,
        }
        block_rows = [
            {
                "run_number": run_number,
                "system": system,
                "mean_block_time_ms": processing_row["mean_block_time_ms"],
                "median_block_time_ms": processing_row["median_block_time_ms"],
                "p95_block_time_ms": processing_row["p95_block_time_ms"],
                "p99_block_time_ms": processing_row["p99_block_time_ms"],
                "minimum_block_time_ms": processing_row["minimum_block_time_ms"],
                "maximum_block_time_ms": processing_row["maximum_block_time_ms"],
                "blocks_processed": processing_row["blocks_processed"],
            }
        ]
        if measured:
            for obs in lookup_obs:
                obs["run_number"] = run_number
                obs["system"] = system
        return {"processing": processing_row, "blocks": block_rows, "lookups": lookup_obs}

    def _command_for(self, system: str, db_path: Path) -> list[str]:
        if system == "baseline":
            return ["python3", str(PROJECT_ROOT / "scripts" / "run_baseline.py"), "--start-height", "0", "--end-height", "139", "--database", str(db_path), "--reset-db", "--leave-running"]
        return ["python3", str(PROJECT_ROOT / "scripts" / "run_mech_scal.py"), "--start-height", "0", "--end-height", "139", "--database", str(db_path), "--t-min", "24", "--reset-db", "--leave-running"]

    def _validate_baseline(self, db_path: Path, run_id: str) -> str:
        completed = subprocess.run(
            ["python3", str(PROJECT_ROOT / "scripts" / "validate_baseline.py"), "--database", str(db_path), "--manifest", str(PROJECT_ROOT / "data" / "workloads" / "small_seed_20260731" / "manifest.jsonl"), "--run-id", run_id],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
        result = json.loads(completed.stdout)
        return str(result["status"])

    def _validate_mech_scal(self, db_path: Path, run_id: str) -> str:
        completed = subprocess.run(
            ["python3", str(PROJECT_ROOT / "scripts" / "validate_mech_scal.py"), "--database", str(db_path), "--manifest", str(PROJECT_ROOT / "data" / "workloads" / "small_seed_20260731" / "manifest.jsonl"), "--run-id", run_id, "--t-min", "24"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
        result = json.loads(completed.stdout)
        return str(result["status"])

    def _ensure_regtest(self) -> None:
        try:
            info = self.rpc.cli_json("getblockchaininfo")
            if info["chain"] == "regtest":
                return
        except Exception:
            subprocess.run([str(START_SCRIPT)], cwd=PROJECT_ROOT, text=True, check=True, capture_output=True)
        info = self.rpc.cli_json("getblockchaininfo")
        if info["chain"] != "regtest":
            raise RuntimeError(f"unexpected chain: {info['chain']}")

    def _aggregate(self, raw_processing_runs: list[dict[str, object]], raw_lookup_observations: list[dict[str, object]], valid_pairs: int, invalid_pairs: int) -> dict[str, object]:
        baseline_runs = [row for row in raw_processing_runs if row["system"] == "baseline"]
        mech_runs = [row for row in raw_processing_runs if row["system"] == "mech_scal"]
        baseline_times = [float(row["duration_seconds"]) for row in baseline_runs]
        mech_times = [float(row["duration_seconds"]) for row in mech_runs]
        baseline_sizes = [float(row["sqlite_size_bytes"]) for row in baseline_runs]
        mech_sizes = [float(row["sqlite_size_bytes"]) for row in mech_runs]
        baseline_rss = [float(row["peak_rss_kib"]) for row in baseline_runs]
        mech_rss = [float(row["peak_rss_kib"]) for row in mech_runs]
        time_ci = bootstrap_paired_median_ci(baseline_times, mech_times, self.config.seed)
        size_ci = bootstrap_paired_median_ci(baseline_sizes, mech_sizes, self.config.seed)
        rss_ci = bootstrap_paired_median_ci(baseline_rss, mech_rss, self.config.seed)

        baseline_summary = summarize_numeric(baseline_times)
        mech_summary = summarize_numeric(mech_times)
        _, overhead_percent, _, overhead_summary = summarize_paired(baseline_times, mech_times)
        lookup_baseline_raw = [obs["latency_ns"] / 1_000_000.0 for obs in raw_lookup_observations if obs["system"] == "baseline"]
        lookup_mech_raw = [obs["latency_ns"] / 1_000_000.0 for obs in raw_lookup_observations if obs["system"] == "mech_scal"]
        lookup_baseline = self._lookup_run_medians_ms(raw_lookup_observations, "baseline")
        lookup_mech = self._lookup_run_medians_ms(raw_lookup_observations, "mech_scal")
        lookup_ci = bootstrap_paired_median_ci(
            lookup_baseline[: min(len(lookup_baseline), len(lookup_mech))],
            lookup_mech[: min(len(lookup_baseline), len(lookup_mech))],
            self.config.seed,
        )
        status = "PASS"
        if valid_pairs < 28:
            status = "FAIL"
        if invalid_pairs > 2:
            status = "FAIL"
        return {
            "status": status,
            "valid_pairs": valid_pairs,
            "invalid_pairs": invalid_pairs,
            "estimated_duration_seconds": self.estimate_duration_seconds(),
            "projected_storage_bytes": self.estimate_storage_bytes(),
            "baseline_time_summary": baseline_summary,
            "mech_scal_time_summary": mech_summary,
            "overhead_percent_summary": overhead_summary,
            "bootstrap_intervals": {
                "time_median_difference": time_ci,
                "sqlite_size_median_difference": size_ci,
                "peak_rss_median_difference": rss_ci,
                "lookup_median_difference_ms": lookup_ci,
            },
            "lookup_summary": {
                "baseline_raw_ms": summarize_numeric(lookup_baseline_raw),
                "mech_scal_raw_ms": summarize_numeric(lookup_mech_raw),
                "baseline_run_median_ms": summarize_numeric(lookup_baseline),
                "mech_scal_run_median_ms": summarize_numeric(lookup_mech),
            },
        }

    def _lookup_run_medians_ms(self, raw_lookup_observations: list[dict[str, object]], system: str) -> list[float]:
        grouped: dict[int, list[float]] = {}
        for obs in raw_lookup_observations:
            if obs["system"] != system:
                continue
            run_number = int(obs["run_number"])
            grouped.setdefault(run_number, []).append(float(obs["latency_ns"]) / 1_000_000.0)
        return [statistics.median(grouped[run_number]) for run_number in sorted(grouped)]

    def _write_outputs(self, raw_processing_runs: list[dict[str, object]], raw_block_metrics: list[dict[str, object]], raw_lookup_observations: list[dict[str, object]], summary: dict[str, object]) -> None:
        results_dir = self.config.results_dir
        write_csv(results_dir / "raw_processing_runs.csv", raw_processing_runs)
        write_csv(results_dir / "raw_block_metrics.csv", raw_block_metrics)
        write_csv(results_dir / "raw_lookup_observations.csv", raw_lookup_observations)

        baseline_runs = [row for row in raw_processing_runs if row["system"] == "baseline"]
        mech_runs = [row for row in raw_processing_runs if row["system"] == "mech_scal"]
        paired_rows = []
        for baseline_row, mech_row in zip(baseline_runs, mech_runs):
            overhead = 100.0 * (float(mech_row["duration_seconds"]) - float(baseline_row["duration_seconds"])) / float(baseline_row["duration_seconds"]) if float(baseline_row["duration_seconds"]) else 0.0
            paired_rows.append(
                {
                    "run_number": baseline_row["run_number"],
                    "baseline_duration_seconds": baseline_row["duration_seconds"],
                    "mech_scal_duration_seconds": mech_row["duration_seconds"],
                    "absolute_difference": float(mech_row["duration_seconds"]) - float(baseline_row["duration_seconds"]),
                    "overhead_percent": overhead,
                }
            )
        write_csv(results_dir / "paired_processing_comparison.csv", paired_rows)
        write_csv(results_dir / "processing_summary.csv", [{"metric": k, **{kk: vv for kk, vv in v.items()}} for k, v in [("baseline_time", summary["baseline_time_summary"]), ("mech_scal_time", summary["mech_scal_time_summary"]), ("overhead_percent", summary["overhead_percent_summary"])]] )

        lookup_latencies_baseline = [obs["latency_ns"] / 1_000_000.0 for obs in raw_lookup_observations if obs["system"] == "baseline"]
        lookup_latencies_mech = [obs["latency_ns"] / 1_000_000.0 for obs in raw_lookup_observations if obs["system"] == "mech_scal"]
        lookup_run_medians_baseline = self._lookup_run_medians_ms(raw_lookup_observations, "baseline")
        lookup_run_medians_mech = self._lookup_run_medians_ms(raw_lookup_observations, "mech_scal")
        write_csv(
            results_dir / "lookup_summary.csv",
            [
                {"system": "baseline", "sample_type": "raw", **summarize_numeric(lookup_latencies_baseline)},
                {"system": "mech_scal", "sample_type": "raw", **summarize_numeric(lookup_latencies_mech)},
                {"system": "baseline", "sample_type": "run_median", **summarize_numeric(lookup_run_medians_baseline)},
                {"system": "mech_scal", "sample_type": "run_median", **summarize_numeric(lookup_run_medians_mech)},
            ],
        )
        write_csv(results_dir / "resource_summary.csv", [{"system": "baseline", "median_peak_rss_kib": summarize_numeric([float(r["peak_rss_kib"]) for r in baseline_runs])["median"]}, {"system": "mech_scal", "median_peak_rss_kib": summarize_numeric([float(r["peak_rss_kib"]) for r in mech_runs])["median"]}])
        write_csv(results_dir / "storage_summary.csv", [{"system": "baseline", "median_sqlite_size_bytes": summarize_numeric([float(r["sqlite_size_bytes"]) for r in baseline_runs])["median"]}, {"system": "mech_scal", "median_sqlite_size_bytes": summarize_numeric([float(r["sqlite_size_bytes"]) for r in mech_runs])["median"]}])
        write_csv(results_dir / "bootstrap_intervals.csv", [{"metric": key, **value} for key, value in summary["bootstrap_intervals"].items()])

        outlier_rows = []
        all_overheads = [row["overhead_percent"] for row in paired_rows]
        mask = iqr_outlier_mask(all_overheads)
        for row, is_outlier in zip(paired_rows, mask):
            outlier_rows.append({**row, "is_potential_outlier": is_outlier})
        write_csv(results_dir / "outlier_report.csv", outlier_rows)

        write_json(results_dir / "phase6_summary.json", summary)
        self._write_latex(results_dir, summary)
        self._write_report(results_dir, summary)
        self._write_figures(results_dir, raw_processing_runs, paired_rows)

    def _write_latex(self, results_dir: Path, summary: dict[str, object]) -> None:
        tables_dir = results_dir / "tables"
        write_latex_table(tables_dir / "processing_comparison.tex", ["Metric", "Baseline", "Mech-Scal"], [["Median total time (s)", f"{summary['baseline_time_summary']['median']:.4f}", f"{summary['mech_scal_time_summary']['median']:.4f}"]])
        write_latex_table(tables_dir / "retrieval_comparison.tex", ["Metric", "Value"], [["Lookup median diff (ms)", f"{summary['bootstrap_intervals']['lookup_median_difference_ms']['median_difference']:.6f}"]])
        write_latex_table(tables_dir / "resource_comparison.tex", ["Metric", "Value"], [["Peak RSS diff CI low", f"{summary['bootstrap_intervals']['peak_rss_median_difference']['ci_low']:.4f}"]])
        write_latex_table(tables_dir / "storage_comparison.tex", ["Metric", "Value"], [["SQLite size diff CI low", f"{summary['bootstrap_intervals']['sqlite_size_median_difference']['ci_low']:.4f}"]])

    def _write_report(self, results_dir: Path, summary: dict[str, object]) -> None:
        lines = [
            "# Phase 6 Benchmark Report",
            "",
            "## Final Status",
            "",
            f"- {summary['status']}",
            "",
            "## Design",
            "",
            "- 2 warm-up runs per system, excluded from results.",
            "- 30 measured pairs with strict alternation: baseline then Mech-Scal.",
            "- Same heights, same workload, same T_min=24, same deterministic lookup order.",
            "- Warm-cache or uncontrolled-cache conditions; system caches were not cleared.",
            "",
            "## Aggregate Results",
            "",
            f"- Valid pairs: `{summary['valid_pairs']}`",
            f"- Invalid pairs: `{summary['invalid_pairs']}`",
            f"- Baseline median time (s): `{summary['baseline_time_summary']['median']}`",
            f"- Mech-Scal median time (s): `{summary['mech_scal_time_summary']['median']}`",
            f"- Median overhead (%): `{summary['overhead_percent_summary']['median']}`",
            "",
            "## Bootstrap Intervals",
            "",
        ]
        for key, value in summary["bootstrap_intervals"].items():
            lines.append(f"- {key}: median diff `{value['median_difference']}`, 95% CI [`{value['ci_low']}`, `{value['ci_high']}`]")
        lines.extend(
            [
                "",
                "## Limitations",
                "",
                "- Negative overhead is reported as an observed difference, not as automatic acceleration.",
                "- Lookup percentages should be read together with absolute latencies.",
                "- The small workload is experimental and not representative of production scale.",
            ]
        )
        (results_dir / "phase6_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    def _write_figures(self, results_dir: Path, raw_processing_runs: list[dict[str, object]], paired_rows: list[dict[str, object]]) -> None:
        figures_dir = results_dir / "figures"
        figures_dir.mkdir(parents=True, exist_ok=True)
        try:
            import matplotlib.pyplot as plt
        except Exception:
            return
        baseline_runs = [row for row in raw_processing_runs if row["system"] == "baseline"]
        mech_runs = [row for row in raw_processing_runs if row["system"] == "mech_scal"]
        x = [row["run_number"] for row in baseline_runs]
        plt.figure(figsize=(8, 4))
        plt.plot(x, [row["duration_seconds"] for row in baseline_runs], label="Baseline")
        plt.plot(x, [row["duration_seconds"] for row in mech_runs], label="Mech-Scal")
        plt.xlabel("Run number")
        plt.ylabel("Total time (s)")
        plt.legend()
        plt.tight_layout()
        plt.savefig(figures_dir / "total_time_per_run.png", dpi=300)
        plt.savefig(figures_dir / "total_time_per_run.pdf")
        plt.close()

        plt.figure(figsize=(8, 4))
        plt.plot([row["run_number"] for row in paired_rows], [row["overhead_percent"] for row in paired_rows])
        plt.xlabel("Run number")
        plt.ylabel("Overhead (%)")
        plt.tight_layout()
        plt.savefig(figures_dir / "overhead_percent_per_pair.png", dpi=300)
        plt.savefig(figures_dir / "overhead_percent_per_pair.pdf")
        plt.close()
