from __future__ import annotations

import unittest

from pythia.analyst import AnalystReport, ReasoningStep
from pythia.pm import TradePlan
from pythia.preview import to_full, to_preview
from pythia.publisher import copy_trade_url
from pythia.scout import MarketCandidate


def _market() -> MarketCandidate:
    return MarketCandidate(
        market_id="0xabc",
        question="Will the demo market resolve yes?",
        description="Resolution source is the official market page.",
        yes_price=0.42,
        no_price=0.58,
        volume_24h_usd=125_000,
        liquidity_usd=80_000,
        end_date_iso="2026-12-31T23:59:59Z",
        tags=["demo"],
        raw={
            "slug": "demo-market",
            "data_mode": "fixture",
            "observed_at": "2026-05-22T00:00:00Z",
            "source_url": "https://polymarket.com/event/demo-market",
        },
    )


class PublisherPayloadTests(unittest.TestCase):
    def test_hold_decision_has_no_copy_trade_url(self) -> None:
        self.assertIsNone(copy_trade_url(_market(), "HOLD", "pythia"))

    def test_buy_decisions_include_side_hint(self) -> None:
        market = _market()

        self.assertIn("&side=yes", copy_trade_url(market, "BUY_YES", "pythia") or "")
        self.assertIn("&side=no", copy_trade_url(market, "BUY_NO", "pythia") or "")

    def test_full_payload_hides_copy_trade_for_hold_and_includes_source_bundle(self) -> None:
        market = _market()
        report = AnalystReport(
            market_id=market.market_id,
            question=market.question,
            decision="HOLD",
            confidence_bps=0,
            fair_price_yes=0.43,
            edge_bps=0,
            reasoning=[
                ReasoningStep("observation", "The market is close to fair value."),
                ReasoningStep("risk", "Liquidity and timing do not justify action."),
                ReasoningStep("conclusion", "HOLD."),
            ],
            model="test-model",
            generated_at="2026-05-22T00:01:00Z",
            liquidity_usd=market.liquidity_usd,
        )
        plan = TradePlan(
            market_id=market.market_id,
            question=market.question,
            decision="HOLD",
            size_usdc=0.0,
            confidence_bps=0,
            edge_bps=0,
        )

        full = to_full(report, plan, market, trace_id=1, trace_hash="0x123", builder_code="pythia")

        self.assertIsNone(full["copy_trade_url"])
        self.assertGreaterEqual(len(full["sources"]), 3)
        self.assertTrue(any(source.get("observed_at") for source in full["sources"] if isinstance(source, dict)))
        self.assertGreaterEqual(len(full["risk_factors"]), 1)

    def test_preview_payload_never_includes_builder_code(self) -> None:
        market = _market()
        report = AnalystReport(
            market_id=market.market_id,
            question=market.question,
            decision="BUY_YES",
            confidence_bps=5000,
            fair_price_yes=0.5,
            edge_bps=800,
            reasoning=[ReasoningStep("observation", "ok")],
            model="test-model",
            generated_at="2026-05-22T00:01:00Z",
            liquidity_usd=market.liquidity_usd,
        )
        plan = TradePlan(
            market_id=market.market_id,
            question=market.question,
            decision="BUY_YES",
            size_usdc=10.0,
            confidence_bps=5000,
            edge_bps=800,
        )

        preview = to_preview(report, plan, market, trace_id=1, trace_hash="0x123")

        self.assertNotIn("builder_code", preview)

    def test_full_payload_adds_default_risk_factor_when_reasoning_has_no_risk_step(self) -> None:
        market = _market()
        report = AnalystReport(
            market_id=market.market_id,
            question=market.question,
            decision="BUY_YES",
            confidence_bps=5000,
            fair_price_yes=0.5,
            edge_bps=800,
            reasoning=[
                ReasoningStep("observation", "The market is liquid enough to analyze."),
                ReasoningStep("conclusion", "BUY_YES."),
            ],
            model="test-model",
            generated_at="2026-05-22T00:01:00Z",
            liquidity_usd=market.liquidity_usd,
        )
        plan = TradePlan(
            market_id=market.market_id,
            question=market.question,
            decision="BUY_YES",
            size_usdc=10.0,
            confidence_bps=5000,
            edge_bps=800,
        )

        full = to_full(report, plan, market, trace_id=1, trace_hash="0x123", builder_code="pythia")

        self.assertGreaterEqual(len(full["risk_factors"]), 1)


if __name__ == "__main__":
    unittest.main()
