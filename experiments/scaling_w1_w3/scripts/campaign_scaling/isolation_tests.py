"""Offline regression tests for the rolling-cohort funding boundary."""
from __future__ import annotations

import tempfile
from decimal import Decimal
from pathlib import Path

from . import generate


def test_experimental_outputs_never_used_as_funding() -> None:
    with tempfile.TemporaryDirectory() as directory:
        old_out = generate.OUT
        generate.OUT = Path(directory)
        try:
            state = generate.IsolationState(final_height=218)
            state.add_funding({"txid": "funding-0", "vout": 0, "amount": "50"}, "initial_coinbase")
            for cohort_id in (1, 2, 3):
                selected = state.select_funding(Decimal("0.0901"), cohort_id)
                assert all(generate.outpoint(str(item["txid"]), int(item["vout"]))
                           not in state.by_outpoint for item in selected)
                state.remove_funding(selected)
                state.add_funding({"txid": f"change-{cohort_id}", "vout": 0, "amount": "49.9"},
                                  "cohort_change")
                record = {"creation_txid": f"experimental-{cohort_id}", "vout": 0}
                state.protect(record)
            assert state.funding_inputs.isdisjoint(state.by_outpoint)
            assert len(state.funding_inputs) == 3
        finally:
            generate.OUT = old_out


def test_incremental_manifest_survives_abort() -> None:
    with tempfile.TemporaryDirectory() as directory:
        old_out = generate.OUT
        generate.OUT = Path(directory)
        try:
            audit = generate.OUT / "audit"
            generate.append_event(audit / "planned_cohorts.jsonl", {
                "cohort_id": 1, "planned_creation_height": 102, "status": "PLANNED"})
            generate.append_event(audit / "realized_cohorts.jsonl", {
                "cohort_id": 1, "actual_creation_height": 102, "status": "REALIZED"})
            generate.append_event(audit / "validation_events.jsonl", {
                "event": "controlled_abort", "status": "FAIL"})
            assert (audit / "planned_cohorts.jsonl").read_text().count("\n") == 1
            assert (audit / "realized_cohorts.jsonl").read_text().count("\n") == 1
            assert (audit / "validation_events.jsonl").read_text().count("\n") == 1
            assert not (generate.OUT / "workload" / "manifest.jsonl").exists()
        finally:
            generate.OUT = old_out


def main() -> None:
    test_experimental_outputs_never_used_as_funding()
    test_incremental_manifest_survives_abort()
    print("PASS: funding isolation regression")
    print("PASS: incremental manifest abort persistence")


if __name__ == "__main__":
    main()
