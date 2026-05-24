from __future__ import annotations

import unittest

from pythia.scripts.validate_oracle_eval import summarize_eval, validate_eval_dataset


def _record(i: int, **overrides: object) -> dict[str, object]:
    outcome = i % 2 == 0
    decision = "BUY_YES" if outcome else "BUY_NO"
    record: dict[str, object] = {
        "market": f"Resolved long-tail market {i}",
        "vertical": "sports" if i < 15 else "politics",
        "scored_at": f"2026-01-{(i % 28) + 1:02d}T12:00:00Z",
        "market_probability_yes": 0.42,
        "agent_probability_yes": 0.58 if decision == "BUY_YES" else 0.33,
        "decision": decision,
        "outcome_yes": outcome,
        "resolved_at": f"2026-02-{(i % 28) + 1:02d}T12:00:00Z",
        "resolution_source_url": f"https://example.com/resolved/{i}",
        "reasoning_summary": "The agent cited market price, liquidity, and event-specific context.",
        "paper_pnl_usdc": 1.25,
    }
    record.update(overrides)
    return record


class OracleEvalTests(unittest.TestCase):
    def test_rejects_missing_twenty_market_backtest(self) -> None:
        records = [_record(i) for i in range(19)]

        failures = validate_eval_dataset(records)

        self.assertTrue(any("at least 20" in failure for failure in failures), failures)

    def test_requires_three_correct_sounding_wrong_examples(self) -> None:
        records = [_record(i) for i in range(20)]
        records[0].update(
            {
                "decision": "BUY_YES",
                "outcome_yes": False,
                "reasoning_sounded_right": "Historical home advantage sounded compelling.",
                "why_wrong": "The bracket path and injuries dominated the base-rate argument.",
                "policy_change": "Downweight generic historical trends when injury data is missing.",
            }
        )
        records[1].update(
            {
                "decision": "BUY_NO",
                "outcome_yes": True,
                "reasoning_sounded_right": "The model trusted a thin market's stale price.",
                "why_wrong": "Resolution criteria favored the opposite interpretation.",
                "policy_change": "Require explicit resolution-criteria contradiction checks.",
            }
        )

        failures = validate_eval_dataset(records)

        self.assertTrue(any("3 correct-sounding wrong" in failure for failure in failures), failures)

    def test_accepts_complete_dataset_and_summarizes_metrics(self) -> None:
        records = [_record(i) for i in range(20)]
        for i in range(3):
            records[i].update(
                {
                    "decision": "BUY_YES",
                    "outcome_yes": False,
                    "reasoning_sounded_right": f"Reasoning {i} sounded plausible before resolution.",
                    "why_wrong": f"Post-resolution review found missing source {i}.",
                    "policy_change": f"Policy change {i}.",
                    "paper_pnl_usdc": -2.0,
                }
            )

        failures = validate_eval_dataset(records)
        summary = summarize_eval(records)

        self.assertEqual(failures, [])
        self.assertEqual(summary["markets"], 20)
        self.assertGreaterEqual(summary["brier_score"], 0)
        self.assertIn("actionable_hit_rate", summary)
        self.assertIn("paper_pnl_usdc", summary)


if __name__ == "__main__":
    unittest.main()

