#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit("usage: validate_phase6.py <phase6_summary.json>")
    summary = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    status = summary.get("status", "FAIL")
    print(json.dumps({"status": status, "valid_pairs": summary.get("valid_pairs"), "invalid_pairs": summary.get("invalid_pairs")}, indent=2))
    return 0 if status in {"PASS", "PASS WITH WARNINGS"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
