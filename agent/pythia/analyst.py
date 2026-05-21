"""Analyst: score each candidate market for +EV using LLM reasoning.

The analyst produces both a decision and a *reasoning trace*. The trace is the product:
a structured record of why the agent thinks the position is +EV. It is later pinned to
IPFS and logged on Arc via ``trace.py``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal

import structlog

from .config import Settings
from .scout import MarketCandidate

log = structlog.get_logger(__name__)

DecisionLabel = Literal["BUY_YES", "BUY_NO", "HOLD"]


@dataclass(slots=True)
class ReasoningStep:
    """A single step in the analyst's chain of reasoning."""

    kind: Literal["observation", "comparison", "inference", "risk", "conclusion"]
    text: str


@dataclass(slots=True)
class AnalystReport:
    """Full analyst output for one market. Becomes the IPFS-pinned reasoning trace."""

    market_id: str
    question: str
    decision: DecisionLabel
    confidence_bps: int  # 0..10000
    fair_price_yes: float  # analyst's estimate of P(yes)
    edge_bps: int  # (fair - market) * 10000, signed
    reasoning: list[ReasoningStep] = field(default_factory=list)
    model: str = ""
    generated_at: str = ""

    def summary(self) -> str:
        return (
            f"{self.decision} {self.market_id[:10]} "
            f"@conf={self.confidence_bps / 100:.1f}% "
            f"edge={self.edge_bps / 100:+.2f}% "
            f"fair={self.fair_price_yes:.3f}"
        )


class Analyst:
    """Reasoning analyst.

    The default implementation in Day 1 is a deterministic heuristic so the loop runs
    end-to-end without an API key. When ``settings.anthropic_api_key`` is set, the
    analyst will route reasoning through Claude with a structured JSON output schema.
    """

    def __init__(self, settings: Settings):
        self._settings = settings
        self._client = None
        self._model = ""
        if settings.anthropic_api_key:
            try:
                import anthropic

                self._client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
                self._model = "claude-sonnet-4-5"
            except ImportError:
                log.warning("analyst.anthropic_unavailable")

    def score(self, market: MarketCandidate) -> AnalystReport:
        if self._client is not None:
            return self._score_with_llm(market)
        return self._score_heuristic(market)

    # ------------------------------------------------------------------
    #  Heuristic baseline - deterministic, runs without API keys
    # ------------------------------------------------------------------
    def _score_heuristic(self, market: MarketCandidate) -> AnalystReport:
        """Deterministic placeholder baseline. **Not for live trading.**

        This is intentionally conservative so Day-1 demo output is believable:
        we only fire on deep-liquidity markets sitting at extreme prices, and
        even then we take a tiny mean-reversion bet. The LLM-driven analyst
        on Day 3 replaces this entirely.
        """
        yes = max(0.01, min(0.99, market.yes_price))
        liq = market.liquidity_usd

        steps: list[ReasoningStep] = [
            ReasoningStep(
                "observation",
                f"Market YES price = {yes:.3f}; 24h volume = ${market.volume_24h_usd:,.0f}; liquidity = ${liq:,.0f}.",
            ),
        ]

        # Liquidity floor: thinner than this and round-trip slippage eats the edge.
        if liq < 25_000:
            steps.append(ReasoningStep("risk", "Liquidity below $25k; skipping to avoid slippage."))
            steps.append(ReasoningStep("conclusion", "HOLD."))
            return _hold(market, yes, steps)

        # Only act near the tails. Mid-range markets are noise for this placeholder.
        if 0.20 <= yes <= 0.80:
            steps.append(ReasoningStep("inference", "Price not extreme enough; no edge from this baseline."))
            steps.append(ReasoningStep("conclusion", "HOLD."))
            return _hold(market, yes, steps)

        # Tiny mean-reversion bet at the tails. Cap magnitude tightly.
        fair = 0.5 + (yes - 0.5) * 0.92  # very conservative pull toward 0.5
        edge = fair - yes
        edge_bps = int(round(edge * 10_000))

        if abs(edge_bps) < 200:
            steps.append(ReasoningStep("inference", "Edge < 200 bps after fair-price adjustment; not worth the round-trip."))
            steps.append(ReasoningStep("conclusion", "HOLD."))
            return _hold(market, fair, steps)

        decision: DecisionLabel = "BUY_YES" if edge_bps > 0 else "BUY_NO"
        # Modest confidence; the heuristic is not a real model.
        confidence_bps = min(6000, 3000 + abs(edge_bps) * 3)

        steps.append(
            ReasoningStep(
                "inference",
                f"Tail-of-distribution market; heuristic fair {fair:.3f} vs market {yes:.3f} -> {edge_bps:+d} bps.",
            )
        )
        steps.append(
            ReasoningStep("risk", "Placeholder model: confidence is artificially capped at 60% until the LLM analyst lands.")
        )
        steps.append(ReasoningStep("conclusion", f"Decision: {decision} @ conf={confidence_bps / 100:.1f}%"))

        return AnalystReport(
            market_id=market.market_id,
            question=market.question,
            decision=decision,
            confidence_bps=confidence_bps,
            fair_price_yes=fair,
            edge_bps=edge_bps,
            reasoning=steps,
            model="heuristic-v1-placeholder",
            generated_at=_now(),
        )

    # ------------------------------------------------------------------
    #  LLM-backed analyst (Claude)
    # ------------------------------------------------------------------
    def _score_with_llm(self, market: MarketCandidate) -> AnalystReport:
        """Route reasoning through Claude with a JSON-schema'd output.

        Wired up on Day 3 once the JSON schema settles. For Day 1 we fall back to the
        heuristic so the loop runs.
        """
        # TODO(day-3): structured output via tool_choice=auto + the AnalystReport schema.
        return self._score_heuristic(market)


def _hold(market: MarketCandidate, fair: float, steps: list[ReasoningStep]) -> AnalystReport:
    return AnalystReport(
        market_id=market.market_id,
        question=market.question,
        decision="HOLD",
        confidence_bps=0,
        fair_price_yes=fair,
        edge_bps=0,
        reasoning=steps,
        model="heuristic-v1-placeholder",
        generated_at=_now(),
    )


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
