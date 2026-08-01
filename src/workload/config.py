from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from mech_scal import environment as env

CONFIG_DIR = env.CONFIG_DIR
PROJECT_ROOT = env.PROJECT_ROOT
REGTEST_DATADIR = env.REGTEST_DATADIR

REGTEST_CLI = PROJECT_ROOT / "scripts" / "regtest_cli.sh"
START_SCRIPT = PROJECT_ROOT / "scripts" / "start_regtest.sh"
STOP_SCRIPT = PROJECT_ROOT / "scripts" / "stop_regtest.sh"
RESET_SCRIPT = PROJECT_ROOT / "scripts" / "reset_regtest.sh"
VALIDATE_ISOLATION_SCRIPT = PROJECT_ROOT / "scripts" / "validate_isolation.sh"
WORKLOAD_PROFILE_CONFIG = CONFIG_DIR / "workload_profiles.json"
WALLET_NAME = "mech_scal_test"
MIN_AVAILABLE_MEMORY_BYTES = 1_500_000_000


@dataclass(frozen=True)
class GroupSpec:
    name: str
    count: int
    spend_age_blocks: int | None
    expected_state_at_end: str
    value_btc: Decimal


@dataclass(frozen=True)
class WorkloadProfile:
    name: str
    threshold_blocks: int
    max_outputs: int
    allow_execution: bool
    requires_flag: bool
    groups: tuple[GroupSpec, ...]

    @property
    def total_outputs(self) -> int:
        return sum(group.count for group in self.groups)

    def with_threshold(self, threshold_blocks: int) -> WorkloadProfile:
        updated = []
        for group in self.groups:
            spend_age = threshold_blocks if group.name == "operational-boundary" else group.spend_age_blocks
            updated.append(
                GroupSpec(
                    name=group.name,
                    count=group.count,
                    spend_age_blocks=spend_age,
                    expected_state_at_end=group.expected_state_at_end,
                    value_btc=group.value_btc,
                )
            )
        return WorkloadProfile(
            name=self.name,
            threshold_blocks=threshold_blocks,
            max_outputs=self.max_outputs,
            allow_execution=self.allow_execution,
            requires_flag=self.requires_flag,
            groups=tuple(updated),
        )


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_group(raw: dict[str, object]) -> GroupSpec:
    spend_age = raw.get("spend_age_blocks")
    return GroupSpec(
        name=str(raw["name"]),
        count=int(raw["count"]),
        spend_age_blocks=None if spend_age is None else int(spend_age),
        expected_state_at_end=str(raw["expected_state_at_end"]),
        value_btc=Decimal(str(raw["value_btc"])),
    )


def load_profiles(config_path: Path) -> dict[str, WorkloadProfile]:
    raw = json.loads(config_path.read_text(encoding="utf-8"))
    profiles: dict[str, WorkloadProfile] = {}
    for item in raw["profiles"]:
        profile = WorkloadProfile(
            name=str(item["name"]),
            threshold_blocks=int(item["threshold_blocks"]),
            max_outputs=int(item["max_outputs"]),
            allow_execution=bool(item["allow_execution"]),
            requires_flag=bool(item.get("requires_flag", False)),
            groups=tuple(_load_group(group) for group in item["groups"]),
        )
        if profile.total_outputs > profile.max_outputs:
            raise ValueError(f"profile {profile.name} exceeds max_outputs")
        profiles[profile.name] = profile
    return profiles
