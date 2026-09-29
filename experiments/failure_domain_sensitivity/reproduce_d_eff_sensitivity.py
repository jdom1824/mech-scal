#!/usr/bin/env python3
"""Generate the analytical sensitivity table P_loss = q_D ** d_eff.

The q_D values are illustrative, not calibrated by the prototype. The prototype
does not measure independent physical failure domains or d_eff.
"""

from __future__ import annotations

import csv
from decimal import Decimal
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
OUTPUT_PATH = ROOT / "results" / "final_paper" / "data" / "d_eff_analytical_sensitivity.csv"
D_EFF_VALUES = (13, 7, 4, 2, 1)
Q_D_VALUES = (Decimal("0.01"), Decimal("0.05"), Decimal("0.10"))


def main() -> None:
    rows = [
        {
            "d_eff": d_eff,
            "q_d": str(q_d),
            "p_loss": str(q_d**d_eff),
            "evidence_type": "analytical sensitivity; illustrative q_D",
        }
        for d_eff in D_EFF_VALUES
        for q_d in Q_D_VALUES
    ]

    expected = {
        (13, Decimal("0.01")): Decimal("1e-26"),
        (13, Decimal("0.05")): Decimal("1.220703125e-17"),
        (13, Decimal("0.10")): Decimal("1e-13"),
        (7, Decimal("0.01")): Decimal("1e-14"),
        (7, Decimal("0.05")): Decimal("7.8125e-10"),
        (7, Decimal("0.10")): Decimal("1e-7"),
        (4, Decimal("0.01")): Decimal("1e-8"),
        (4, Decimal("0.05")): Decimal("6.25e-6"),
        (4, Decimal("0.10")): Decimal("1e-4"),
        (2, Decimal("0.01")): Decimal("1e-4"),
        (2, Decimal("0.05")): Decimal("2.5e-3"),
        (2, Decimal("0.10")): Decimal("1e-2"),
        (1, Decimal("0.01")): Decimal("1e-2"),
        (1, Decimal("0.05")): Decimal("5e-2"),
        (1, Decimal("0.10")): Decimal("1e-1"),
    }
    computed = {(int(row["d_eff"]), Decimal(row["q_d"])): Decimal(row["p_loss"]) for row in rows}
    if computed != expected:
        raise SystemExit("Analytical values do not match the stated q_D ** d_eff table")

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_PATH.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)

    print("d_eff  q_D  P_loss=q_D**d_eff")
    for row in rows:
        print(f"{row['d_eff']:>5}  {row['q_d']:>4}  {row['p_loss']}")
    print(f"PASS: {len(rows)} analytical rows verified; wrote {OUTPUT_PATH.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
