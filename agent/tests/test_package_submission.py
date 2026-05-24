from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from scripts.package_submission import should_exclude  # noqa: E402


class PackageSubmissionTests(unittest.TestCase):
    def test_excludes_private_paid_traces_and_runtime_artifacts(self) -> None:
        excluded = [
            ".env",
            ".private/archive-traces/trace-000023.json",
            "submission.zip",
            "traces/trace-000023.json",
            "web/data/.blob-url",
            "web/data/picks-full.json",
            "web/data/picks-full.private.json",
            "web/node_modules/.modules.yaml",
            "web/.next/BUILD_ID",
            "web/.vercel/project.json",
            "agent/.venv/pyvenv.cfg",
            "contracts/cache/solidity-files-cache.json",
        ]

        for rel in excluded:
            with self.subTest(rel=rel):
                self.assertTrue(should_exclude(Path(rel), is_dir=False))

    def test_includes_public_deliverables(self) -> None:
        included = [
            ".env.example",
            "README.md",
            "STATUS.md",
            "VERIFY.md",
            "agent/pythia/scripts/publish_live_feed.py",
            "contracts/src/UnlockMarket.sol",
            "docs/POLYMARKET-INTEGRATION.md",
            "traces/sanitized-full-trace.example.json",
            "web/data/picks-preview.json",
            "web/app/page.tsx",
        ]

        for rel in included:
            with self.subTest(rel=rel):
                self.assertFalse(should_exclude(Path(rel), is_dir=False))

    def test_includes_audit_proof_files(self) -> None:
        # VERIFY.md and STATUS.md reference these files; if they don't ship in
        # the zip, the uploaded artifact contradicts its own sign-off.
        included = [
            ".github/workflows/ci.yml",
            "verify/screenshots/unlocked-trace.png",
            "verify/screenshots/explorer-tx.png",
        ]

        for rel in included:
            with self.subTest(rel=rel):
                self.assertFalse(should_exclude(Path(rel), is_dir=False))


if __name__ == "__main__":
    unittest.main()
