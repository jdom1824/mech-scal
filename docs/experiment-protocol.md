# Experiment Protocol

## Environment

- Bitcoin Core regtest node isolated from any mainnet datadir.
- External prototype processes communicating over RPC.
- Local SQLite databases for baseline and Mech-Scal runs.

## Workload

- Reference workload: 140 blocks, 148 transactions, 362 outputs, and 57 spends.
- Deterministic seed: `20260731`.
- Reduced transition threshold: `T_min = 24`.

## Quick validation

- Run the unit and logic suite:
  - `python3 -m unittest discover -s tests -v`
- Observed runtime in this workspace: well below 1 second.

## Full paired benchmark

- Reference command:
  - `bash scripts/run_phase6.sh`
- Reference paired benchmark size:
  - 2 warm-up pairs
  - 30 measured pairs
- Reference observed estimate from existing artifacts:
  - about `406` seconds

## Resilience evaluation

- Reference command:
  - `bash scripts/run_phase7.sh`
- Existing local artifacts report:
  - `495900` retrieval observations
  - `630762` recovery observations

## Interpretation rules

- Time-based metrics are hardware dependent.
- Functional counts for the deterministic workload should match exactly.
- The SQLite increase is a local-index cost, not a replicated-network-storage increase.
