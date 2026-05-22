"""Portfolio Manager: sizing, risk limits, and the final go/no-go on each pick.

The PM consumes ``AnalystReport``s and decides which picks to publish, the
hypothetical position size in USDC, and what exit conditions to set. Sizing is
against a virtual ``paper_capital_usdc`` (no real funds at risk); per-position
size is capped by ``pythia_max_position_usdc`` and the daily pick count by
``pythia_daily_max_trades``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import structlog

from .analyst import AnalystReport, DecisionLabel
from .config import Settings

log = structlog.get_logger(__name__)


@dataclass(slots=True)
class TradePlan:
    """A sized, ready-to-execute decision."""

    market_id: str
    question: str
    decision: DecisionLabel
    size_usdc: float
    confidence_bps: int
    edge_bps: int
    parent_trace_id: int = 0  # 0 for new threads


class PortfolioManager:
    """Risk + sizing layer between analyst output and execution."""

    def __init__(self, settings: Settings):
        self._settings = settings
        self._today: date = date.today()
        self._trades_today: int = 0

    # ------------------------------------------------------------------
    #  Public API
    # ------------------------------------------------------------------
    def plan(self, reports: list[AnalystReport]) -> list[TradePlan]:
        self._maybe_roll_day()
        # Sort by confidence * |edge| - rough proxy for expected USDC PnL per dollar risked.
        ranked = sorted(reports, key=self._score, reverse=True)
        plans: list[TradePlan] = []
        for r in ranked:
            if r.decision == "HOLD":
                continue
            if self._trades_today >= self._settings.pythia_daily_max_trades:
                log.info("pm.daily_cap_reached", cap=self._settings.pythia_daily_max_trades)
                break
            size = self._size(r)
            if size <= 0:
                continue
            plans.append(
                TradePlan(
                    market_id=r.market_id,
                    question=r.question,
                    decision=r.decision,
                    size_usdc=size,
                    confidence_bps=r.confidence_bps,
                    edge_bps=r.edge_bps,
                )
            )
            self._trades_today += 1
        log.info("pm.planned", count=len(plans), trades_today=self._trades_today)
        return plans

    # ------------------------------------------------------------------
    #  Internals
    # ------------------------------------------------------------------
    @staticmethod
    def _score(r: AnalystReport) -> float:
        return (r.confidence_bps / 10_000.0) * abs(r.edge_bps)

    def _size(self, r: AnalystReport) -> float:
        """Linear sizing in confidence; capped by max position env."""
        # 3500 bps (35%) is a deliberately low confidence floor; below this we skip.
        if r.confidence_bps < 3500:
            return 0.0
        confidence = r.confidence_bps / 10_000.0
        max_pos = self._settings.pythia_max_position_usdc
        return round(max_pos * confidence, 2)

    def _maybe_roll_day(self) -> None:
        today = date.today()
        if today != self._today:
            self._today = today
            self._trades_today = 0
