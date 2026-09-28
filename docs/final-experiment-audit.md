# Final experiment audit

This document maps the final experimental claims to repository-contained
reproducibility artifacts. It describes results and accounting boundaries; it
does not reproduce a manuscript or package publication material.

## Mainnet reconstruction boundary

The processed storage series includes the frame through Bitcoin block `870429`.
At that frame, the class-specific values are:

- MH: `5.79 GiB` (`1.01%`),
- ML: `34.99 GiB` (`6.10%`),
- IM: `532.36 GiB` (`92.89%`),
- MH + ML: `7.11%`.

The exact byte-level row is retained in
`results/final_paper/data/cumulative_storage_growth_by_class_frame47_simplified.csv`;
the compact summary is in `class_storage_summary.csv`.

These are classified output-byte accounting quantities. The IM/ML/MH labels do
not imply that a publication PDF or a complete chain database is stored here.

## Storage-attribution sensitivity

The saved attribution artifact covers 17,000 sampled transaction instances and
46,962 original outputs. Its IM shares are:

| Method | IM share |
| --- | ---: |
| A | 92.33% |
| B | 93.78% |
| C | 92.38% |

The full per-output A/B/C values are in `final_attribution_abc.csv`, with the
selection weights and sample frame in `final_selection_manifest.csv`.
Method B is explicitly bounded to serialized output bytes; it is not a
measurement of physical storage.

## Threshold and congestion sensitivity

The threshold artifacts evaluate `Tmin` values `144`, `1008`, `2016`, `4032`,
`8064`, and `13140` with `Tmax=26280`. The complementary `Tmax` evaluation uses
`13140`, `26280`, and `52560`. The stress artifact evaluates 50,000 consecutive
full blocks over the saved frame.

`Tmin=2016` and `Tmax=26280` are practical evaluated Bitcoin parameters in this
experiment. They are not presented as universal or theoretically optimal
thresholds.

## Replication and storage arithmetic

The clean processed summary in `replicated_storage_table5.csv` reports:

- full replication: `10,316,324.56 GiB`, `0.00%` reduction;
- class partitioning only: `3,438,774.85 GiB`, `66.67%` reduction;
- reduced IM replication only: `740,845.24 GiB`, `92.82%` reduction;
- complete Mech-Scal: `251,562.16 GiB`, `97.56%` reduction.

The policy sensitivity artifact reports the final tested policies: Fixed-3,
Fixed-5, Logarithmic, Proportional-1%, Square-root, and Layer-full IM. The
unrounded processed values remain in `im_replication_factor_sensitivity.csv`.

## Reproducibility and limitations

Run `python3 scripts/verify_final_paper_results.py` from the repository root to
recompute the stored arithmetic checks. The validator uses only repository-
relative files, the Python standard library, and no network or blockchain
database access.

The independent saved artifact audit is `PASS`, including attribution,
weighted totals, variance/CI recomputation, and selected-ordinal mapping. It
also records the final ID26 inference verdict as unstable and the precision
target as unmet. Those checks do not authorize upgrading the result into a
fresh full-chain claim.

No manuscript source, manuscript PDF, LaTeX/Overleaf source, reviewer-response
material, submission package, or publication-only figure is required or
stored by this audit.
