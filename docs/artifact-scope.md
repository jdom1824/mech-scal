# Artifact Scope

This repository includes only the compact scientific artifacts needed to inspect the reference results and rebuild the publication figures without shipping machine-bound runtime state.

## Included

- `results/reference/phase6/`
  - paired benchmark summaries
  - raw benchmark CSV inputs used by the published comparisons
  - LaTeX tables
  - concise JSON and Markdown summaries
- `results/reference/phase7/`
  - resilience and recovery CSV summaries
  - raw retrieval and recovery observation CSV files required by the paper figures and validation
  - LaTeX tables
  - concise JSON summary
- `results/figures/section_5_4/`
  - final PDF and PNG figures prepared for the paper

## Excluded

- logs under `logs/`
- local runtime state under `.runtime/`
- generated SQLite databases under `data/` and runtime `results/`
- cached directories such as `__pycache__/`, `.ruff_cache/`, `.pytest_cache/`, `.mypy_cache/`
- helper figure summaries and generation reports that embed absolute local source paths
- machine-specific build summaries and failure-state snapshots that are reproducible from the public inputs

## Regeneration guidance

- Rebuild benchmark outputs with `bash scripts/run_phase6.sh`.
- Rebuild resilience outputs with `bash scripts/run_phase7.sh`.
- Recreate resilience figures with `python3 scripts/generate_phase7_figures.py`.
- Section 5.4 final figures are preserved directly because they are publication outputs, while their path-bearing helper reports remain excluded.
