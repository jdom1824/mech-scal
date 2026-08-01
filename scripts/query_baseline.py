#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

LOCAL_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(LOCAL_ROOT / "src"))

from baseline.database import BaselineDatabase  # noqa: E402
from baseline.retrieval import BaselineRetriever  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Query the baseline SQLite database.")
    parser.add_argument("--database", required=True)
    parser.add_argument("--txid")
    parser.add_argument("--vout", type=int)
    parser.add_argument("--outpoint")
    parser.add_argument("--created-height", type=int)
    parser.add_argument("--spent", action="store_true")
    parser.add_argument("--unspent", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    database = BaselineDatabase(Path(args.database))
    try:
        database.init_schema()
        retriever = BaselineRetriever(database)
        if args.outpoint:
            print(BaselineRetriever.to_json(retriever.by_outpoint(args.outpoint)))
        elif args.txid and args.vout is not None:
            print(BaselineRetriever.to_json(retriever.by_txid_vout(args.txid, args.vout)))
        elif args.created_height is not None:
            print(BaselineRetriever.to_json(retriever.created_at_height(args.created_height)))
        elif args.spent:
            print(BaselineRetriever.to_json(retriever.spent_outputs()))
        elif args.unspent:
            print(BaselineRetriever.to_json(retriever.unspent_outputs()))
        else:
            raise SystemExit("no query option provided")
    finally:
        database.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
