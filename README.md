# Mech-Scal

Research prototype for output-aware replication and experimental indexing in
UTXO blockchains.

**Status:** research and reproducibility artifact; not production software.

## Experimental scope

Mech-Scal is an external processing and indexing layer built on top of Bitcoin
Core RPC. It does not modify Bitcoin Core. The repository contains source code,
controlled regtest experiments, processed evidence, analysis utilities, and
reproducibility documentation. The manuscript and its publication package are
not repository inputs or outputs.

The compact prototype uses `T_min = 24` so that MH, ML, and IM transitions are
observable in a short deterministic workload. The historically analyzed
operational threshold pair is `T_min = 2,016` and `T_max = 26,280`; these are
evaluated experimental parameters, not universal or theoretically optimal
values.

## Evidence types

The final evaluation combines different evidence sources. They should not be
read as one physical deployment or as a single end-to-end network measurement.

1. **Historical mainnet reconstruction:** processed output-class and storage
   accounting through Bitcoin block `870429`.
2. **Analytical and modeled storage analysis:** attribution, threshold,
   replication-policy, and storage-sensitivity calculations based on processed
   class volumes and explicit assumptions.
3. **Controlled local experiments:** Bitcoin Core regtest workload generation,
   paired Baseline/Mech-Scal processing, local SQLite retrieval, and IM fault
   and recovery scenarios.
4. **Synthetic topology simulation:** a complementary sensitivity model for
   graph-derived hop delays. The original BA/ER/WS experiment package and its
   exact run configuration are missing from this repository. Unverified
   candidate files in a detached local workspace are not claimed as the
   original experiment or as reproducible evidence.

## Output classes

- `MH`: unspent outputs below the reduced prototype threshold.
- `ML`: unspent outputs at or above the reduced prototype threshold.
- `IM`: spent outputs retained as historical information.

These labels describe the experimental classifier and storage accounting. They
do not imply a production deployment or a complete physical-storage audit.

## Environment and requirements

- Python `>=3.9`.
- The core package has no mandatory Python dependencies; optional development
  and figure dependencies are declared in `pyproject.toml`.
- The compact regtest path requires a local Bitcoin Core installation and the
  usual `bitcoind`/`bitcoin-cli` tools.
- The W1--W3 full campaign additionally requires Bitcoin Core `v31.1` (or an
  explicitly validated equivalent), SQLite, an isolated ARM64/Linux or
  equivalent host, and enough disk/RAM for fresh regtest workspaces.
- Shell entrypoints may also use standard utilities such as `jq`.

Create a local environment with:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[figures,dev]'
```

## Reproducing the experiments

### 1. Historical mainnet reconstruction and output classes

The processed frame reaches Bitcoin block `870429`. The final classified
output-byte accounting is:

| Class | Storage | Share |
| --- | ---: | ---: |
| MH | `5.79 GiB` | `1.01%` |
| ML | `34.99 GiB` | `6.10%` |
| IM | `532.36 GiB` | `92.89%` |
| MH + ML | `40.78 GiB` | `7.11%` |

The exact processed row is in
`results/final_paper/data/cumulative_storage_growth_by_class_frame47_simplified.csv`;
the compact summary is in
`results/final_paper/data/class_storage_summary.csv`, and frame metadata is in
`results/final_paper/data/final_frame_metadata.json`.

This checkout does not contain the complete chain database, raw `blk*.dat`
files, or a public full-chain reconstruction runner. The repository therefore
provides processed evidence and arithmetic verification, not a fresh full
mainnet rerun from the compact bundle.

Verify the stored arithmetic with:

```bash
python3 scripts/verify_final_paper_results.py
```

This repository-level verifier also checks the saved attribution,
threshold/stress, replication-policy, alpha, `d_eff`, Phase 6, and Phase 7
artifacts described below; it does not regenerate the historical reconstruction.

### 2. Storage-attribution sensitivity

The saved attribution study contains 17,000 sampled transaction instances and
46,962 original outputs. The IM shares are:

| Method | IM share |
| --- | ---: |
| A | `92.33%` |
| B | `93.78%` |
| C | `92.38%` |

Use `results/final_paper/data/final_selection_manifest.csv` for the sampled
frame and weights, `results/final_paper/data/final_attribution_abc.csv` for the
per-output A/B/C values, and
`results/final_paper/data/storage_attribution_summary.csv` for the summary.

Method B is serialized output bytes only. It is not a measurement of physical
storage.

### 3. Threshold and congestion sensitivity

The processed threshold artifacts evaluate:

- `T_min`: `144`, `1,008`, `2,016`, `4,032`, `8,064`, and `13,140` blocks;
- `T_max`: `13,140`, `26,280`, and `52,560` blocks;
- a stress scenario with 50,000 consecutive full blocks.

The files are:

- `results/final_paper/data/tmin_sensitivity_summary.csv`
- `results/final_paper/data/tmax_sensitivity_summary.csv`
- `results/final_paper/data/full_blocks_50000_summary.csv`
- `results/final_paper/data/tmin_delta_identity_audit.csv`

The pair `T_min = 2,016`, `T_max = 26,280` is the practical evaluated
configuration. The threshold results do not establish a universal optimum or a
production congestion guarantee. The verifier checks the six `T_min` values,
three `T_max` values, and all three 50,000-full-block cases over the 870,430-row
processed frame.

### 4. Replicated-storage comparison

`results/final_paper/data/replicated_storage_table5.csv` reports the following
modeled cumulative storage comparison:

| Configuration | Storage | Reduction |
| --- | ---: | ---: |
| Uniform full replication | `10,316,324.56 GiB` | `0.00%` |
| Class partitioning only | `3,438,774.85 GiB` | `66.67%` |
| Reduced IM replication only | `740,845.24 GiB` | `92.82%` |
| Complete Mech-Scal | `251,562.16 GiB` | `97.56%` |

The reduction is relative to an analytical uniform-replication upper bound of
18,000 storage nodes. It is not measured physical storage on the current
Bitcoin network.

### 5. Replication-policy sensitivity

The policy summary is in
`results/final_paper/data/replication_policy_summary.csv`; unrounded values are
in `results/final_paper/data/im_replication_factor_sensitivity.csv`. The tested
policies are:

- Fixed-3;
- Fixed-5;
- Logarithmic, with `r_IM = ceil(log2(m_IM))` and `r_IM = 13` for `m_IM = 6,000`;
- Proportional-1%;
- Square-root;
- Layer-full IM.

The modeled storage/reduction pairs are Fixed-3 `240.47 TiB / 97.61%`, Fixed-5
`241.51 TiB / 97.60%`, Logarithmic `245.67 TiB / 97.56%`, Proportional-1%
`270.10 TiB / 97.32%`, Square-root `279.46 TiB / 97.23%`, and Layer-full IM
`3,358.18 TiB / 66.67%`. These are modeled policy comparisons. They do not
establish policy optimality.

### 6. Alpha sensitivity

Recompute the analytical storage sensitivity from the canonical processed
block-870429 class-byte row and the existing Logarithmic policy inputs with:

```bash
python3 experiments/alpha_sensitivity/reproduce_alpha_sensitivity.py
```

Inputs are `results/final_paper/data/cumulative_storage_growth_by_class_frame47_simplified.csv`
and `results/final_paper/data/im_replication_factor_sensitivity.csv`. The script
writes `results/final_paper/data/alpha_sensitivity.csv`. It evaluates
`r_IM(alpha) = ceil(alpha * log2(m_IM))` for `m_IM = 6,000` and
`alpha` values `0.50`, `0.75`, `1.00`, `1.25`, `1.50`, and `2.00`. The result
spans `r_IM = 7..26`, modeled storage from `242.55` to `252.42 TiB`, and modeled
reduction from `97.59%` to `97.49%`. At `alpha = 1`, `r_IM = 13` and storage
matches the existing Logarithmic policy within `1e-9 GiB`. This is an
analytical/model-derived sensitivity, not a measured storage experiment or a
reliability calibration; alpha one is an evaluated operating point, not an
optimality claim.

### 7. W1--W3 controlled scaling

The reproducibility package is in `experiments/scaling_w1_w3/`. Its frozen
workloads are:

| Workload | Blocks | Reconstructed outputs | Measured pairs |
| --- | ---: | ---: | ---: |
| W1 | `1,000` | `3,883` | `3` |
| W2 | `5,001` | `20,085` | `5` |
| W3 | `10,001` | `40,335` | `5` |

W3 is approximately 71 times the compact 140-block workload by block count
and approximately 111 times larger by reconstructed outputs. It is still a
controlled regtest evaluation, not a production-scale Bitcoin deployment.

Recompute the frozen Table 6 result and verify its public manifest with:

```bash
cd experiments/scaling_w1_w3
python3 analysis/reproduce_table6.py
python3 analysis/verify_public_artifacts.py
```

The reproducible controller for a full rerun is
`experiments/scaling_w1_w3/scripts/run_scaling_campaign_w1_w3.py`. It requires
a new empty workspace and Bitcoin Core binaries:

```bash
W1_W3_ROOT="$(mktemp -d /tmp/mech-scal-w1-w3.XXXXXX)"
command -v bitcoind >/dev/null || { echo "Install/provide Bitcoin Core first" >&2; exit 1; }
BITCOIN_BIN_DIR="$(dirname "$(command -v bitcoind)")"
python3 experiments/scaling_w1_w3/scripts/run_scaling_campaign_w1_w3.py \
  --base-root "$W1_W3_ROOT" \
  --bitcoin-bin "$BITCOIN_BIN_DIR"
```

The frozen outputs and conventions are documented in
`experiments/scaling_w1_w3/README.md`. Full timing and resource values are
hardware-dependent; W1--W3 do not establish an asymptotic complexity class or
throughput preservation. The command still requires the actual Bitcoin Core
binary directory; it does not install or locate Bitcoin Core for the user.

### 8. Phase 6 paired processing benchmark

Validate the saved paired Baseline/Mech-Scal processing summary with:

```bash
python3 scripts/validate_phase6.py results/reference/phase6/phase6_summary.json
python3 scripts/verify_final_paper_results.py
```

The saved inputs and outputs are under `results/reference/phase6/`, including
`raw_processing_runs.csv`, `raw_block_metrics.csv`,
`raw_lookup_observations.csv`, `paired_processing_comparison.csv`,
`processing_summary.csv`, and the remaining summary and LaTeX table artifacts.
The saved summary reports 30 valid pairs, 0 invalid pairs, baseline median
`3.4474 s`, Mech-Scal median `3.8094 s`, median paired difference `0.3863 s`,
and median overhead `10.73%`. These are saved local benchmark measurements,
not production-throughput results. The repository-level verifier also checks
the saved Phase 6 summary fields and raw CSV row counts.

To opt in to a new local run:

```bash
bash scripts/run_phase6.sh
```

This requires a configured local Bitcoin Core/regtest environment and writes
new artifacts. This audit validated the saved summary and did not rerun the
benchmark.

### 9. Fault, retrieval, and recovery experiments

The controlled IM resilience path is launched with:

```bash
bash scripts/run_phase7.sh
```

The scenario and validation helpers are
`scripts/build_im_replicas.py`, `scripts/run_failure_scenarios.py`,
`scripts/run_recovery_scenarios.py`, `scripts/validate_resilience.py`, and
`scripts/generate_phase7_tables.py`.

The saved phase-7 summary contains 495,900 retrieval observations and 630,762
recovery observations for 57 IM objects. It evaluates Fixed-3, Fixed-5, and
Logarithmic (`r = 13`) policies. The maximum tolerated failures recorded by the
summary are 2, 4, and 12 respectively; the corresponding retrieval p99 values
are `0.3412 ms`, `0.3386 ms`, and `0.3345 ms`.

The raw observations are in:

- `results/reference/phase7/raw_retrieval_observations.csv`
- `results/reference/phase7/raw_recovery_observations.csv`

Scenarios include latency and timeout/withholding behavior, corruption and
checksum validation, progressive failures, churn, correlated logical failures,
recovery/repair, and external fallback. Recovery traffic is logical payload
bytes transferred by the model, not measured NIC/network traffic. The saved
summary and raw CSV row counts were cross-checked; this audit did not rerun the
fault campaign. A new run is opt-in and requires the configured local Bitcoin
Core/regtest environment. Check the frozen summary/raw row counts together
with the other saved results using:

```bash
python3 scripts/verify_final_paper_results.py
```

### 10. Correlated logical-failure scenarios

`results/reference/phase7/correlated_failure_summary.csv` contains four logical
failure-domain families—`single-rack`, `two-racks`, `largest-provider`, and
`placement-hotspot`—across the three policies and two retrieval strategies.
Each family has 1,710 attempts per policy/strategy pair.

For the Logarithmic (`r = 13`) policy, both retrieval strategies completed
3,420 of 3,420 correlated-failure attempts successfully. The two-rack model
removed 8--9 of the 13 replicas, leaving a mean of 4.4333 surviving replicas.
The corresponding Log-13 correlated-recovery rows report 44,460 successful
observations and 58,707,480 logical bytes transferred.

These are logical failure-domain simulations. The labels do not prove physical
rack or provider independence, and they are not measurements of real outages.

### 11. `d_eff` sensitivity

Recompute the analytical values from `P_loss = q_D ** d_eff` with:

```bash
python3 experiments/failure_domain_sensitivity/reproduce_d_eff_sensitivity.py
```

The script writes `results/final_paper/data/d_eff_analytical_sensitivity.csv`
with 15 combinations of `d_eff` in `{13, 7, 4, 2, 1}` and illustrative `q_D`
values in `{0.01, 0.05, 0.10}`. For example, at `q_D = 0.05`, the computed
`P_loss` values for `d_eff = 13, 7, 4, 2, 1` are respectively
`1.220703125e-17`, `7.8125e-10`, `6.25e-6`, `2.5e-3`, and `5e-2`. These are
analytical sensitivity values, not measured
availability. `q_D` is not empirically calibrated by the prototype, and
`d_eff` is not measured by it. Thirteen logical replicas do not imply thirteen
independent physical failure domains; the prototype's logical rack/provider
labels do not establish physical independence.

### 12. Synthetic topology availability

The public repository and its available Git history contain no complete
BA/ER/WS experiment package. A detached local workspace copy contains a
candidate simulator, raw and summarized outputs, and a report, but the exact
configuration used for that run is absent. Without that input the candidate
cannot be rerun or certified against its reported p50/p95/p99 values. Status:
**MISSING — ORIGINAL EXPERIMENTAL ARTIFACT NOT PRESENT**. No topology-delay
result is presented here as a repository reproduction. Detached candidate
files without established provenance and the exact run configuration do not
close this gap. To complete this evidence block, recover the original run
original source, configuration, seeds, dependencies, and outputs, then verify
their provenance before rerunning that original implementation. Any resulting
values would remain a synthetic availability-sensitivity model, not measured
WAN latency or a physical Bitcoin deployment.

## Experiment-to-artifact map

| Evidence | Type | Script | Inputs | Output | Status |
| --- | --- | --- | --- | --- | --- |
| Historical class/storage accounting through block 870429 | Historical mainnet reconstruction; processed evidence | `scripts/verify_final_paper_results.py` | `results/final_paper/data/cumulative_storage_growth_by_class_frame47_simplified.csv`; `results/final_paper/data/final_frame_metadata.json` | `results/final_paper/data/class_storage_summary.csv` | VERIFIED |
| Full raw-chain reconstruction | Historical mainnet reconstruction | No full-chain runner in this checkout | Raw chain blocks and original extractor are not packaged | Processed frame only; no fresh raw-chain output | PARTIAL |
| Attribution A/B/C | Analytical/model-derived attribution on a sampled historical frame | `scripts/verify_final_paper_results.py` | `results/final_paper/data/final_selection_manifest.csv`; `results/final_paper/data/final_attribution_abc.csv` | `results/final_paper/data/storage_attribution_summary.csv` | VERIFIED |
| Thresholds and 50,000-full-block stress | Analytical/model-derived sensitivity | `scripts/verify_final_paper_results.py` | `results/final_paper/data/tmin_sensitivity_summary.csv`; `results/final_paper/data/tmax_sensitivity_summary.csv`; `results/final_paper/data/full_blocks_50000_summary.csv`; `results/final_paper/data/tmin_delta_identity_audit.csv` | Saved CSVs, checked for consistency | VERIFIED |
| Table 5 replication comparison | Analytical/model-derived storage | `scripts/verify_final_paper_results.py` | `results/final_paper/data/cumulative_storage_growth_by_class_frame47_simplified.csv`; `results/final_paper/data/im_replication_factor_sensitivity.csv` | `results/final_paper/data/replicated_storage_table5.csv` | VERIFIED |
| Replication-policy sensitivity | Analytical/model-derived storage | `scripts/verify_final_paper_results.py` | `results/final_paper/data/im_replication_factor_sensitivity.csv`; `results/final_paper/data/cumulative_storage_growth_by_class_frame47_simplified.csv` | `results/final_paper/data/replication_policy_summary.csv` | VERIFIED |
| Alpha sensitivity | Analytical/model-derived storage sensitivity | `experiments/alpha_sensitivity/reproduce_alpha_sensitivity.py` | `results/final_paper/data/cumulative_storage_growth_by_class_frame47_simplified.csv`; `results/final_paper/data/im_replication_factor_sensitivity.csv` | `results/final_paper/data/alpha_sensitivity.csv` | VERIFIED |
| d_eff sensitivity | Analytical failure-probability sensitivity; not measured availability | `experiments/failure_domain_sensitivity/reproduce_d_eff_sensitivity.py` | Declared equation and illustrative inputs in the script | `results/final_paper/data/d_eff_analytical_sensitivity.csv` | VERIFIED |
| Phase 6 saved paired benchmark | Controlled local Bitcoin Core/regtest processing experiment | `scripts/verify_final_paper_results.py` | `results/reference/phase6/phase6_summary.json`; `raw_processing_runs.csv`; `raw_block_metrics.csv`; `raw_lookup_observations.csv` | Saved Phase 6 summary, raw observations, derived summaries, and tables in `results/reference/phase6/` | VERIFIED |
| Phase 6 fresh benchmark | Controlled local Bitcoin Core/regtest processing experiment | `scripts/run_phase6.sh` | Configured local Bitcoin Core/regtest environment | New outputs under `results/reference/phase6/` | PARTIAL |
| W1--W3 frozen table and public-hash verification | Controlled local regtest evidence; saved-artifact verification | `experiments/scaling_w1_w3/analysis/reproduce_table6.py`; `experiments/scaling_w1_w3/analysis/verify_public_artifacts.py` | Frozen W1--W3 outputs and public hash manifest | `experiments/scaling_w1_w3/results/table6_reproduced.csv`; 23 validated hashes | VERIFIED |
| W1--W3 fresh campaign | Controlled local Bitcoin Core/regtest experiment | `experiments/scaling_w1_w3/scripts/run_scaling_campaign_w1_w3.py` | Frozen workloads, Bitcoin Core binaries, new workspace | User-selected new campaign workspace | PARTIAL |
| Phase 7 saved fault/recovery evidence | Controlled local logical fault/recovery experiment | `scripts/verify_final_paper_results.py` | `results/reference/phase7/phase7_summary.json`; `raw_retrieval_observations.csv`; `raw_recovery_observations.csv` | Saved Phase 7 summary and raw retrieval/recovery CSVs in `results/reference/phase7/` | VERIFIED |
| BA/ER/WS topology-delay study | Synthetic topology/queueing simulation | Original executable is not present in this checkout | Original run configuration and provenance are absent | No certified reproduction output | MISSING |

## Experimental dataset

Large or raw experimental materials are not included in this repository. The
existence, contents, and completeness of any external dataset record have not
been verified in this audit. This repository contains only the compact
experimental files listed in its artifact maps; it does not contain the
manuscript or a manuscript submission package.

## Scope and limitations

This repository does not demonstrate:

- production-scale Bitcoin throughput;
- throughput preservation under real network load;
- sublinear scalability proven in deployment;
- a physically distributed multi-node storage deployment;
- geographically realistic WAN latency or availability;
- optimality of the logarithmic replication policy;
- empirical calibration of analytical failure probabilities;
- a universal optimum for `T_min`, `T_max`, `alpha`, or `d_eff`.

The local SQLite sizes and lookup times are auxiliary prototype measurements,
not replicated blockchain-storage measurements or Internet latency. Processed
mainnet values are accounting evidence bounded by the included metadata and
validation scripts; they are not a claim that the compact repository can
reconstruct the entire chain without external inputs.

## Compact prototype and reference checks

The deterministic functional workload contains 140 blocks, 148 transactions,
362 outputs, and 57 spends. Its final class counts are MH `50`, ML `255`, and
IM `57`; transition counts are MH-to-ML `266`, MH-to-IM `46`, and ML-to-IM
`11`.

Run the unit and regression checks with:

```bash
python3 -m unittest discover -s tests -v
```

The paired local benchmark and resilience entrypoints are:

```bash
bash scripts/run_phase6.sh
bash scripts/run_phase7.sh
```

These commands require a suitable local Bitcoin Core/regtest environment. See
[`docs/reproduction-guide.md`](docs/reproduction-guide.md),
[`docs/experiment-protocol.md`](docs/experiment-protocol.md), and
[`docs/results-reference.md`](docs/results-reference.md) for the compact
prototype workflow.

## Repository structure

- `src/`: core Python packages for workload generation, baseline processing,
  Mech-Scal classification, benchmarking, and resilience.
- `scripts/`: regtest orchestration, fault/recovery entrypoints, validators,
  and report generators.
- `experiments/scaling_w1_w3/`: frozen W1--W3 inputs, analysis, and campaign
  controller.
- `results/final_paper/data/`: compact processed evidence for the final
  mainnet/accounting analyses.
- `results/reference/phase6/`: paired benchmark reference artifacts.
- `results/reference/phase7/`: resilience and correlated-failure artifacts.
- `tests/`: local logic and regression tests.
- `docs/`: experiment protocols, artifact boundaries, and reproduction notes.

## Contributing, citation, and security

- Contribution guide: [`CONTRIBUTING.md`](CONTRIBUTING.md)
- Citation metadata: [`CITATION.cff`](CITATION.cff)
- Security policy: [`SECURITY.md`](SECURITY.md)

## License

MIT. See [`LICENSE`](LICENSE).
