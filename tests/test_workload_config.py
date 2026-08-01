from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from workload.config import load_profiles  # noqa: E402


class WorkloadConfigTests(unittest.TestCase):
    def test_small_profile_counts(self) -> None:
        profiles = load_profiles(ROOT / "config" / "workload_profiles.json")
        small = profiles["small"]
        self.assertEqual(small.total_outputs, 75)
        self.assertEqual(small.threshold_blocks, 24)

    def test_threshold_override_updates_boundary_group(self) -> None:
        profiles = load_profiles(ROOT / "config" / "workload_profiles.json")
        updated = profiles["small"].with_threshold(30)
        boundary = next(group for group in updated.groups if group.name == "operational-boundary")
        self.assertEqual(boundary.spend_age_blocks, 30)


if __name__ == "__main__":
    unittest.main()
