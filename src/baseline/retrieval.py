from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass

from .database import BaselineDatabase


@dataclass
class QueryResult:
    found: bool
    latency_ms: float
    payload: dict[str, object] | None


class BaselineRetriever:
    def __init__(self, database: BaselineDatabase):
        self.database = database

    def by_txid_vout(self, txid: str, vout: int) -> QueryResult:
        started = time.perf_counter()
        row = self.database.get_output(txid, vout)
        latency = (time.perf_counter() - started) * 1000.0
        return QueryResult(found=row is not None, latency_ms=latency, payload=None if row is None else dict(row))

    def by_outpoint(self, outpoint: str) -> QueryResult:
        txid, vout_text = outpoint.split(":", 1)
        return self.by_txid_vout(txid, int(vout_text))

    def created_at_height(self, height: int) -> QueryResult:
        started = time.perf_counter()
        rows = [dict(row) for row in self.database.get_outputs_created_at(height)]
        latency = (time.perf_counter() - started) * 1000.0
        return QueryResult(found=bool(rows), latency_ms=latency, payload={"height": height, "outputs": rows})

    def spent_outputs(self) -> QueryResult:
        started = time.perf_counter()
        rows = [dict(row) for row in self.database.get_spent_outputs()]
        latency = (time.perf_counter() - started) * 1000.0
        return QueryResult(found=bool(rows), latency_ms=latency, payload={"outputs": rows})

    def unspent_outputs(self) -> QueryResult:
        started = time.perf_counter()
        rows = [dict(row) for row in self.database.get_unspent_outputs()]
        latency = (time.perf_counter() - started) * 1000.0
        return QueryResult(found=bool(rows), latency_ms=latency, payload={"outputs": rows})

    @staticmethod
    def to_json(result: QueryResult) -> str:
        return json.dumps(asdict(result), indent=2)
