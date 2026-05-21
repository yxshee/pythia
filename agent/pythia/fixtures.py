"""Synthetic market fixtures for offline development.

Polymarket APIs (gamma, clob, polymarket.com) are geo-blocked from some networks
(notably India during early testing). To keep the agent loop runnable without
network access, ``--mock`` injects these fixtures in place of a live Scout fetch.

These shapes mirror real Gamma payloads closely enough that the rest of the
pipeline (analyst, pm, publisher, trace) cannot tell the difference.
"""

from __future__ import annotations

from .scout import MarketCandidate

_MOCK_MARKETS: list[dict] = [
    {
        "market_id": "0x84b7c95ee5c0c81b9b35d1f9c0e1b0c0aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        "question": "Will ETH close above $4,000 on May 31, 2026?",
        "description": "Resolves YES if the daily close on Coinbase ETH/USD on 2026-05-31 is >= $4,000.",
        "yes_price": 0.88,
        "no_price": 0.12,
        "volume_24h_usd": 412_400.0,
        "liquidity_usd": 185_000.0,
        "end_date_iso": "2026-05-31T23:59:59Z",
        "tags": ["crypto", "eth"],
        "slug": "eth-above-4000-may-31",
    },
    {
        "market_id": "0xa1c0e8d2def7b3b54f4d6f6d8b5a3f0bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
        "question": "Will the Fed cut rates by 25bps at the June 2026 meeting?",
        "description": "Resolves YES if the FOMC announces a 25bp rate cut at the June 17-18, 2026 meeting.",
        "yes_price": 0.42,
        "no_price": 0.58,
        "volume_24h_usd": 218_900.0,
        "liquidity_usd": 92_000.0,
        "end_date_iso": "2026-06-18T20:00:00Z",
        "tags": ["macro", "fed"],
        "slug": "fed-25bp-june-2026",
    },
    {
        "market_id": "0xf9c8a7b6d3e2f1a0b9c8d7e6f5a4b3c2cccccccccccccccccccccccccccccccc",
        "question": "Will BTC reach a new all-time high in 2026?",
        "description": "Resolves YES if BTC closes above its 2024 ATH on any day during calendar year 2026.",
        "yes_price": 0.16,
        "no_price": 0.84,
        "volume_24h_usd": 1_205_700.0,
        "liquidity_usd": 540_000.0,
        "end_date_iso": "2026-12-31T23:59:59Z",
        "tags": ["crypto", "btc"],
        "slug": "btc-new-ath-2026",
    },
    {
        "market_id": "0x4e3d2c1b0a9f8e7d6c5b4a3e2d1c0b9addddddddddddddddddddddddddddddddd",
        "question": "Will Polymarket V2 surpass $10B all-time volume by Dec 31, 2026?",
        "description": "Resolves YES if Polymarket's cumulative volume crosses $10B before 2027-01-01.",
        "yes_price": 0.55,
        "no_price": 0.45,
        "volume_24h_usd": 88_100.0,
        "liquidity_usd": 31_000.0,
        "end_date_iso": "2026-12-31T23:59:59Z",
        "tags": ["crypto", "polymarket"],
        "slug": "polymarket-10b-volume-2026",
    },
]


def mock_candidates() -> list[MarketCandidate]:
    """Return the offline market fixtures as MarketCandidate objects."""
    out: list[MarketCandidate] = []
    for raw in _MOCK_MARKETS:
        out.append(
            MarketCandidate(
                market_id=raw["market_id"],
                question=raw["question"],
                description=raw["description"],
                yes_price=raw["yes_price"],
                no_price=raw["no_price"],
                volume_24h_usd=raw["volume_24h_usd"],
                liquidity_usd=raw["liquidity_usd"],
                end_date_iso=raw["end_date_iso"],
                tags=raw["tags"],
                raw=raw,
            )
        )
    return out
