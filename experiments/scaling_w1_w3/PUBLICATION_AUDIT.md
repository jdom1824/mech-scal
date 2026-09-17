# Public W1--W3 Package Audit

## Scope

This release contains the frozen compact result tables used to reproduce the
W1--W3 scaling values and the portable campaign code needed for an opt-in
full regtest rerun. No W1, W2, or W3 experiment was rerun while preparing
this release. W4 and W5 are excluded because W4 did not complete workload
generation and W5 was not executed.

## Frozen evidence used

The public result tables were copied from the preserved W1--W3 scaling audit
artifacts:

- `scaling_master_runs.csv`
- `scaling_master_pairs.csv`
- `scaling_summary_by_workload.csv`
- `scaling_lookup_run_level.csv`
- `scaling_dbstat_per_run.csv`
- `evidence_integrity_checks.csv`

The public `table6_reproduced.csv` is derived only by
`analysis/reproduce_table6.py`; it is not represented as an old raw
manifest. A new release-specific SHA-256 manifest is generated for this
directory.

## Reproducibility checks

- Table 6 reproduction: **PASS**.
- W1/W2/W3 dimensions: **PASS** (1,000/5,001/10,001 blocks and
  3,883/20,085/40,335 reconstructed outputs).
- Pair counts: **PASS** (N=3/5/5; warm-ups excluded).
- Displayed processing, overhead, RSS, SQLite, lookup, and index-allocation
  values: **PASS** against the frozen manuscript values.
- Quartile convention: linear interpolation at `h=(n-1)p`.
- Lookup reduction: one basic median per measured run before across-run
  summaries; raw observations are not treated as independent replicates.
- Offline funding-isolation regression tests: **PASS**.

## Security and privacy audit

The candidate package was scanned for passwords, tokens, API keys, private
keys, RPC credentials, cookies, wallet data, SSH material, Tailscale data,
private IP addresses, and absolute workstation/Radxa paths. No secret or
machine-specific credential was found. The strings referring to a local
regtest cookie and an ephemeral wallet name are code-level mechanisms: the
cookie is read only from the newly created isolated regtest directory and is
never included in the package or printed.

The following were deliberately excluded: logs, raw block and transaction
manifests, SQLite databases, regtest directories, wallet directories,
cookies, runtime state, absolute-path provenance manifests, and incomplete
W4/W5 artifacts.

## Size audit

All candidate files are small text artifacts; no file is near the 10 MiB
review threshold and no database or generated runtime directory is included.
The final file count and total byte size are reported after manifest
generation in the release summary.

## Environment distinction

The frozen experiment environment was a Radxa ROCK-5T, ARM64, Armbian based
on Debian 13, Bitcoin Core v31.1.0, and SQLite 3.46.1. The separate audit
environment used Python 3.9.6 and NumPy 1.25.2. These environments are not
conflated in the README or the analysis code.

## Clean-checkout verification

The package is designed to run from a clean clone with only Python's
standard library for result verification. The full controller is opt-in,
requires an explicitly supplied Bitcoin Core binary directory and a new
workspace, and operates only on isolated loopback regtest directories.

## Limitations

The W1--W3 campaign is controlled prototype evidence, not production-scale
Bitcoin validation. Processing time is hardware dependent; local lookup is
not network latency; the small number of measured pairs does not establish
an asymptotic law; and the package does not claim throughput preservation or
geographically distributed deployment performance.
