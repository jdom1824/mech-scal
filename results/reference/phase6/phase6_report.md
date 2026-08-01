# Phase 6 Benchmark Report

## Final Status

- PASS

## Design

- 2 warm-up runs per system, excluded from results.
- 30 measured pairs with strict alternation: baseline then Mech-Scal.
- Same heights, same workload, same T_min=24, same deterministic lookup order.
- Warm-cache or uncontrolled-cache conditions; system caches were not cleared.

## Aggregate Results

- Valid pairs: `30`
- Invalid pairs: `0`
- Baseline median time (s): `3.447364944004221`
- Mech-Scal median time (s): `3.8093742529890733`
- Median overhead (%): `10.730663481382233`

## Bootstrap Intervals

- time_median_difference: median diff `0.3862574719969416`, 95% CI [`0.23168621500371955`, `0.5022428439988289`]
- sqlite_size_median_difference: median diff `233472.0`, 95% CI [`233472.0`, `233472.0`]
- peak_rss_median_difference: median diff `386.0`, 95% CI [`384.0`, `396.0`]
- lookup_median_difference_ms: median diff `0.003207999999999999`, 95% CI [`0.0029175000000000017`, `0.003209`]

## Limitations

- Negative overhead is reported as an observed difference, not as automatic acceleration.
- Lookup percentages should be read together with absolute latencies.
- The small workload is experimental and not representative of production scale.
