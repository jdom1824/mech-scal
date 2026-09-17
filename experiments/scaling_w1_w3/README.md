# W1--W3 Scaling Reproducibility Package

This directory contains the frozen result tables and the portable campaign
code for the complementary W1--W3 scaling evaluation reported with Mech-Scal.
The experiment uses controlled Bitcoin Core regtest workloads; it is not a
production-scale Bitcoin validation and it is not a distributed deployment.

## Frozen scope

| Workload | Blocks | Reconstructed outputs | Measured pairs | Warm-ups |
| --- | ---: | ---: | ---: | ---: |
| W1 | 1,000 | 3,883 | 3 | 1 per system |
| W2 | 5,001 | 20,085 | 5 | 1 per system |
| W3 | 10,001 | 40,335 | 5 | 1 per system |

Baseline and Mech-Scal were run as paired processors over the same frozen
regtest workload. All included measured runs have `PASS` status. W4 was an
incomplete workload-generation attempt and W5 was not executed; neither is
part of this package or Table 6.

The fixed workload parameters are in
[`configs/w1_w2_w3.json`](configs/w1_w2_w3.json). They include the seed,
cohort cadence, output groups and spend ages, `T_min = 24`, funding
isolation, warm-up policy, lookup sampling, resource gates, and paired run
order. The public configuration intentionally omits attempt metadata, local
paths, logs, wallet directories, and runtime credentials.

## Metrics and conventions

- Processing time is summarized over measured runs as median `[IQR]`.
- Paired processing overhead is `100 * (Mech-Scal / Baseline - 1)` and is
  summarized over paired runs as median `[IQR]`.
- RSS is converted from KiB to MiB using 1,024 KiB/MiB.
- Physical SQLite size and index allocation are converted from bytes to MiB
  using 1,048,576 bytes/MiB.
- Index allocation is the physical allocation reported by SQLite `dbstat`;
  it is not indexing time.
- Lookup observations are reduced to one `basic` median per measured run
  before the across-run summary. Raw lookup observations are not treated as
  independent experimental replicates.
- Quartiles use the pandas/NumPy linear convention, with position
  `h = (n - 1) p` and linear interpolation.

Lookup values are local SQLite retrieval measurements on the experimental
device. They are not network latency or a claim about geographically
distributed retrieval.

## Result verification

From this directory, run:

```bash
python3 analysis/reproduce_table6.py
python3 analysis/verify_public_artifacts.py
```

The first command reads the frozen CSVs, calculates the statistics, checks
the expected W1--W3 dimensions and sample counts, validates the displayed
Table 6 values, and writes `results/table6_reproduced.csv`. It does not run
Bitcoin Core or modify the frozen inputs. The second command verifies the
public SHA-256 manifest and the generated Table 6 output.

## Full experiment reproduction

The heavier path is opt-in and requires Bitcoin Core v31.1, Python 3.9 or
newer, SQLite, an ARM64/Linux or equivalent isolated host, and enough free
RAM and disk for the selected workload. The execution environment recorded
for the frozen campaign was a Radxa ROCK-5T with ARM64, Armbian based on
Debian 13, Bitcoin Core v31.1.0, and SQLite 3.46.1. Python 3.9.6 and NumPy
1.25.2 were used for the separate post-processing audit; they are not a
claim about the experiment runtime.

The portable controller creates one fresh regtest directory per level and
uses loopback-only ports. It requires a directory containing `bitcoind` and
`bitcoin-cli`, and a new empty workspace:

```bash
python3 scripts/run_scaling_campaign_w1_w3.py \
  --base-root /path/to/new/w1-w3-run \
  --bitcoin-bin /path/to/bitcoin/bin
```

The controller never accepts a mainnet datadir, never uses a wallet from the
repository, and refuses to reuse a non-empty output workspace. Full reruns
are expected to be substantially slower than result verification and are
hardware dependent. Exact transaction identifiers can differ across fresh
regtest resets; the logical workload invariants and validation checks are the
reproducible target.

The campaign code under `scripts/campaign_scaling/` is the final workload
generator, isolation logic, processor worker, and resource-gate logic used
by the W1--W3 design. The repository's existing `src/` implementation is
used by the controller for Baseline and Mech-Scal processing. This package
does not automatically launch a rerun when verifying the published values.

## Public artifacts

The compact frozen inputs are:

- `results/scaling_master_runs.csv`
- `results/scaling_master_pairs.csv`
- `results/scaling_summary_by_workload.csv`
- `results/scaling_lookup_run_level.csv`
- `results/scaling_dbstat_per_run.csv`
- `results/evidence_integrity_checks.csv`
- `results/table6_reproduced.csv`

`manifests/public_sha256sums.txt` covers every public artifact in this
directory, including scripts, configuration, documentation, and result
tables. Logs, raw regtest block files, manifests containing transaction
identifiers, SQLite databases, wallet directories, cookies, private paths,
and incomplete W4/W5 artifacts are deliberately excluded.

## Interpretation limits

W1--W3 provide controlled workload-scaling evidence for the prototype over
the evaluated range. They do not establish an asymptotic complexity class,
throughput preservation, production-scale performance, Internet-scale
latency, or deployment optimality. Resource and timing values are
hardware-dependent, and the measured pair counts are small.

## Citation

Please cite the Mech-Scal manuscript and the repository release containing
this directory. No new DOI is assigned by this package.
