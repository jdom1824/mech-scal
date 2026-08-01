from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path


@dataclass
class OutputRecord:
    run_id: str
    profile: str
    seed: int
    logical_output_id: str
    group: str
    creation_txid: str | None = None
    vout: int | None = None
    creation_height: int | None = None
    creation_blockhash: str | None = None
    value_btc: str | None = None
    address: str | None = None
    expected_spend_age_blocks: int | None = None
    spend_txid: str | None = None
    spend_height: int | None = None
    spend_blockhash: str | None = None
    actual_spend_age_blocks: int | None = None
    is_spent: bool = False
    expected_state_at_end: str = "unspent"
    final_chain_height: int | None = None
    validation_status: str = "PENDING"

    def finalize_age(self) -> None:
        if self.creation_height is None or self.spend_height is None:
            self.actual_spend_age_blocks = None
            return
        self.actual_spend_age_blocks = self.spend_height - self.creation_height

    def to_dict(self) -> dict[str, object]:
        self.finalize_age()
        return asdict(self)


@dataclass
class RunMetadata:
    run_id: str
    profile: str
    seed: int
    threshold_blocks: int
    config_hash: str
    bitcoin_core_version: str
    git_commit: str | None
    dry_run: bool
    started_at: str
    finished_at: str | None = None
    manifest_hash: str | None = None
    final_chain_height: int | None = None
    status: str = "PENDING"
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass
class RunArtifacts:
    output_dir: Path
    manifest_jsonl: Path
    manifest_csv: Path
    summary_json: Path
    sqlite_db: Path
    validation_json: Path
    log_path: Path
