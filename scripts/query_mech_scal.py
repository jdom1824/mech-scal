#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

LOCAL_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(LOCAL_ROOT / "src"))

from mech_scal.database import MechScalDatabase  # noqa: E402
from mech_scal.retrieval import MechScalRetriever  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Query the Mech-Scal SQLite database.")
    parser.add_argument("--database", required=True)
    parser.add_argument("--outpoint")
    parser.add_argument("--class-name")
    parser.add_argument("--final-class")
    parser.add_argument("--class-at-height")
    parser.add_argument("--history")
    parser.add_argument("--spent", action="store_true")
    parser.add_argument("--unspent", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    database = MechScalDatabase(Path(args.database))
    try:
        database.init_schema()
        retriever = MechScalRetriever(database)
        if args.outpoint:
            print(MechScalRetriever.to_json(retriever.by_outpoint_text(args.outpoint)))
        elif args.class_name:
            print(MechScalRetriever.to_json(retriever.by_class(args.class_name)))
        elif args.final_class:
            print(MechScalRetriever.to_json(retriever.by_class(args.final_class, final_only=True)))
        elif args.class_at_height:
            outpoint, height = args.class_at_height.split("@", 1)
            txid, vout = outpoint.split(":", 1)
            print(MechScalRetriever.to_json(retriever.class_at_height(txid, int(vout), int(height))))
        elif args.history:
            txid, vout = args.history.split(":", 1)
            print(MechScalRetriever.to_json(retriever.transition_history(txid, int(vout))))
        elif args.spent:
            print(MechScalRetriever.to_json(retriever.spent()))
        elif args.unspent:
            print(MechScalRetriever.to_json(retriever.unspent()))
        else:
            raise SystemExit("no query option provided")
    finally:
        database.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
