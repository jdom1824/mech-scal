from __future__ import annotations

import csv
import json
from pathlib import Path


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def write_latex_table(path: Path, headers: list[str], rows: list[list[str]]) -> None:
    lines = ["\\begin{tabular}{" + "l" * len(headers) + "}", "\\hline", " & ".join(headers) + " \\\\", "\\hline"]
    for row in rows:
        lines.append(" & ".join(row) + " \\\\")
    lines.extend(["\\hline", "\\end{tabular}"])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_phase6_outputs(base_dir: Path, artifacts: dict[str, list[dict[str, object]]], summary: dict[str, object]) -> None:
    for name, rows in artifacts.items():
        write_csv(base_dir / name, rows)
    write_json(base_dir / "phase6_summary.json", summary)
