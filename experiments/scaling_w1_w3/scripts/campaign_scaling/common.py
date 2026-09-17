import base64
import csv
import hashlib
import json
import os
import statistics
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
CODE = Path(os.environ.get("CAMPAIGN_CODE", str(HERE.parent)))
ROOT = Path(os.environ.get("CAMPAIGN_ROOT", str(CODE.parent)))
ATTEMPT_ID = os.environ.get("CAMPAIGN_ATTEMPT_ID", "pilot_w1_retry_01")
OUT = ROOT / "results" / ATTEMPT_ID
WORK = OUT / "workload"
DATA = ROOT / ("regtest_" + ATTEMPT_ID)
CONFIG = json.loads((HERE / "config.json").read_text())
QUERY = "SELECT txid, vout, creation_height, current_class, is_spent FROM outputs WHERE is_spent = 0 AND current_class = 'MH'"


def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")


def csvfile(path, rows):
    rows = list(rows)
    assert rows, str(path)
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def digest(data):
    return hashlib.sha256(json.dumps(data, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def quantile(values, p):
    a = sorted(values)
    index = (len(a) - 1) * p
    lo = int(index)
    return a[lo] + (a[min(lo + 1, len(a) - 1)] - a[lo]) * (index - lo)


def stats(values):
    return {"n": len(values), "median": statistics.median(values), "min": min(values),
            "max": max(values), "iqr": quantile(values, .75) - quantile(values, .25),
            "p95": quantile(values, .95), "p99": quantile(values, .99)}


def rpc(method, *params, wallet=None):
    # Only the new, local W1 cookie; never persist or print its value.
    auth = base64.b64encode((DATA / "regtest/.cookie").read_bytes().strip()).decode()
    url = "http://127.0.0.1:19443/" + ("wallet/" + wallet if wallet else "")
    request = urllib.request.Request(url, data=json.dumps(
        {"jsonrpc": "1.0", "id": "w1", "method": method, "params": list(params)}).encode(),
        headers={"Authorization": "Basic " + auth, "Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=30) as response:
        body = json.load(response)
    if body.get("error"):
        raise RuntimeError(str(body["error"]))
    return body["result"]


def verify_frozen(live=True):
    frozen = json.loads((OUT / "workload_hashes.json").read_text())
    for relative, expected in frozen.items():
        assert sha(WORK / relative) == expected, "Workload changed: " + relative
    if live:
        sequence = json.loads((WORK / "block_hashes.json").read_text())
        info = rpc("getblockchaininfo")
        assert info["chain"] == "regtest" and info["blocks"] == CONFIG["end_height"]
        assert rpc("getnetworkinfo")["connections"] == 0
        assert [rpc("getblockhash", h) for h in range(len(sequence))] == sequence, "Live block sequence changed"
    return frozen


def configure_historical():
    # Runtime configuration only: override imported route constants in memory.
    # No source rewrite and no schema/algorithm change.
    import importlib
    import sys
    sys.path.insert(0, str(CODE / "src"))
    pin = json.loads((OUT / "manifest_pin.json").read_text())
    os.environ["MECH_SCAL_SMOKE_MANIFEST_SHA256"] = pin["manifest_sha256"]
    for name in ["baseline.config", "mech_scal.config", "baseline.processor", "mech_scal.processor"]:
        module = importlib.import_module(name)
        module.REGTEST_CLI = HERE / "w1_cli.sh"
        module.START_SCRIPT = HERE / "refuse_start.sh"
        module.STOP_SCRIPT = HERE / "refuse_start.sh"
