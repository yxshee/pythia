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

    The default implementation is a deterministic heuristic so the loop runs
    end-to-end without an API key. When ``settings.anthropic_api_key`` is set, the
    analyst routes reasoning through Claude with a structured JSON output schema.
    """

    def __init__(self, settings: Settings):
        self._settings = settings
        self._client = None
        self._model = ""
        if settings.anthropic_api_key:
            try:
                import anthropic

                self._client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
                self._model = "claude-sonnet-4-6"
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
        """Deterministic fallback baseline. **Not for live trading.**

        Runs when no ``ANTHROPIC_API_KEY`` is configured or when the LLM call
        fails. Intentionally conservative: we only fire on deep-liquidity
        markets sitting at extreme prices, and even then we take a tiny
        mean-reversion bet. The LLM-driven analyst is the primary path.
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
            ReasoningStep("risk", "Heuristic-only fallback: confidence is artificially capped at 60%; the LLM analyst produces calibrated estimates when an API key is configured.")
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
        """Score the market via Claude with a forced JSON tool call.

        Uses the forced tool-use pattern: we declare a ``submit_analysis`` tool
        with a strict input_schema and pin ``tool_choice`` to it. Claude returns
        a single tool_use block whose ``input`` is guaranteed to match the schema.

        Falls back to the heuristic on any error (network, rate limit, schema
        mismatch). The heuristic is the safety net — failing closed is correct
        here because we publish paper picks, not execute trades.
        """
        system_prompt = (
            "You are Pythia, a prediction-market analyst. Your job: score one market "
            "for +EV and explain your reasoning concisely.\n\n"
            "Discipline:\n"
            "- HOLD is the default. Only BUY when you have a thesis the market is mispricing.\n"
            "- Confidence is calibrated, not promotional. 70%+ confidence means you would "
            "bet your own money. ~50% is essentially HOLD.\n"
            "- Edge below 200 bps after slippage is not worth the round-trip.\n"
            "- Liquidity below $25k is a hard pass — slippage eats the edge.\n"
            "- Produce 3-6 reasoning steps. Be specific: cite price, liquidity, catalyst.\n"
            "- `fair_price_yes` is YOUR probability YES resolves true (clamped 0.01-0.99). "
            "The market price is one data point among many.\n\n"
            "Always call the submit_analysis tool. Do not respond in prose."
        )
        user_prompt = (
            f"Market: {market.question}\n"
            f"Description: {market.description[:1200]}\n"
            f"Current YES price: {market.yes_price:.3f}  (NO: {market.no_price:.3f})\n"
            f"24h volume: ${market.volume_24h_usd:,.0f}\n"
            f"Liquidity: ${market.liquidity_usd:,.0f}\n"
            f"Resolves: {market.end_date_iso}\n"
            f"Tags: {', '.join(market.tags[:8])}\n\n"
            "Analyze and submit."
        )
        tool = {
            "name": "submit_analysis",
            "description": "Submit your structured analysis of this market.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "decision": {"type": "string", "enum": ["BUY_YES", "BUY_NO", "HOLD"]},
                    "confidence_bps": {
                        "type": "integer",
                        "minimum": 0,
                        "maximum": 10000,
                        "description": "Calibrated confidence, 0-10000 basis points (0-100%).",
                    },
                    "fair_price_yes": {
                        "type": "number",
                        "minimum": 0.01,
                        "maximum": 0.99,
                        "description": "Analyst's probability YES resolves true.",
                    },
                    "reasoning": {
                        "type": "array",
                        "minItems": 2,
                        "maxItems": 8,
                        "items": {
                            "type": "object",
                            "properties": {
                                "kind": {
                                    "type": "string",
                                    "enum": ["observation", "comparison", "inference", "risk", "conclusion"],
                                },
                                "text": {"type": "string", "maxLength": 600},
                            },
                            "required": ["kind", "text"],
                        },
                    },
                },
                "required": ["decision", "confidence_bps", "fair_price_yes", "reasoning"],
            },
        }
        try:
            resp = self._client.messages.create(
                model=self._model,
                max_tokens=2048,
                system=[
                    {
                        "type": "text",
                        "text": system_prompt,
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
                messages=[{"role": "user", "content": user_prompt}],
                tools=[tool],
                tool_choice={"type": "tool", "name": "submit_analysis"},
            )
            payload: dict | None = None
            for block in resp.content:
                if getattr(block, "type", None) == "tool_use" and getattr(block, "name", None) == "submit_analysis":
                    payload = block.input
                    break
            if payload is None:
                raise RuntimeError("no submit_analysis tool_use in response")
        except Exception as exc:  # noqa: BLE001 - heuristic is the safety net
            log.warning("analyst.llm_failed", error=str(exc), market_id=market.market_id)
            return self._score_heuristic(market)

        fair = max(0.01, min(0.99, float(payload["fair_price_yes"])))
        edge_bps = int(round((fair - market.yes_price) * 10_000))
        steps = [ReasoningStep(kind=s["kind"], text=s["text"]) for s in payload["reasoning"]]
        return AnalystReport(
            market_id=market.market_id,
            question=market.question,
            decision=payload["decision"],
            confidence_bps=max(0, min(10_000, int(payload["confidence_bps"]))),
            fair_price_yes=fair,
            edge_bps=edge_bps,
            reasoning=steps,
            model=self._model,
            generated_at=_now(),
        )


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
