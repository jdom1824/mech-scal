from __future__ import annotations

import json
import subprocess
from pathlib import Path


class RegtestRPC:
    def __init__(self, cli_script: Path, project_root: Path):
        self.cli_script = cli_script
        self.project_root = project_root

    def cli(self, *args: str, check: bool = True) -> str:
        completed = subprocess.run(
            [str(self.cli_script), *args],
            cwd=self.project_root,
            text=True,
            capture_output=True,
            check=False,
        )
        if check and completed.returncode != 0:
            raise RuntimeError(f"regtest_cli failed: {' '.join(args)}\n{completed.stderr.strip()}")
        return completed.stdout.strip()

    def cli_json(self, *args: str) -> dict[str, object] | list[object]:
        output = self.cli(*args)
        return json.loads(output)

    def ensure_chain(self) -> dict[str, object]:
        info = self.cli_json("getblockchaininfo")
        if info["chain"] != "regtest":
            raise RuntimeError(f"unexpected chain: {info['chain']}")
        return info

    def tx(self, txid: str) -> dict[str, object]:
        return self.cli_json("getrawtransaction", txid, "1")

    def block_header(self, blockhash: str) -> dict[str, object]:
        return self.cli_json("getblockheader", blockhash)
