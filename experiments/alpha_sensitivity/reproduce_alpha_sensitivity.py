#!/usr/bin/env python3
"""Recompute analytical alpha sensitivity from the canonical processed frame.

This is a modeled storage calculation, not a new physical-storage experiment.
"""

from __future__ import annotations

import csv
import math
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "results" / "final_paper" / "data"
FRAME_PATH = DATA / "cumulative_storage_growth_by_class_frame47_simplified.csv"
POLICY_PATH = DATA / "im_replication_factor_sensitivity.csv"
OUTPUT_PATH = DATA / "alpha_sensitivity.csv"
ALPHAS = tuple(Decimal(value) for value in ("0.50", "0.75", "1.00", "1.25", "1.50", "2.00"))
GIB = Decimal(2) ** 30


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def round_two(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def main() -> None:
    frame = read_rows(FRAME_PATH)
    final = [row for row in frame if row["block_height"] == "870429"]
    if len(final) != 1:
        raise SystemExit("Expected exactly one canonical row at block height 870429")

    policies = read_rows(POLICY_PATH)
    logarithmic = [row for row in policies if row["policy"] == "Logarithmic"]
    if len(logarithmic) != 1:
        raise SystemExit("Expected exactly one existing Logarithmic policy row")
    log_row = logarithmic[0]
    total_nodes = int(log_row["m"])
    im_layer_nodes = int(log_row["m_c"])
    expected_log_replicas = int(log_row["r_im"])
    if total_nodes != 18000 or im_layer_nodes != 6000 or expected_log_replicas != 13:
        raise SystemExit("Canonical Logarithmic policy inputs no longer match 18000/6000/13")

    mh = Decimal(final[0]["MH_bytes"]) / GIB
    ml = Decimal(final[0]["ML_bytes"]) / GIB
    im = Decimal(final[0]["IM_bytes"]) / GIB
    full_replication_gib = (mh + ml + im) * total_nodes

    rows: list[dict[str, str]] = []
    for alpha in ALPHAS:
        replicas = math.ceil(float(alpha) * math.log2(im_layer_nodes))
        replicated_gib = (mh + ml) * im_layer_nodes + im * replicas
        reduction = (Decimal(1) - replicated_gib / full_replication_gib) * Decimal(100)
        rows.append(
            {
                "alpha": str(alpha),
                "m_im": str(im_layer_nodes),
                "r_im": str(replicas),
                "replicated_storage_gib": str(replicated_gib),
                "replicated_storage_tib": str(replicated_gib / Decimal(1024)),
                "reduction_percent": str(reduction),
                "evidence_type": "analytical/model-derived",
            }
        )

    alpha_one = next(row for row in rows if row["alpha"] == "1.00")
    if int(alpha_one["r_im"]) != expected_log_replicas:
        raise SystemExit("alpha=1 does not reproduce the canonical Logarithmic replica count")
    if not math.isclose(
        float(alpha_one["replicated_storage_gib"]),
        float(log_row["replicated_storage_gib"]),
        rel_tol=0.0,
        abs_tol=1e-9,
    ):
        raise SystemExit("alpha=1 storage does not match the canonical Logarithmic policy")

    first, last = rows[0], rows[-1]
    reference_checks = (
        (round_two(Decimal(first["replicated_storage_tib"])), Decimal("242.55")),
        (round_two(Decimal(last["replicated_storage_tib"])), Decimal("252.42")),
        (round_two(Decimal(first["reduction_percent"])), Decimal("97.59")),
        (round_two(Decimal(last["reduction_percent"])), Decimal("97.49")),
    )
    if any(actual != expected for actual, expected in reference_checks):
        raise SystemExit(f"Computed alpha endpoints disagree with study reference: {reference_checks}")

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_PATH.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)

    print("alpha  r_IM  replicated TiB  reduction %")
    for row in rows:
        print(
            f"{row['alpha']:>5}  {row['r_im']:>4}  "
            f"{Decimal(row['replicated_storage_tib']):>14.6f}  "
            f"{Decimal(row['reduction_percent']):>11.6f}"
        )
    print(f"PASS: alpha=1 matches the existing Logarithmic policy; wrote {OUTPUT_PATH.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
