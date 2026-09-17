"""Generate an isolated rolling-cohort workload with explicit coin control.

This module is campaign-only code. It never uses wallet coin selection for a
cohort-creation transaction: every funding input is selected from the explicit
funding pool and every experimental spend is constructed from explicit
experimental outpoints.
"""
from __future__ import annotations

import json
import os
import random
import time
from decimal import Decimal
from pathlib import Path

from .common import CONFIG, HERE, OUT, WORK, csvfile, rpc, save, sha

ATTEMPT_ID = os.environ.get("CAMPAIGN_ATTEMPT_ID", "pilot_w1_retry_01")
WALLET = os.environ.get("CAMPAIGN_WALLET", "w1_retry_01")
FEE_BTC = Decimal(str(CONFIG["spend_fee_btc"]))


def outpoint(txid: str, vout: int) -> str:
    return f"{txid}:{vout}"


def atomic_save(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def append_event(path: Path, event: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


class IsolationState:
    def __init__(self, final_height: int) -> None:
        self.final_height = final_height
        self.funding_utxos: dict[str, dict[str, object]] = {}
        self.protected_experimental_utxos: set[str] = set()
        self.scheduled_spend_utxos: dict[str, int] = {}
        self.spent_experimental_utxos: set[str] = set()
        self.records: list[dict[str, object]] = []
        self.by_outpoint: dict[str, dict[str, object]] = {}
        self.cohorts: dict[int, dict[str, object]] = {}
        self.funding_inputs: set[str] = set()
        self.unexpected_spends = 0

    def log_validation(self, event: str, **details: object) -> None:
        append_event(OUT / "audit" / "validation_events.jsonl", {
            "event": event, "status": "PASS", "height": details.pop("height", None), **details
        })

    def add_funding(self, item: dict[str, object], source: str) -> None:
        key = outpoint(str(item["txid"]), int(item["vout"]))
        if key in self.protected_experimental_utxos:
            raise RuntimeError("experimental outpoint entered funding pool: " + key)
        self.funding_utxos[key] = {
            "txid": str(item["txid"]), "vout": int(item["vout"]),
            "amount": str(item["amount"]), "source": source,
        }

    def select_funding(self, amount: Decimal, cohort_id: int) -> list[dict[str, object]]:
        selected: list[dict[str, object]] = []
        total = Decimal("0")
        for key in sorted(self.funding_utxos):
            if key in self.protected_experimental_utxos:
                raise RuntimeError("protected experimental outpoint in funding pool: " + key)
            selected.append(self.funding_utxos[key])
            total += Decimal(str(self.funding_utxos[key]["amount"]))
            if total >= amount + FEE_BTC:
                break
        if total < amount + FEE_BTC:
            raise RuntimeError(f"insufficient explicit funding for cohort {cohort_id}")
        keys = {outpoint(str(item["txid"]), int(item["vout"])) for item in selected}
        if keys & self.protected_experimental_utxos:
            raise RuntimeError("funding isolation violation before broadcast")
        self.funding_inputs.update(keys)
        self.log_validation("funding_inputs_checked", cohort_id=cohort_id,
                            funding_inputs=sorted(keys), protected_intersection=[])
        return selected

    def remove_funding(self, selected: list[dict[str, object]]) -> None:
        for item in selected:
            self.funding_utxos.pop(outpoint(str(item["txid"]), int(item["vout"])), None)

    def protect(self, record: dict[str, object]) -> None:
        key = outpoint(str(record["creation_txid"]), int(record["vout"]))
        if key in self.funding_inputs:
            raise RuntimeError("experimental outpoint overlaps funding input: " + key)
        self.protected_experimental_utxos.add(key)
        self.by_outpoint[key] = record

    def schedule(self, record: dict[str, object], height: int) -> None:
        key = outpoint(str(record["creation_txid"]), int(record["vout"]))
        if key not in self.protected_experimental_utxos:
            raise RuntimeError("scheduled spend is not a protected experimental outpoint")
        self.scheduled_spend_utxos[key] = height
        append_event(OUT / "audit" / "scheduled_spends.jsonl", {
            "outpoint": key, "cohort_id": record["cohort_id"],
            "scheduled_age_blocks": record["expected_spend_age_blocks"],
            "scheduled_height": height,
        })

    def mark_spent(self, record: dict[str, object], txid: str, height: int, blockhash: str) -> None:
        key = outpoint(str(record["creation_txid"]), int(record["vout"]))
        expected = self.scheduled_spend_utxos.get(key)
        if expected != height:
            raise RuntimeError(f"scheduled spend height mismatch for {key}: {height} != {expected}")
        record.update(spend_txid=txid, spend_height=height, spend_blockhash=blockhash,
                     is_spent=True, actual_spend_age_blocks=height - int(record["creation_height"]))
        self.protected_experimental_utxos.remove(key)
        self.spent_experimental_utxos.add(key)
        append_event(OUT / "audit" / "realized_spends.jsonl", {
            "outpoint": key, "cohort_id": record["cohort_id"],
            "spending_txid": txid, "actual_spend_height": height,
            "realized_age_blocks": record["actual_spend_age_blocks"],
        })

    def post_block_validation(self, height: int) -> None:
        for key in sorted(self.protected_experimental_utxos):
            record = self.by_outpoint[key]
            txout = rpc("gettxout", str(record["creation_txid"]), int(record["vout"]), True)
            expected = self.scheduled_spend_utxos.get(key)
            if txout is None:
                self.unexpected_spends += 1
                raise RuntimeError(f"unexpected experimental spend at height {height}: {key}")
            if expected is not None and expected <= height:
                self.unexpected_spends += 1
                raise RuntimeError(f"scheduled spend missing at height {height}: {key}")
        self.log_validation("post_block_experimental_utxo_check", height=height,
                            protected_unspent=len(self.protected_experimental_utxos),
                            spent_experimental=len(self.spent_experimental_utxos))


def create_raw_spend(records: list[dict[str, object]], destination: str) -> str:
    total = sum(Decimal(str(record["value_btc"])) for record in records)
    if total <= FEE_BTC:
        raise RuntimeError("experimental spend total is too small for fee")
    raw_inputs = [{"txid": str(record["creation_txid"]), "vout": int(record["vout"])} for record in records]
    raw_outputs = {destination: str((total - FEE_BTC).quantize(Decimal("0.00000001")))}
    raw = rpc("createrawtransaction", raw_inputs, raw_outputs)
    signed = rpc("signrawtransactionwithwallet", raw, wallet=WALLET)
    if not signed.get("complete"):
        raise RuntimeError("experimental raw transaction signing did not complete")
    return str(rpc("sendrawtransaction", str(signed["hex"])))


def prepare_spend(state: IsolationState, records: list[dict[str, object]], height: int,
                  destination: str, unlock: bool = True) -> str:
    keys = [outpoint(str(r["creation_txid"]), int(r["vout"])) for r in records]
    if not set(keys) <= state.protected_experimental_utxos:
        raise RuntimeError("spend input is not in protected experimental pool")
    if unlock:
        rpc("lockunspent", True, [{"txid": str(r["creation_txid"]), "vout": int(r["vout"])} for r in records], wallet=WALLET)
        state.log_validation("scheduled_inputs_unlocked", height=height, outpoints=keys)
    else:
        state.log_validation("same_block_inputs_not_locked", height=height, outpoints=keys)
    txid = create_raw_spend(records, destination)
    state.log_validation("experimental_spend_broadcast", height=height,
                         outpoints=keys, spending_txid=txid)
    return txid


def cohort_plan(cohort_id: int, creation_height: int) -> dict[str, object]:
    return {
        "cohort_id": cohort_id,
        "planned_creation_height": creation_height,
        "seed": CONFIG["seed"],
        "profile": "rolling_cohort",
        "groups": [
            {"group": group, "count": count, "spend_age_blocks": age,
             "intended_unspent_count": count if age is None else 0}
            for group, count, age in CONFIG["groups"]
        ],
        "intended_output_count": 75,
        "intended_unspent_count": 20,
    }


def prepare_cohort(state: IsolationState, cohort_id: int, creation_height: int,
                   funding_address: str, spend_destination: str) -> dict[str, object]:
    plan = cohort_plan(cohort_id, creation_height)
    append_event(OUT / "audit" / "planned_cohorts.jsonl", plan)
    groups: list[dict[str, object]] = []
    payment_map: dict[str, str] = {}
    for group, count, age in CONFIG["groups"]:
        for ordinal in range(count):
            address = str(rpc("getnewaddress", f"cohort-{cohort_id}-{group}-{ordinal}", "bech32", wallet=WALLET))
            record = {
                "run_id": ATTEMPT_ID, "profile": "rolling_cohort", "seed": CONFIG["seed"],
                "cohort_id": cohort_id, "logical_output_id": f"cohort-{cohort_id:03d}/{group}/{ordinal:03d}",
                "group": group, "address": address, "value_btc": CONFIG["value_btc"],
                "creation_height": creation_height, "creation_txid": None, "vout": None,
                "creation_blockhash": None, "expected_spend_age_blocks": age,
                "intended_spend_height": None if age is None else creation_height + age,
                "spend_txid": None, "spend_height": None, "spend_blockhash": None,
                "is_spent": False, "actual_spend_age_blocks": None,
                "final_chain_height": state.final_height,
            }
            groups.append(record)
            payment_map[address] = str(CONFIG["value_btc"])

    selected = state.select_funding(sum(Decimal(v) for v in payment_map.values()), cohort_id)
    funding_total = sum(Decimal(str(item["amount"])) for item in selected)
    change = funding_total - sum(Decimal(v) for v in payment_map.values()) - FEE_BTC
    funding_inputs = [{"txid": str(item["txid"]), "vout": int(item["vout"])} for item in selected]
    outputs = dict(payment_map)
    outputs[funding_address] = str(change.quantize(Decimal("0.00000001")))
    raw = rpc("createrawtransaction", funding_inputs, outputs)
    signed = rpc("signrawtransactionwithwallet", raw, wallet=WALLET)
    if not signed.get("complete"):
        raise RuntimeError("funding transaction signing did not complete")
    txid = str(rpc("sendrawtransaction", str(signed["hex"])))
    state.remove_funding(selected)
    tx = rpc("getrawtransaction", txid, True)
    vouts = {str(v["scriptPubKey"].get("address")): int(v["n"]) for v in tx["vout"]}
    for record in groups:
        record["creation_txid"] = txid
        record["vout"] = vouts[str(record["address"])]
        state.protect(record)
    change_vout = vouts[funding_address]
    append_event(OUT / "audit" / "funding_transactions.jsonl", {
        "cohort_id": cohort_id, "transaction_type": "cohort_creation",
        "txid": txid, "inputs": funding_inputs, "change_vout": change_vout,
        "experimental_output_count": len(groups), "protected_intersection": [],
    })
    same_block = [r for r in groups if r["expected_spend_age_blocks"] == 0]
    same_txid = None
    if same_block:
        for record in same_block:
            state.schedule(record, creation_height)
        same_txid = prepare_spend(state, same_block, creation_height, spend_destination, unlock=False)
    return {"plan": plan, "records": groups, "parent_txid": txid,
            "change_vout": change_vout, "same_block_records": same_block,
            "same_block_txid": same_txid}


def confirm_cohort(state: IsolationState, context: dict[str, object], height: int,
                   blockhash: str, funding_address: str) -> None:
    records = context["records"]
    parent_txid = str(context["parent_txid"])
    parent = next(tx for tx in rpc("getblock", blockhash, 2)["tx"] if tx["txid"] == parent_txid)
    actual_height = height
    if actual_height != height:
        raise RuntimeError(f"cohort creation height mismatch: {actual_height} != {height}")
    for record in records:
        record["creation_blockhash"] = blockhash
        state.records.append(record)
        append_event(OUT / "audit" / "experimental_outputs.jsonl", record.copy())
    to_lock = [r for r in records if r not in context["same_block_records"]]
    if to_lock:
        rpc("lockunspent", False,
            [{"txid": str(r["creation_txid"]), "vout": int(r["vout"])} for r in to_lock], wallet=WALLET)
    state.log_validation("experimental_outputs_locked", height=height,
                         cohort_id=context["plan"]["cohort_id"],
                         protected_outputs=len(to_lock))
    change_vout = int(context["change_vout"])
    change_value = next(v["value"] for v in parent["vout"] if int(v["n"]) == change_vout)
    state.add_funding({"txid": parent_txid, "vout": change_vout, "amount": str(change_value)}, "cohort_change")
    append_event(OUT / "audit" / "realized_cohorts.jsonl", {
        "cohort_id": context["plan"]["cohort_id"], "parent_txid": parent_txid,
        "actual_creation_height": height, "creation_blockhash": blockhash,
        "experimental_outpoints": [outpoint(str(r["creation_txid"]), int(r["vout"])) for r in records],
        "values_btc": [r["value_btc"] for r in records],
    })
    state.log_validation("cohort_creation_confirmed", height=height,
                         cohort_id=context["plan"]["cohort_id"],
                         experimental_outputs=len(records))


def realize_group(state: IsolationState, records: list[dict[str, object]], txid: str,
                  height: int, blockhash: str) -> None:
    for record in records:
        state.mark_spent(record, txid, height, blockhash)


def write_chain_evidence(final_height: int) -> list[str]:
    hashes: list[str] = []
    with (WORK / "blocks.jsonl").open("x", encoding="utf-8") as handle:
        for height in range(final_height + 1):
            blockhash = str(rpc("getblockhash", height))
            block = rpc("getblock", blockhash, 2)
            hashes.append(blockhash)
            handle.write(json.dumps(block, sort_keys=True) + "\n")
    save(WORK / "block_hashes.json", hashes)
    save(WORK / "block_heights.json", list(range(len(hashes))))
    return hashes


def validate_chain(hashes: list[str]) -> dict[str, int]:
    outputs: dict[str, tuple[int, str]] = {}
    spends: dict[str, tuple[str, int, str]] = {}
    transactions: set[str] = set()
    previous = None
    same_block_spends = 0
    with (WORK / "blocks.jsonl").open(encoding="utf-8") as handle:
        for height, line in enumerate(handle):
            block = json.loads(line)
            assert block["height"] == height and block["hash"] == hashes[height]
            if previous is not None:
                assert block["previousblockhash"] == previous
            previous = block["hash"]
            for tx in block["tx"]:
                txid = str(tx["txid"])
                assert txid not in transactions
                transactions.add(txid)
                coinbase = "coinbase" in tx["vin"][0]
                for value in tx["vout"]:
                    key = outpoint(txid, int(value["n"]))
                    assert key not in outputs
                    outputs[key] = (height, block["hash"])
                if not coinbase:
                    for vin in tx["vin"]:
                        key = outpoint(str(vin["txid"]), int(vin["vout"]))
                        assert key in outputs, "orphan spend: " + key
                        assert key not in spends, "double spend: " + key
                        spends[key] = (txid, height, block["hash"])
                        if outputs[key][0] == height:
                            same_block_spends += 1
    assert len(hashes) == height + 1
    return {"blocks": len(hashes), "transactions": len(transactions),
            "outputs": len(outputs), "spends": len(spends),
            "unspent": len(outputs) - len(spends), "same_block_spends": same_block_spends}


def validate_final(state: IsolationState, hashes: list[str]) -> dict[str, object]:
    assert len(hashes) == state.final_height + 1
    assert state.unexpected_spends == 0
    assert not (state.funding_inputs & set(state.by_outpoint))
    chain = validate_chain(hashes)
    with (WORK / "blocks.jsonl").open(encoding="utf-8") as handle:
        chain_outputs: dict[str, tuple[int, str]] = {}
        chain_spends: dict[str, tuple[str, int, str]] = {}
        for line in handle:
            block = json.loads(line)
            for tx in block["tx"]:
                for value in tx["vout"]:
                    chain_outputs[outpoint(str(tx["txid"]), int(value["n"]))] = (int(block["height"]), str(block["hash"]))
                if "coinbase" not in tx["vin"][0]:
                    for vin in tx["vin"]:
                        key = outpoint(str(vin["txid"]), int(vin["vout"]))
                        chain_spends[key] = (str(tx["txid"]), int(block["height"]), str(block["hash"]))
    for key, record in state.by_outpoint.items():
        assert key in chain_outputs
        assert chain_outputs[key][0] == int(record["creation_height"])
        if record["is_spent"]:
            assert key in chain_spends
            assert chain_spends[key][0] == record["spend_txid"]
            assert chain_spends[key][1] == record["spend_height"]
        else:
            assert key not in chain_spends
    cohorts = []
    for cohort_id in sorted(state.cohorts):
        records = state.cohorts[cohort_id]["records"]
        intended = [r for r in records if r["expected_spend_age_blocks"] is not None]
        realized = [r for r in intended if r["is_spent"]]
        unspent = [r for r in records if r["expected_spend_age_blocks"] is None]
        assert len(records) == 75 and len(intended) == 55 and len(unspent) == 20
        assert all(r["is_spent"] for r in intended if int(r["intended_spend_height"]) <= state.final_height)
        assert all(not r["is_spent"] for r in intended if int(r["intended_spend_height"]) > state.final_height)
        assert all(not r["is_spent"] for r in unspent)
        cohorts.append({"cohort_id": cohort_id, "experimental_outputs": len(records),
                        "scheduled_spends": len(intended), "realized_scheduled_spends": len(realized),
                        "unexpected_spends": 0, "protected_unspent": len(unspent) + len(intended) - len(realized),
                        "experimental_inputs_used_for_funding": 0})
    result = {
        "status": "PASS", "attempt": ATTEMPT_ID, "parent_attempt": "pilot_w1",
        "reason_for_retry": "Funding isolation defect: automatic coin selection spent protected experimental outputs.",
        "blocks": state.final_height + 1, "height_start": 0, "height_end": state.final_height,
        "chain_counts": chain,
        "cohorts": len(cohorts), "outputs": len(state.records),
        "scheduled_spends": sum(c["scheduled_spends"] for c in cohorts),
        "realized_scheduled_spends": sum(c["realized_scheduled_spends"] for c in cohorts),
        "censored_spends": sum(c["scheduled_spends"] - c["realized_scheduled_spends"] for c in cohorts),
        "experimental_outputs_used_for_funding": 0, "unexpected_experimental_spends": 0,
        "intended_unspent_incorrectly_spent": 0, "duplicate_outpoints": 0,
        "orphan_spends": 0, "double_spends": 0, "cohort_validation": cohorts,
        "incremental_audit_artifacts_complete": True,
    }
    csvfile(WORK / "cohort_validation.csv", cohorts)
    return result


def generate() -> dict[str, object]:
    cohort_limit = int(os.environ.get("CAMPAIGN_COHORT_LIMIT", "0"))
    if cohort_limit and cohort_limit < 3:
        raise ValueError("isolation smoke requires at least three cohorts")
    if OUT.exists():
        raise RuntimeError(f"attempt output already exists; refusing reuse: {OUT}")
    OUT.mkdir(parents=True)
    WORK.mkdir()
    for name in ["planned_cohorts", "realized_cohorts", "experimental_outputs",
                 "funding_transactions", "scheduled_spends", "realized_spends", "validation_events"]:
        (OUT / "audit" / (name + ".jsonl")).parent.mkdir(parents=True, exist_ok=True)
        (OUT / "audit" / (name + ".jsonl")).touch()
    final_height = (CONFIG["first_cohort_height"] + (cohort_limit - 1) * CONFIG["cadence"] + 36
                    if cohort_limit else CONFIG["end_height"])
    status = {"status": "IN_PROGRESS", "attempt": ATTEMPT_ID,
              "parent_attempt": "pilot_w1", "final_height": final_height}
    atomic_save(OUT / "attempt_status.json", status)
    started = time.monotonic()
    rpc("createwallet", WALLET)
    funding_address = str(rpc("getnewaddress", "funding", "bech32", wallet=WALLET))
    spend_destination = str(rpc("getnewaddress", "spend-sink", "bech32", wallet=WALLET))
    rpc("generatetoaddress", 101, funding_address)
    state = IsolationState(final_height)
    for item in rpc("listunspent", 1, 9999999, [], True,
                    {"minimumAmount": 0, "include_immature_coinbase": False}, wallet=WALLET):
        state.add_funding(item, "initial_coinbase")
    save(OUT / "generator_configuration.json", {
        **CONFIG, "attempt_id": ATTEMPT_ID, "parent_attempt": "pilot_w1",
        "reason_for_retry": "Funding isolation defect: automatic coin selection spent protected experimental outputs.",
        "cohort_limit": cohort_limit or None, "final_height": final_height,
        "funding_pool_policy": "explicit inputs only; experimental outpoints excluded by invariant",
        "lockunspent_policy": "experimental outputs locked after confirmation and unlocked only immediately before scheduled spend",
    })
    creation_heights = list(range(CONFIG["first_cohort_height"], final_height + 1, CONFIG["cadence"]))
    pending: dict[int, list[list[dict[str, object]]]] = {}
    current = 101
    for cohort_id, creation_height in enumerate(creation_heights, 1):
        while current + 1 < creation_height:
            target = current + 1
            due = pending.pop(target, [])
            realized = [(records, prepare_spend(state, records, target, spend_destination)) for records in due]
            blockhash = str(rpc("generatetoaddress", 1, funding_address)[0])
            current = target
            for records, txid in realized:
                realize_group(state, records, txid, current, blockhash)
            state.post_block_validation(current)
        context = prepare_cohort(state, cohort_id, creation_height, funding_address, spend_destination)
        for group, count, age in CONFIG["groups"]:
            if age is not None and age != 0:
                records = [r for r in context["records"] if r["group"] == group]
                target_height = creation_height + int(age)
                for record in records:
                    state.schedule(record, target_height)
                pending.setdefault(target_height, []).append(records)
        due = pending.pop(creation_height, [])
        realized = [(records, prepare_spend(state, records, creation_height, spend_destination))
                    for records in due]
        blockhash = str(rpc("generatetoaddress", 1, funding_address)[0])
        current = creation_height
        confirm_cohort(state, context, current, blockhash, funding_address)
        if context["same_block_records"]:
            realize_group(state, context["same_block_records"], str(context["same_block_txid"]), current, blockhash)
        for records, txid in realized:
            realize_group(state, records, txid, current, blockhash)
        state.cohorts[cohort_id] = context
        state.post_block_validation(current)
        print(f"cohort={cohort_id} height={current} outputs=75", flush=True)

    while current < final_height:
        target = current + 1
        due = pending.pop(target, [])
        realized = [(records, prepare_spend(state, records, target, spend_destination)) for records in due]
        blockhash = str(rpc("generatetoaddress", 1, funding_address)[0])
        current = target
        for records, txid in realized:
            realize_group(state, records, txid, current, blockhash)
        state.post_block_validation(current)
    hashes = write_chain_evidence(final_height)
    validation = validate_final(state, hashes)
    for record in state.records:
        record["final_chain_height"] = final_height
        record["censored"] = record["expected_spend_age_blocks"] is not None and not record["is_spent"]
        record["expected_state_at_end"] = "spent" if record["is_spent"] else "unspent"
        record["validation_status"] = "PASS"
    with (WORK / "manifest.jsonl").open("x", encoding="utf-8") as handle:
        for record in state.records:
            handle.write(json.dumps(record, sort_keys=True) + "\n")
    csvfile(WORK / "manifest.csv", state.records)
    targets = [outpoint(str(r["creation_txid"]), int(r["vout"])) for r in state.records]
    random.Random(CONFIG["seed"]).shuffle(targets)
    save(WORK / "lookup_targets.json", targets[:CONFIG["lookup_target_limit"]])
    validation.update({"generation_seconds": round(time.monotonic() - started, 3),
                       "manifest_sha256": sha(WORK / "manifest.jsonl"),
                       "config_sha256": sha(HERE / "config.json"), "status": "PASS"})
    atomic_save(OUT / "summary.json", validation)
    atomic_save(OUT / "manifest_pin.json", {"manifest_sha256": validation["manifest_sha256"],
                                              "config_sha256": validation["config_sha256"],
                                              "phase": "before_processors"})
    status.update({"status": "PASS", "summary": validation})
    atomic_save(OUT / "attempt_status.json", status)
    print("W1 retry frozen and workload validation PASS; processors not run", flush=True)
    return validation


if __name__ == "__main__":
    generate()
