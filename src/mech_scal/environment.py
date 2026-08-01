from __future__ import annotations

import os
from pathlib import Path


def _path_from_env(name: str, default: Path) -> Path:
    value = os.getenv(name)
    if value:
        return Path(value).expanduser().resolve()
    return default.resolve()


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = _path_from_env("MECH_SCAL_PROJECT_ROOT", PACKAGE_ROOT.parent)
CONFIG_DIR = _path_from_env("MECH_SCAL_CONFIG_DIR", PROJECT_ROOT / "config")
DATA_DIR = _path_from_env("MECH_SCAL_DATA_DIR", PROJECT_ROOT / "data")
RESULTS_DIR = _path_from_env("MECH_SCAL_RESULTS_DIR", PROJECT_ROOT / "results")
LOGS_DIR = _path_from_env("MECH_SCAL_LOGS_DIR", PROJECT_ROOT / "logs")
RUNTIME_DIR = _path_from_env("MECH_SCAL_RUNTIME_DIR", PROJECT_ROOT / ".runtime")
REGTEST_DATADIR = _path_from_env("MECH_SCAL_REGTEST_DATADIR", RUNTIME_DIR / "regtest")
MAINNET_DATADIR = Path(os.getenv("MECH_SCAL_MAINNET_DATADIR", "")).expanduser().resolve() if os.getenv("MECH_SCAL_MAINNET_DATADIR") else None
MAINNET_BLOCKSDIR = Path(os.getenv("MECH_SCAL_MAINNET_BLOCKSDIR", "")).expanduser().resolve() if os.getenv("MECH_SCAL_MAINNET_BLOCKSDIR") else None


def project_path(*parts: str) -> Path:
    return PROJECT_ROOT.joinpath(*parts)


def data_path(*parts: str) -> Path:
    return DATA_DIR.joinpath(*parts)


def results_path(*parts: str) -> Path:
    return RESULTS_DIR.joinpath(*parts)


def logs_path(*parts: str) -> Path:
    return LOGS_DIR.joinpath(*parts)
