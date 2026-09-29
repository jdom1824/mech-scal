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
4. **Synthetic topology simulation:** intended as a complementary sensitivity
   model for graph-derived hop delays. The topology scripts/configuration and
   their result bundle are not included in the current tracked checkout, so no
   synthetic-topology result is claimed as repository-reproducible here.

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
production congestion guarantee.

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

These are modeled policy comparisons. They do not establish policy optimality.

### 6. Alpha sensitivity

The evaluated analytical grid was `alpha` values `0.50`, `0.75`, `1.00`,
`1.25`, `1.50`, and `2.00`, with `r_IM(alpha) = ceil(alpha * log2(m_IM))`.
The `alpha = 1` /
logarithmic configuration is an evaluated operating point and the repository's
reported baseline, not a universally optimal value.

The corresponding portable alpha-sensitivity script and result CSV are not
bundled in the current tracked checkout. No alpha rerun command is advertised
here. The reliability values for this analysis are analytical/parametric and
are not calibrated failure probabilities.

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
python3 experiments/scaling_w1_w3/scripts/run_scaling_campaign_w1_w3.py \
  --base-root /path/to/new/w1-w3-run \
  --bitcoin-bin /path/to/bitcoin/bin
```

The frozen outputs and conventions are documented in
`experiments/scaling_w1_w3/README.md`. Full timing and resource values are
hardware-dependent; W1--W3 do not establish an asymptotic complexity class or
throughput preservation.

### 8. Fault, retrieval, and recovery experiments

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
bytes transferred by the model, not measured NIC/network traffic.

### 9. Correlated logical-failure scenarios

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

### 10. `d_eff` sensitivity

The current tracked checkout contains no executable `d_eff` sensitivity script
or result artifact. The analytical placement discussion is therefore not
presented as a repository-rerunnable experiment. A future artifact should
include the parameter file, executable analysis, raw/processed output, and a
validation check before this claim is treated as reproducible.

### 11. Synthetic topology availability

The current tracked checkout contains no topology configuration, executable
topology simulator, or topology result bundle. Consequently, this README does
not claim the synthetic BA/ER/WS topology experiment as reproducible from
GitHub, and no topology command is provided.

The intended scope of that analysis is a 18,000-node synthetic graph with
6,000 nodes per layer, a 500 ms target, 100,000 requests per topology, and
topology-specific shortest-path distance surrogates. Those assumptions must be
reintroduced as tracked configuration and validated artifacts before numerical
p99 results are treated as repository evidence. They would represent a
complementary sensitivity model, not measured WAN availability or a physical
Bitcoin deployment.

## Experiment-to-artifact map

| Experiment | Executable path | Main result/artifact path | Status |
| --- | --- | --- | --- |
| Mainnet arithmetic audit | `scripts/verify_final_paper_results.py` | `results/final_paper/data/` | Processed evidence; no full-chain rerun |
| Attribution A/B/C | `scripts/verify_final_paper_results.py` | `results/final_paper/data/final_attribution_abc.csv` | Included |
| Threshold sensitivity | `scripts/verify_final_paper_results.py` | `results/final_paper/data/tmin_sensitivity_summary.csv` | Included |
| 50,000-block stress | `scripts/verify_final_paper_results.py` | `results/final_paper/data/full_blocks_50000_summary.csv` | Included |
| Replication policies | `scripts/verify_final_paper_results.py` | `results/final_paper/data/im_replication_factor_sensitivity.csv` | Included |
| W1--W3 frozen verification | `experiments/scaling_w1_w3/analysis/reproduce_table6.py` | `experiments/scaling_w1_w3/results/table6_reproduced.csv` | Included |
| W1--W3 full campaign | `experiments/scaling_w1_w3/scripts/run_scaling_campaign_w1_w3.py` | New user-selected output workspace | Opt-in, hardware-dependent |
| Fault/recovery | `scripts/run_phase7.sh` | `results/reference/phase7/` | Included reference artifacts |
| Correlated logical failures | `scripts/run_phase7.sh` | `results/reference/phase7/correlated_failure_summary.csv` | Included reference artifact |
| Alpha sensitivity | Not bundled | Not bundled in current checkout | Missing portable artifact |
| `d_eff` sensitivity | Not bundled | Not bundled in current checkout | Missing executable artifact |
| Synthetic topology | Not bundled | Not bundled in current checkout | Missing config/script/results |

## Experimental dataset

Large or raw experimental materials may be distributed separately from this
repository. The associated dataset record is the Harvard Dataverse DOI
[`10.7910/DVN/QBFA7Y`](https://doi.org/10.7910/DVN/QBFA7Y). This repository
contains only the compact experimental files explicitly listed in its artifact
maps; it does not contain the manuscript or a manuscript submission package.

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
