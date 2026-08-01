from __future__ import annotations

from datetime import datetime, timezone

from .database import MechScalDatabase


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def persist_transition(
    database: MechScalDatabase,
    txid: str,
    vout: int,
    from_class: str | None,
    to_class: str,
    transition_height: int,
    reason: str,
    age_blocks: int,
) -> None:
    database.insert_transition(
        {
            "txid": txid,
            "vout": vout,
            "from_class": from_class,
            "to_class": to_class,
            "transition_height": transition_height,
            "reason": reason,
            "age_blocks": age_blocks,
            "executed_at": utc_now(),
        }
    )
