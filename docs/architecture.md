# Architecture

Mech-Scal is an external processing and indexing layer built on top of Bitcoin Core RPC.

## Core boundary

- Bitcoin Core remains unmodified.
- The prototype interacts with Bitcoin Core through RPC in regtest.
- SQLite is used as a local auxiliary index, not as replicated blockchain storage.

## Components

- `workload`: deterministic regtest workload generation and validation.
- `baseline`: direct reconstruction of outputs and spends without class transitions.
- `mech_scal`: experimental layer-transition logic over outputs classified as MH, ML, and IM.
- `benchmark`: paired execution and lookup comparison between baseline and Mech-Scal.
- `resilience`: replica-placement, failure, retrieval, and recovery experiments for IM objects.

## Layer-transition logic

- `MH`: unspent outputs younger than the reduced operational threshold.
- `ML`: unspent outputs at or above the reduced threshold.
- `IM`: spent outputs preserved as historical information.

The compact regtest prototype uses `T_min = 24` only to trigger observable transitions in a short workload. Historical analysis in the paper still uses the operational boundary of `2,016` blocks.

## Limits of the prototype

- Validated only in regtest.
- The reference workload is intentionally small and deterministic.
- The benchmark does not demonstrate production-scale Bitcoin throughput.
- Single-device experiments do not constitute a distributed deployment.
