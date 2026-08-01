# Reproduction Guide

## 1. Install the repository

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .[figures,dev]
```

## 2. Quick validation

```bash
python3 -m unittest discover -s tests -v
```

Expected result:

- 44 local logic tests pass without needing Bitcoin Core.

## 3. Regtest setup

Export the paths of the already-existing mainnet node before running any orchestration script that checks isolation:

```bash
export MECH_SCAL_MAINNET_DATADIR=/path/to/mainnet/datadir
export MECH_SCAL_MAINNET_BLOCKSDIR=/path/to/mainnet/blocksdir
```

```bash
bash scripts/run_regtest_setup.sh
```

## 4. Generate the deterministic workload

```bash
python3 scripts/generate_workload.py \
  --profile small \
  --seed 20260731 \
  --reset \
  --output-dir data/workloads/small_seed_20260731
```

## 5. Run baseline and Mech-Scal

```bash
python3 scripts/run_baseline.py \
  --start-height 0 \
  --end-height 139 \
  --database data/baseline/small_seed_20260731/baseline.sqlite \
  --reset-db

python3 scripts/run_mech_scal.py \
  --start-height 0 \
  --end-height 139 \
  --database data/mech_scal/small_seed_20260731/mech_scal.sqlite \
  --t-min 24 \
  --reset-db
```

## 6. Benchmark and resilience

```bash
bash scripts/run_phase6.sh
bash scripts/run_phase7.sh
```

## 7. Results

- Benchmark references: `results/reference/phase6/`
- Resilience references: `results/reference/phase7/`
- Final Section 5.4 figures: `results/figures/section_5_4/`
