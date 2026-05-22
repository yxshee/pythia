from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from pythia.scripts.validate_submission import validate_repo


def _entry(trace_id: int, *, question: str | None = None, decision: str = "BUY_YES") -> dict:
    q = question or f"Will live market {trace_id} resolve yes?"
    return {
        "trace_id": trace_id,
        "generated_at": f"2026-05-23T00:{trace_id:02d}:00+00:00",
        "market_id": f"0x{trace_id:064x}",
        "model": "claude-sonnet-4-6",
        "theme": "crypto",
        "vault": None,
        "onchain": {
            "tx_hash": f"0x{trace_id:064x}",
            "block_number": trace_id,
            "trace_id": trace_id,
            "publisher": "0x0000000000000000000000000000000000000001",
            "contract": "0x0000000000000000000000000000000000000002",
            "chain_id": 5042002,
        },
        "preview": {
            "trace_id": trace_id,
            "trace_hash": f"0x{trace_id + 1:064x}",
            "market_id": f"0x{trace_id:064x}",
            "question": q,
            "current_implied_yes": 0.42,
            "agent_probability_yes": 0.48,
            "decision": decision,
            "confidence": "medium",
            "risk": "balanced",
            "model": "claude-sonnet-4-6",
            "generated_at": f"2026-05-23T00:{trace_id:02d}:00+00:00",
            "end_date_iso": "2026-12-31T23:59:59Z",
        },
    }


def _full_entry(trace_id: int, *, decision: str = "BUY_YES", fixture_source: bool = False) -> dict:
    entry = _entry(trace_id, decision=decision)
    entry["full"] = {
        **entry["preview"],
        "edge_bps": 600,
        "expected_value_pct": 4.2,
        "suggested_size_usdc": 12.0 if decision != "HOLD" else 0.0,
        "suggested_size_by_profile": {"conservative": 4.8, "balanced": 12.0, "aggressive": 19.2},
        "reasoning": [{"kind": "risk", "text": "Resolution timing can still surprise the market."}],
        "sources": [
            {"kind": "model", "name": "claude-sonnet-4-6", "observed_at": "2026-05-23T00:00:00+00:00"},
            {
                "kind": "market_data",
                "name": ("Offline market " + "fixture") if fixture_source else "Polymarket Gamma",
                "url": "https://polymarket.com/event/live-market",
                "observed_at": "2026-05-23T00:00:00+00:00",
            },
            {
                "kind": "resolution_criteria",
                "name": "Market resolution text",
                "url": "https://polymarket.com/event/live-market",
                "observed_at": "2026-05-23T00:00:00+00:00",
            },
        ],
        "risk_factors": ["Resolution timing can still surprise the market."],
        "market_url": "https://polymarket.com/event/live-market",
        "copy_trade_url": None if decision == "HOLD" else "https://polymarket.com/event/live-market?side=yes",
        "market_volume_24h_usd": 100_000,
        "market_liquidity_usd": 100_000,
    }
    return entry


class ValidateSubmissionTests(unittest.TestCase):
    def test_accepts_private_full_snapshot_and_public_preview_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "web" / "data").mkdir(parents=True)
            (root / "web" / "components").mkdir(parents=True)
            (root / "agent").mkdir()
            (root / "README.md").write_text("Public README")
            (root / "STATUS.md").write_text("Production paid traces are private.")
            (root / "docs").mkdir()

            preview = [_entry(i) for i in range(1, 9)]
            full = [_full_entry(i) for i in range(1, 9)]
            (root / "web" / "data" / "picks-preview.json").write_text(json.dumps(preview))
            (root / "web" / "data" / "picks-full.private.json").write_text(json.dumps(full))
            (root / "web" / "components" / "pick-card.tsx").write_text("Unlock 0.10 DevUSDC")

            self.assertEqual(validate_repo(root), [])

    def test_rejects_public_full_snapshot_fixture_source_wrong_dates_and_stale_copy(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "web" / "data").mkdir(parents=True)
            (root / "web" / "components").mkdir(parents=True)
            (root / "agent").mkdir()
            (root / "agent" / "fixtures.py").write_text("June " + "17-18 2026-06-" + "18")
            (root / "README.md").write_text("Public README")
            (root / "STATUS.md").write_text("Production paid traces are private.")
            (root / "docs").mkdir()

            preview = [_entry(i) for i in range(1, 9)]
            full = [_full_entry(i, fixture_source=i == 1) for i in range(1, 9)]
            (root / "web" / "data" / "picks-preview.json").write_text(json.dumps(preview))
            (root / "web" / "data" / "picks-full.json").write_text(json.dumps(full))
            (root / "web" / "components" / "pick-card.tsx").write_text("Unlock 0.10 " + "USDC")

            failures = validate_repo(root)

            self.assertTrue(any("public paid snapshot" in failure for failure in failures))
            self.assertTrue(any("fixture source" in failure for failure in failures))
            self.assertTrue(any("wrong FOMC" in failure for failure in failures))
            self.assertTrue(any("stale unlock-price copy" in failure for failure in failures))


if __name__ == "__main__":
    unittest.main()
