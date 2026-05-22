from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from pythia.scripts.publish_live_feed import _dedupe_live_candidates, _load_gamma_candidates


def _raw_market(idx: int, question: str | None = None) -> dict:
    return {
        "id": f"market-{idx}",
        "conditionId": f"0x{idx:064x}",
        "question": question or f"Will live imported market {idx} resolve yes?",
        "description": "Resolution comes from the official market page.",
        "outcomePrices": json.dumps(["0.42", "0.58"]),
        "volume24hr": "100000",
        "liquidity": "75000",
        "endDate": "2099-12-31T23:59:59Z",
        "tags": ["crypto"],
        "slug": f"live-imported-market-{idx}",
    }


class PublishLiveFeedTests(unittest.TestCase):
    def test_load_gamma_candidates_marks_import_as_live_not_fixture(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "gamma.json"
            path.write_text(json.dumps({"data": [_raw_market(1)]}))

            candidates = _load_gamma_candidates(path)

            self.assertEqual(len(candidates), 1)
            self.assertEqual(candidates[0].raw["data_mode"], "live_import")
            self.assertEqual(candidates[0].yes_price, 0.42)
            self.assertIn("polymarket.com/event/live-imported-market-1", candidates[0].raw["source_url"])

    def test_dedupe_rejects_fixture_markers_and_duplicate_questions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "gamma.json"
            duplicated = _raw_market(2, question="Same live question?")
            duplicate_question = _raw_market(3, question="Same live question?")
            path.write_text(json.dumps([_raw_market(1), duplicated, duplicate_question]))

            candidates = _load_gamma_candidates(path)
            candidates[0].raw["data_mode"] = "fixture"

            deduped = _dedupe_live_candidates(candidates)

            self.assertEqual([c.market_id for c in deduped], [duplicated["conditionId"]])

    def test_dedupe_rejects_expired_or_low_signal_markets(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "gamma.json"
            expired = _raw_market(1, question="Expired live market?")
            expired["endDate"] = "2025-01-01T00:00:00Z"
            low_signal = _raw_market(2, question="Will Jesus Christ return before GTA VI?")
            good = _raw_market(3, question="Will another live market resolve yes?")
            path.write_text(json.dumps([expired, low_signal, good]))

            deduped = _dedupe_live_candidates(_load_gamma_candidates(path))

            self.assertEqual([c.market_id for c in deduped], [good["conditionId"]])

    def test_dedupe_caps_repeated_template_clusters(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "gamma.json"
            raw = [
                _raw_market(1, question="Will Spain win the 2026 FIFA World Cup?"),
                _raw_market(2, question="Will England win the 2026 FIFA World Cup?"),
                _raw_market(3, question="Will France win the 2026 FIFA World Cup?"),
            ]
            path.write_text(json.dumps(raw))

            deduped = _dedupe_live_candidates(_load_gamma_candidates(path))

            self.assertEqual([c.market_id for c in deduped], [raw[0]["conditionId"], raw[1]["conditionId"]])


if __name__ == "__main__":
    unittest.main()
