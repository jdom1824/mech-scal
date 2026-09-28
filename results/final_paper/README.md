# Final experimental evidence

This directory contains processed experimental evidence and small audit inputs
for the final Mech-Scal evaluation. It is intentionally not a manuscript or a
publication package.

Run the repository-relative arithmetic check from the repository root:

```bash
python3 scripts/verify_final_paper_results.py
```

The check verifies the canonical frame through block `870429`, the 17,000-
transaction / 46,962-output attribution artifact, threshold sensitivity, the
50,000-consecutive-full-block stress scenario, and the replication calculations.

The bundled frame is processed experimental data, not a full blockchain dump.
The complete chain database and the original execution environment remain
external inputs; this repository does not claim a fresh full-chain rerun from
the compact evidence bundle. The saved ID26 execution audit passes its
arithmetic checks, but its inference verdict remains `ID26-FINAL-INFERENCE-
UNSTABLE`, and `precision_target_met` remains false. That limitation is part of
the reproducibility record.

Method B in the storage-attribution summary is serialized output bytes only.
It must not be interpreted as measured physical storage.

Manuscript PDFs, LaTeX/Overleaf sources, submission material, reviewer
responses, publication-only figures, and publication-table artifacts are
deliberately excluded from this directory and from the repository.
