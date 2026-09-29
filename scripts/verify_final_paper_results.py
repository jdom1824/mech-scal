#!/usr/bin/env python3
"""Verify the bundled final experimental evidence without external dependencies.

This is an arithmetic and scope check over saved experimental artifacts.  It does
not read a blockchain database, download data, or claim a fresh full-chain run.
"""

from __future__ import annotations

import csv
import json
import math
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "results" / "final_paper" / "data"
REFERENCE = ROOT / "results" / "reference"


def fail(message: str) -> None:
    raise SystemExit(f"FAIL: {message}")


def load_csv(name: str) -> list[dict[str, str]]:
    path = DATA / name
    if not path.is_file():
        fail(f"missing artifact: {path.relative_to(ROOT)}")
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def load_json(name: str) -> dict:
    path = DATA / name
    if not path.is_file():
        fail(f"missing artifact: {path.relative_to(ROOT)}")
    return json.loads(path.read_text(encoding="utf-8"))


def load_reference_json(relative_path: str) -> dict:
    path = REFERENCE / relative_path
    if not path.is_file():
        fail(f"missing reference artifact: {path.relative_to(ROOT)}")
    return json.loads(path.read_text(encoding="utf-8"))


def csv_data_rows(relative_path: str) -> int:
    path = REFERENCE / relative_path
    if not path.is_file():
        fail(f"missing reference artifact: {path.relative_to(ROOT)}")
    with path.open(newline="", encoding="utf-8") as handle:
        return sum(1 for _ in csv.DictReader(handle))


def close(actual: float, expected: float, tolerance: float = 1e-10) -> bool:
    return math.isclose(actual, expected, rel_tol=tolerance, abs_tol=tolerance)


def rounded(value: Decimal, places: str = "0.01") -> Decimal:
    return value.quantize(Decimal(places), rounding=ROUND_HALF_UP)


def main() -> None:
    storage = load_csv("cumulative_storage_growth_by_class_frame47_simplified.csv")
    target = next((row for row in storage if row["block_height"] == "870429"), None)
    if target is None:
        fail("canonical storage series has no row for block 870429")
    for key, expected in {
        "IM_bytes": Decimal("571612422059.7296142578"),
        "ML_bytes": Decimal("37565287692.6002273560"),
        "MH_bytes": Decimal("6215021015.1399650574"),
    }.items():
        if Decimal(target[key]) != expected:
            fail(f"{key} at block 870429 changed: {target[key]} != {expected}")

    metadata = load_json("final_frame_metadata.json")
    if metadata.get("target_height") != 870429 or metadata.get("rows") != 870430:
        fail("frame metadata does not identify the 870429 / 870430-row frame")

    manifest = load_csv("final_selection_manifest.csv")
    attribution = load_csv("final_attribution_abc.csv")
    if len(manifest) != 17000:
        fail(f"selection manifest has {len(manifest)} rows, expected 17000")
    if len(attribution) != 46962:
        fail(f"attribution artifact has {len(attribution)} rows, expected 46962")
    weights = {row["ordinal"]: float(row["weight"]) for row in manifest}
    if len(weights) != len(manifest):
        fail("selection manifest contains duplicate ordinals")
    if any(row["ordinal"] not in weights for row in attribution):
        fail("attribution contains an ordinal absent from the selected manifest")

    class_counts: dict[str, int] = {}
    for row in attribution:
        class_counts[row["class"]] = class_counts.get(row["class"], 0) + 1
    expected_counts = {"IM": 42457, "ML": 2496, "UNASSIGNED": 1906, "MH": 103}
    if class_counts != expected_counts:
        fail(f"class counts changed: {class_counts} != {expected_counts}")

    method_shares: dict[str, float] = {}
    for method in ("A", "B", "C"):
        totals = {"IM": 0.0, "ML": 0.0, "MH": 0.0}
        for row in attribution:
            if row["class"] in totals:
                totals[row["class"]] += float(row[f"bytes_{method}"]) * weights[row["ordinal"]]
        denominator = sum(totals.values())
        method_shares[method] = totals["IM"] / denominator
    expected_shares = {
        "A": 0.9232517091203335,
        "B": 0.9377575443094679,
        "C": 0.9238476047777403,
    }
    for method, expected in expected_shares.items():
        if not close(method_shares[method], expected):
            fail(f"method {method} IM share changed: {method_shares[method]} != {expected}")

    validation = load_json("independent_artifact_validation.json")
    if validation.get("status") != "PASS":
        fail("independent artifact validation is not PASS")
    if not validation.get("independent_weighted_totals_and_ratios"):
        fail("independent weighted-total recomputation is not marked true")
    weighted = load_json("final_weighted_estimates.json")
    if weighted.get("verdict") != "ID26-FINAL-INFERENCE-UNSTABLE":
        fail("ID26 inference limitation is missing or has been changed")
    if weighted.get("precision_target_met") is not False:
        fail("ID26 precision_target_met must remain false")

    # Table 5 arithmetic from the canonical class bytes.  These are network
    # storage scenarios, not a claim that all 18,000 nodes were deployed.
    gib = Decimal(2) ** 30
    im = Decimal(target["IM_bytes"]) / gib
    ml = Decimal(target["ML_bytes"]) / gib
    mh = Decimal(target["MH_bytes"]) / gib
    classified = im + ml + mh
    non_im = ml + mh
    full = classified * Decimal(18000)
    class_partition = classified * Decimal(6000)
    reduced_im = non_im * Decimal(18000) + im * Decimal(13)
    complete = non_im * Decimal(6000) + im * Decimal(13)
    table5 = {
        "Full replication": (full, Decimal("10316324.56"), Decimal("0.00")),
        "Class partitioning only": (
            class_partition,
            Decimal("3438774.85"),
            Decimal("66.67"),
        ),
        "Reduced IM replication only": (
            reduced_im,
            Decimal("740845.24"),
            Decimal("92.82"),
        ),
        "Complete Mech-Scal": (
            complete,
            Decimal("251562.16"),
            Decimal("97.56"),
        ),
    }
    for name, (value, expected_storage, expected_reduction) in table5.items():
        if rounded(value) != expected_storage:
            fail(
                f"Table 5 {name} storage changed: "
                f"{rounded(value)} != {expected_storage} GiB"
            )
        reduction = Decimal("0") if name == "Full replication" else (
            Decimal("1") - value / full
        ) * Decimal("100")
        if rounded(reduction) != expected_reduction:
            fail(
                f"Table 5 {name} reduction changed: "
                f"{rounded(reduction)} != {expected_reduction}%"
            )

    policies = load_csv("im_replication_factor_sensitivity.csv")
    expected_policy = {
        "Fixed-3": (Decimal("240.47"), Decimal("97.61")),
        "Fixed-5": (Decimal("241.51"), Decimal("97.60")),
        "Logarithmic": (Decimal("245.67"), Decimal("97.56")),
        "Proportional-1%": (Decimal("270.10"), Decimal("97.32")),
        "Square-root": (Decimal("279.46"), Decimal("97.23")),
        "Full IM": (Decimal("3358.18"), Decimal("66.67")),
    }
    if {row["policy"] for row in policies} != set(expected_policy):
        fail("replication-policy sensitivity set changed")
    for row in policies:
        expected_tib, expected_reduction = expected_policy[row["policy"]]
        if rounded(Decimal(row["replicated_storage_tib"])) != expected_tib:
            fail(f"policy {row['policy']} TiB value changed")
        if rounded(Decimal(row["reduction_percent"])) != expected_reduction:
            fail(f"policy {row['policy']} reduction changed")

    alpha_rows = load_csv("alpha_sensitivity.csv")
    alpha_values = {Decimal(row["alpha"]) for row in alpha_rows}
    expected_alpha_values = {
        Decimal(value) for value in ("0.50", "0.75", "1.00", "1.25", "1.50", "2.00")
    }
    if alpha_values != expected_alpha_values:
        fail("alpha sensitivity grid changed")
    logarithmic = next(row for row in policies if row["policy"] == "Logarithmic")
    for row in alpha_rows:
        alpha = Decimal(row["alpha"])
        replicas = math.ceil(float(alpha) * math.log2(6000))
        if int(row["m_im"]) != 6000 or int(row["r_im"]) != replicas:
            fail(f"alpha={alpha} replication factor is inconsistent")
        expected_storage = non_im * Decimal(6000) + im * Decimal(replicas)
        if Decimal(row["replicated_storage_gib"]) != expected_storage:
            fail(f"alpha={alpha} modeled storage is inconsistent with canonical class bytes")
        expected_reduction = (Decimal(1) - expected_storage / full) * Decimal(100)
        if Decimal(row["reduction_percent"]) != expected_reduction:
            fail(f"alpha={alpha} modeled reduction is inconsistent")
    alpha_one = next(row for row in alpha_rows if Decimal(row["alpha"]) == Decimal("1.00"))
    if int(alpha_one["r_im"]) != int(logarithmic["r_im"]):
        fail("alpha=1 does not match the existing Logarithmic policy")
    if abs(
        Decimal(alpha_one["replicated_storage_gib"])
        - Decimal(logarithmic["replicated_storage_gib"])
    ) > Decimal("1e-20"):
        fail("alpha=1 storage does not match the existing Logarithmic policy")

    deff_rows = load_csv("d_eff_analytical_sensitivity.csv")
    expected_deff_pairs = {
        (d_eff, q_d)
        for d_eff in (13, 7, 4, 2, 1)
        for q_d in (Decimal("0.01"), Decimal("0.05"), Decimal("0.10"))
    }
    actual_deff_pairs = {
        (int(row["d_eff"]), Decimal(row["q_d"])) for row in deff_rows
    }
    if actual_deff_pairs != expected_deff_pairs:
        fail("d_eff analytical sensitivity grid changed")
    for row in deff_rows:
        d_eff, q_d = int(row["d_eff"]), Decimal(row["q_d"])
        if Decimal(row["p_loss"]) != q_d**d_eff:
            fail(f"d_eff={d_eff}, q_D={q_d}: P_loss does not equal q_D**d_eff")
        if row["evidence_type"] != "analytical sensitivity; illustrative q_D":
            fail("d_eff result is missing its analytical/illustrative evidence label")

    phase6 = load_reference_json("phase6/phase6_summary.json")
    if (phase6.get("status"), phase6.get("valid_pairs"), phase6.get("invalid_pairs")) != (
        "PASS",
        30,
        0,
    ):
        fail("saved Phase 6 paired-run status or pair counts changed")
    phase6_expected = {
        "baseline_time_summary.median": 3.447364944004221,
        "mech_scal_time_summary.median": 3.8093742529890733,
        "overhead_percent_summary.median": 10.730663481382233,
        "bootstrap_intervals.time_median_difference.median_difference": 0.3862574719969416,
    }
    for dotted_key, expected in phase6_expected.items():
        value: object = phase6
        for key in dotted_key.split("."):
            if not isinstance(value, dict) or key not in value:
                fail(f"Phase 6 summary is missing {dotted_key}")
            value = value[key]
        if not close(float(value), expected):
            fail(f"Phase 6 {dotted_key} changed: {value} != {expected}")
    for filename, expected_rows in {
        "phase6/raw_processing_runs.csv": 60,
        "phase6/raw_block_metrics.csv": 60,
        "phase6/raw_lookup_observations.csv": 427500,
    }.items():
        rows = csv_data_rows(filename)
        if rows != expected_rows:
            fail(f"Phase 6 {filename} has {rows} rows, expected {expected_rows}")

    phase7 = load_reference_json("phase7/phase7_summary.json")
    if phase7.get("status") != "PASS":
        fail("saved Phase 7 summary status is not PASS")
    for summary_key, filename, expected_rows in (
        ("retrieval_observations", "phase7/raw_retrieval_observations.csv", 495900),
        ("recovery_observations", "phase7/raw_recovery_observations.csv", 630762),
    ):
        if phase7.get(summary_key) != expected_rows:
            fail(f"Phase 7 summary {summary_key} changed")
        rows = csv_data_rows(filename)
        if rows != expected_rows:
            fail(f"Phase 7 {filename} has {rows} rows, expected {expected_rows}")
    if phase7.get("maximum_tolerated_failures") != {
        "Fixed-3": 2,
        "Fixed-5": 4,
        "Logarithmic": 12,
    }:
        fail("Phase 7 maximum tolerated failure counts changed")

    tmin = load_csv("tmin_sensitivity_summary.csv")
    if {int(row["tmin"]) for row in tmin} != {144, 1008, 2016, 4032, 8064, 13140}:
        fail("Tmin sensitivity set changed")
    if {int(row["tmax"]) for row in tmin} != {26280}:
        fail("Tmin sensitivity does not use Tmax=26280 throughout")
    tmax = load_csv("tmax_sensitivity_summary.csv")
    if {int(float(row["tmax_blocks"])) for row in tmax} != {13140, 26280, 52560}:
        fail("Tmax sensitivity set changed")
    full_blocks = load_csv("full_blocks_50000_summary.csv")
    if {int(float(row["tmax_blocks"])) for row in full_blocks} != {13140, 26280, 52560}:
        fail("50,000-full-block stress set changed")
    if any(int(float(row["simulated_points"])) != 870430 for row in full_blocks):
        fail("50,000-full-block stress artifact does not cover the 870430-point frame")

    print("PASS: final experimental evidence is internally consistent")
    print("  block 870429 class bytes and shares: verified")
    print("  attribution methods A/B/C: 17,000 tx / 46,962 outputs verified")
    print("  Table 5 storage arithmetic and policy sensitivity: verified")
    print("  alpha sensitivity from canonical class bytes: verified")
    print("  d_eff analytical sensitivity: verified; illustrative q_D only")
    print("  Tmin/Tmax/full-block sensitivity artifacts: verified")
    print("  Phase 6 saved paired benchmark summary/raw row counts: verified")
    print("  Phase 7 saved fault/recovery summary/raw row counts: verified")
    print("  ID26 limitation preserved: inference unstable; precision target not met")


if __name__ == "__main__":
    main()
