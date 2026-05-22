"""Scout: ingest candidate markets for the configured theme.

Reads from Polymarket's public Gamma API (no auth required for queries) and returns a
normalized list of ``MarketCandidate``s for the analyst to score.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import httpx
import structlog
from tenacity import retry, stop_after_attempt, wait_exponential

from .config import Settings

log = structlog.get_logger(__name__)


@dataclass(slots=True)
class MarketCandidate:
    """A Polymarket question reduced to the fields the agent reasons over."""

    market_id: str
    question: str
    description: str
    yes_price: float  # midpoint price 0..1
    no_price: float
    volume_24h_usd: float
    liquidity_usd: float
    end_date_iso: str
    tags: list[str]
    raw: dict[str, Any]  # full record for the analyst if it needs more context


class Scout:
    """Fetches and filters markets from Polymarket."""

    def __init__(self, settings: Settings, http: httpx.AsyncClient | None = None):
        self._settings = settings
        self._http = http or httpx.AsyncClient(
            base_url=settings.polymarket_gamma_url,
            timeout=httpx.Timeout(15.0),
            headers={"User-Agent": "pythia-agent/0.1"},
        )
        self._owns_client = http is None

    async def __aenter__(self) -> "Scout":
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        if self._owns_client:
            await self._http.aclose()

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
    async def _fetch_markets(self, *, limit: int = 50) -> list[dict[str, Any]]:
        params: dict[str, Any] = {
            "limit": limit,
            "active": "true",
            "closed": "false",
            "order": "volume_24hr",
            "ascending": "false",
        }
        # Polymarket Gamma's `tag_slug` only accepts canonical tags (e.g. `politics`,
        # `crypto`, `sports`). Compound themes like `crypto-politics` are ours -
        # we filter client-side on tags from the payload rather than rely on Gamma.
        theme = (self._settings.pythia_theme or "").strip().lower()
        if theme and "-" not in theme:
            params["tag_slug"] = theme
        resp = await self._http.get("/markets", params=params)
        resp.raise_for_status()
        payload = resp.json()
        if isinstance(payload, dict) and "data" in payload:
            return payload["data"]
        if isinstance(payload, list):
            return payload
        raise RuntimeError(f"unexpected gamma payload shape: {type(payload).__name__}")

    @staticmethod
    def _midpoint(raw: dict[str, Any]) -> tuple[float, float]:
        """Extract YES/NO midpoint prices, tolerating Polymarket's two payload shapes."""
        # Newer payloads expose `outcomePrices` as a JSON-encoded string list.
        prices = raw.get("outcomePrices")
        if isinstance(prices, str):
            try:
                import json

                arr = json.loads(prices)
                if isinstance(arr, list) and len(arr) >= 2:
                    return float(arr[0]), float(arr[1])
            except (ValueError, TypeError):
                pass
        # Legacy / fallback: `tokens` with `price` fields.
        tokens = raw.get("tokens") or []
        yes = no = 0.5
        for t in tokens:
            name = (t.get("outcome") or "").lower()
            price = float(t.get("price", 0.5) or 0.5)
            if name == "yes":
                yes = price
            elif name == "no":
                no = price
        return yes, no

    @staticmethod
    def _parse_end_date(value: Any) -> datetime | None:
        if not value:
            return None
        try:
            text = str(value).replace("Z", "+00:00")
            parsed = datetime.fromisoformat(text)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed
        except ValueError:
            return None

    async def discover(self, *, limit: int = 50) -> list[MarketCandidate]:
        """Return up to ``limit`` candidate markets for the configured theme."""
        raw_markets = await self._fetch_markets(limit=limit)
        out: list[MarketCandidate] = []
        observed_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        for raw in raw_markets:
            try:
                if raw.get("active") is False or raw.get("closed") or raw.get("archived"):
                    continue
                end_date = self._parse_end_date(raw.get("endDate") or raw.get("end_date_iso"))
                if end_date and end_date <= datetime.now(timezone.utc):
                    continue
                yes, no = self._midpoint(raw)
                slug = str(raw.get("slug") or (raw.get("event") or {}).get("slug") or raw.get("id") or "")
                enriched_raw = {
                    **raw,
                    "data_mode": "live",
                    "observed_at": observed_at,
                    "source_url": f"https://polymarket.com/event/{slug}" if slug else "https://polymarket.com",
                }
                candidate = MarketCandidate(
                    market_id=str(raw.get("conditionId") or raw.get("id") or raw.get("slug")),
                    question=str(raw.get("question") or raw.get("title") or ""),
                    description=str(raw.get("description") or "")[:2000],
                    yes_price=yes,
                    no_price=no,
                    volume_24h_usd=float(raw.get("volume24hr") or raw.get("volume_24hr") or raw.get("volumeNum") or 0.0),
                    liquidity_usd=float(raw.get("liquidity") or raw.get("liquidityNum") or 0.0),
                    end_date_iso=str(raw.get("endDate") or raw.get("end_date_iso") or ""),
                    tags=[str(t) for t in (raw.get("tags") or [])],
                    raw=enriched_raw,
                )
                out.append(candidate)
            except (KeyError, ValueError, TypeError) as exc:
                log.warning("scout.skip_market", reason=str(exc), market_keys=list(raw.keys())[:8])
        log.info("scout.discovered", count=len(out), theme=self._settings.pythia_theme)
        return out


async def _demo() -> None:
    """Smoke test: run from CLI to verify the Gamma API path works."""
    from .config import SETTINGS

    structlog.configure(processors=[structlog.dev.ConsoleRenderer()])
    async with Scout(SETTINGS) as scout:
        markets = await scout.discover(limit=10)
        for m in markets[:5]:
            print(f"{m.market_id[:10]}  yes={m.yes_price:.3f}  vol24h=${m.volume_24h_usd:>10,.0f}  {m.question[:80]}")


if __name__ == "__main__":
    asyncio.run(_demo())
