"""Publisher: broadcast a TradePlan as a recommendation, never trade own capital.

Pythia is a *recommendation* agent. The publisher emits each actionable BUY pick
to Telegram + the web feed with a Polymarket deep-link that carries the current
placeholder builder-code query parameter (``?builderCode=pythia``). Production
fee attribution still requires a registered Polymarket V2 bytes32 builder code
attached in the order flow.

The agent's own track-record (the on-Arc PythiaVault NAV) is updated later by
``resolver.py`` once the underlying Polymarket question resolves - paper PnL
only, computed at the published position size.
"""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import quote

import structlog

from .config import Settings
from .pm import TradePlan
from .scout import MarketCandidate

log = structlog.get_logger(__name__)


@dataclass(slots=True)
class PublishResult:
    """Outcome of publishing one pick. No fills, ever - this is publish-only."""

    plan: TradePlan
    published: bool
    builder_code_link: str | None
    fallback_link: str
    error: str | None = None


class Publisher:
    """Emit picks to the broadcast surfaces with a placeholder trade link.

    The actual Telegram + web broadcast happens out-of-process via the bot
    subcommand ``pythia-bot broadcast <trace.json>``; this class formats the
    pick + link and emits the structured log line that downstream consumers
    read.
    """

    def __init__(self, settings: Settings):
        self._settings = settings

    def publish(self, plan: TradePlan, market: MarketCandidate) -> PublishResult:
        builder_link = self._builder_code_link(market, plan)
        fallback_link = self._fallback_link(market)
        log.info(
            "publisher.broadcast",
            market=plan.market_id[:10],
            decision=plan.decision,
            size=plan.size_usdc,
            confidence_bps=plan.confidence_bps,
            builder_link=builder_link,
        )
        # The actual Telegram + web broadcast happens out-of-process: the bot
        # subcommand `pythia-bot broadcast <trace.json>` reads the trace file
        # we just wrote and posts it. Decoupling keeps the loop fast.
        return PublishResult(
            plan=plan,
            published=True,
            builder_code_link=builder_link,
            fallback_link=fallback_link,
        )

    # ------------------------------------------------------------------
    #  Link construction
    # ------------------------------------------------------------------
    def _builder_code_link(self, market: MarketCandidate, plan: TradePlan) -> str:
        """Build the copy-trade URL for actionable BUY decisions.

        Polymarket exposes the market at ``polymarket.com/event/<slug>``. The
        current link includes a placeholder ``builderCode`` query parameter and a
        YES/NO side hint for the UI. HOLD recommendations deliberately return
        ``None`` so no downstream surface asks a user to copy a non-trade.
        """
        return copy_trade_url(market, plan.decision, self._settings.polymarket_builder_code)

    def _fallback_link(self, market: MarketCandidate) -> str:
        slug = self._extract_slug(market)
        return f"https://polymarket.com/event/{quote(slug, safe='')}"

    @staticmethod
    def _extract_slug(market: MarketCandidate) -> str:
        raw = market.raw or {}
        # Polymarket Gamma payloads typically expose `slug` at top level; some
        # endpoints nest it under `event` -> `slug`. Be tolerant.
        slug = raw.get("slug")
        if not slug:
            event = raw.get("event") or {}
            slug = event.get("slug")
        if not slug:
            # Last resort: the market id itself.
            slug = market.market_id
        return str(slug)

    @staticmethod
    def _side_for(plan: TradePlan) -> str:
        if plan.decision == "BUY_YES":
            return "yes"
        if plan.decision == "BUY_NO":
            return "no"
        raise ValueError(f"no Polymarket side for decision {plan.decision!r}")


def copy_trade_url(
    market: MarketCandidate,
    decision: str,
    builder_code: str | None,
) -> str | None:
    """Build the Polymarket copy-trade URL for a market + decision.

    Shared between :class:`Publisher` (the broadcast path) and the paid trace
    payload assembled in ``preview.to_full`` so the link the user clicks in the
    bot matches what is rendered in the web UI. Keeping a single source of
    truth here avoids the failure mode where the broadcast and unlocked content
    point users to different event URLs. Production attribution still requires
    a registered order-level builder code.
    """
    if decision == "HOLD":
        return None

    slug = Publisher._extract_slug(market)
    if decision == "BUY_YES":
        side = "yes"
    elif decision == "BUY_NO":
        side = "no"
    else:
        raise ValueError(f"unsupported copy-trade decision {decision!r}")
    code = builder_code or "pythia"
    return (
        f"https://polymarket.com/event/{quote(slug, safe='')}"
        f"?builderCode={quote(code, safe='')}&side={side}"
    )
