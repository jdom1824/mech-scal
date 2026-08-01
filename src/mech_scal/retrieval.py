from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass

from .database import MechScalDatabase


@dataclass
class QueryResult:
    found: bool
    latency_ms: float
    payload: dict[str, object] | list[dict[str, object]] | None


class MechScalRetriever:
    def __init__(self, database: MechScalDatabase):
        self.database = database

    def outpoint(self, txid: str, vout: int) -> QueryResult:
        started = time.perf_counter()
        row = self.database.get_output(txid, vout)
        latency = (time.perf_counter() - started) * 1000.0
        return QueryResult(found=row is not None, latency_ms=latency, payload=None if row is None else dict(row))

    def by_outpoint_text(self, outpoint: str) -> QueryResult:
        txid, vout = outpoint.split(":", 1)
        return self.outpoint(txid, int(vout))

    def by_class(self, class_name: str, final_only: bool = False) -> QueryResult:
        started = time.perf_counter()
        column = "final_class" if final_only else "current_class"
        rows = [dict(row) for row in self.database.conn.execute(f"SELECT * FROM outputs WHERE {column} = ? ORDER BY creation_height, txid, vout", (class_name,))]
        latency = (time.perf_counter() - started) * 1000.0
        return QueryResult(found=bool(rows), latency_ms=latency, payload=rows)

    def class_at_height(self, txid: str, vout: int, height: int) -> QueryResult:
        started = time.perf_counter()
        row = self.database.get_output(txid, vout)
        if row is None:
            latency = (time.perf_counter() - started) * 1000.0
            return QueryResult(found=False, latency_ms=latency, payload=None)
        transitions = list(
            self.database.conn.execute(
                "SELECT * FROM class_transitions WHERE txid = ? AND vout = ? AND transition_height <= ? ORDER BY transition_height, transition_id",
                (txid, vout, height),
            )
        )
        class_name = transitions[-1]["to_class"] if transitions else None
        latency = (time.perf_counter() - started) * 1000.0
        return QueryResult(found=class_name is not None, latency_ms=latency, payload={"txid": txid, "vout": vout, "height": height, "class": class_name})

    def transition_history(self, txid: str, vout: int) -> QueryResult:
        started = time.perf_counter()
        rows = [
            dict(row)
            for row in self.database.conn.execute(
                "SELECT * FROM class_transitions WHERE txid = ? AND vout = ? ORDER BY transition_height, transition_id",
                (txid, vout),
            )
        ]
        latency = (time.perf_counter() - started) * 1000.0
        return QueryResult(found=bool(rows), latency_ms=latency, payload=rows)

    def spent(self) -> QueryResult:
        started = time.perf_counter()
        rows = [dict(row) for row in self.database.conn.execute("SELECT * FROM outputs WHERE is_spent = 1 ORDER BY spend_height, txid, vout")]
        latency = (time.perf_counter() - started) * 1000.0
        return QueryResult(found=bool(rows), latency_ms=latency, payload=rows)

    def unspent(self) -> QueryResult:
        started = time.perf_counter()
        rows = [dict(row) for row in self.database.conn.execute("SELECT * FROM outputs WHERE is_spent = 0 ORDER BY creation_height, txid, vout")]
        latency = (time.perf_counter() - started) * 1000.0
        return QueryResult(found=bool(rows), latency_ms=latency, payload=rows)

    @staticmethod
    def to_json(result: QueryResult) -> str:
        return json.dumps(asdict(result), indent=2)
