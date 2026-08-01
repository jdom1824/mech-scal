# Results Reference

## Functional deterministic counts

These values are expected for the compact reference workload and should be treated as functional checks:

- blocks: 140
- transactions: 148
- outputs: 362
- spends: 57
- same-block spends: 5
- final MH: 50
- final ML: 255
- final IM: 57
- MH-to-ML: 266
- MH-to-IM: 46
- ML-to-IM: 11

## Timing references

These are hardware-dependent references extracted from existing local artifacts:

- median baseline processing time: 3.4474 s
- median Mech-Scal processing time: 3.8094 s
- median paired difference: 0.3863 s
- 95% bootstrap CI: [0.2317, 0.5022] s

## Lookup references

- baseline lookup median: 0.0245 ms
- Mech-Scal lookup median: 0.027418 ms
- median paired lookup difference: 0.003208 ms
- 95% lookup CI: [0.002918, 0.003209] ms

## Storage interpretation

- baseline local SQLite index: 401,408 bytes
- Mech-Scal local SQLite index: 634,880 bytes
- absolute difference: 233,472 bytes

This difference belongs to the auxiliary local index only. It is not the replicated blockchain storage of the network.

## Artifact policy

- Included in the public repository: compact reference CSV/JSON summaries, LaTeX tables, and final paper figures.
- Excluded from version control: machine-local logs, caches, temporary reports, helper figure summaries with absolute source paths, and large regenerable databases.

See [`docs/artifact-scope.md`](artifact-scope.md).
