"""Preview / full split for Agora Alpha picks.

Every pick has two payloads:

  - **Preview** (always-free): enough to build trust + curiosity.
    Surfaced on the landing page, the Telegram channel, and the public web API.
    Includes: market question, current implied price, agent's headline
    probability, confidence label, risk label, Arc trace hash, decision.

  - **Full** (USDC-unlock-gated): the value-prop of paying.
    Includes: full reasoning chain, edge in bps, EV math, suggested position
    size per user risk profile, sources cited, risk factors, model + run ID.

The split is deliberately structural - one helper produces both shapes from a
single ``AnalystReport`` plus its ``MarketCandidate``, so the agent never has
to decide what to redact at publish time.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any, Literal

from .analyst import AnalystReport
from .pm import TradePlan
from .publisher import copy_trade_url
from .scout import MarketCandidate

RiskLabel = Literal["conservative", "balanced", "aggressive"]
ConfidenceLabel = Literal["low", "medium", "high"]


def _confidence_label(confidence_bps: int) -> ConfidenceLabel:
    if confidence_bps >= 6500:
        return "high"
    if confidence_bps >= 4500:
        return "medium"
    return "low"


def _risk_label(plan: TradePlan, market: MarketCandidate) -> RiskLabel:
    """Map plan size + market liquidity to a coarse risk label for the preview.

    Larger size and thinner liquidity = more aggressive. The exact bucketing
    here is intentionally simple; user-profile-aware sizing is future work.
    """
    size_fraction = plan.size_usdc / 50.0  # 50 is the default max position
    liq_ok = market.liquidity_usd >= 100_000
    if size_fraction >= 0.7 or not liq_ok:
        return "aggressive"
    if size_fraction >= 0.4:
        return "balanced"
    return "conservative"


def to_preview(
    report: AnalystReport,
    plan: TradePlan,
    market: MarketCandidate,
    *,
    trace_id: int | None = None,
    trace_hash: str | None = None,
) -> dict[str, Any]:
    """Free-tier preview surfaced everywhere. Safe to be public + indexed."""
    return {
        "trace_id": trace_id,
        "trace_hash": trace_hash,
        "market_id": report.market_id,
        "question": report.question,
        "current_implied_yes": round(market.yes_price, 4),
        "agent_probability_yes": round(report.fair_price_yes, 4),
        "decision": report.decision,
        "confidence": _confidence_label(report.confidence_bps),
        "risk": _risk_label(plan, market),
        "model": report.model,
        "generated_at": report.generated_at,
        "end_date_iso": market.end_date_iso,
    }


def to_full(
    report: AnalystReport,
    plan: TradePlan,
    market: MarketCandidate,
    *,
    trace_id: int | None = None,
    trace_hash: str | None = None,
    builder_code: str | None = None,
) -> dict[str, Any]:
    """Full unlocked payload. Served only to buyers who paid via UnlockMarket."""
    yes_price = max(0.01, min(0.99, market.yes_price))
    # Expected value as a fraction of the size (a unit-less proxy; the UI can
    # multiply by suggested_size_usdc to render dollars).
    if report.decision == "BUY_YES":
        ev = (report.fair_price_yes / yes_price) - 1.0
    elif report.decision == "BUY_NO":
        ev = ((1 - report.fair_price_yes) / (1 - yes_price)) - 1.0
    else:
        ev = 0.0

    market_url = f"https://polymarket.com/event/{market.raw.get('slug', market.market_id)}"
    observed_at = str(market.raw.get("observed_at") or report.generated_at)
    source_name = (
        "Synthetic fixture market data"
        if market.raw.get("data_mode") == "fixture"
        else "Polymarket Gamma"
    )
    source_url = str(market.raw.get("source_url") or market_url)
    risk_factors = [step.text for step in report.reasoning if step.kind == "risk"]
    if not risk_factors:
        risk_factors = [
            "Market resolution, liquidity, timing, and source quality can still move against the published thesis."
        ]

    return {
        **to_preview(report, plan, market, trace_id=trace_id, trace_hash=trace_hash),
        "edge_bps": report.edge_bps,
        "expected_value_pct": round(ev * 100, 3),
        "suggested_size_usdc": plan.size_usdc,
        "suggested_size_by_profile": {
            "conservative": round(plan.size_usdc * 0.4, 2),
            "balanced": round(plan.size_usdc * 1.0, 2),
            "aggressive": round(plan.size_usdc * 1.6, 2),
        },
        "reasoning": [asdict(step) for step in report.reasoning],
        "sources": [
            {"kind": "model", "name": report.model, "observed_at": report.generated_at},
            {
                "kind": "market_data",
                "name": source_name,
                "url": source_url,
                "observed_at": observed_at,
                "credibility": 0.7 if market.raw.get("data_mode") == "fixture" else 0.9,
            },
            {
                "kind": "resolution_criteria",
                "name": "Market resolution text",
                "url": market_url,
                "observed_at": observed_at,
                "description": market.description[:240],
            },
        ],
        "risk_factors": risk_factors,
        "market_url": market_url,
        "copy_trade_url": copy_trade_url(market, report.decision, builder_code),
        "market_volume_24h_usd": market.volume_24h_usd,
        "market_liquidity_usd": market.liquidity_usd,
    }
