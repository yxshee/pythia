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
    {
        "market_id": "0x5f6e1a2b3c4d5e6f7a8b9c0d1e2f3a4deeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee",
        "question": "Will the Fed cut rates by 25bps at the July 2026 meeting?",
        "description": "Resolves YES if the FOMC announces a 25bp rate cut at the July 29-30, 2026 meeting.",
        "yes_price": 0.31,
        "no_price": 0.69,
        "volume_24h_usd": 156_300.0,
        "liquidity_usd": 78_500.0,
        "end_date_iso": "2026-07-30T20:00:00Z",
        "tags": ["macro", "fed"],
        "slug": "fed-25bp-july-2026",
    },
    {
        "market_id": "0x6a1b9c8d7e6f5a4b3c2d1e0f9a8b7c6effffffffffffffffffffffffffffffff",
        "question": "Will Polymarket monthly active traders exceed 500k in Q3 2026?",
        "description": "Resolves YES if the Polymarket platform reports >=500,000 unique active addresses in any month during Q3 2026 (July-Sep).",
        "yes_price": 0.48,
        "no_price": 0.52,
        "volume_24h_usd": 67_200.0,
        "liquidity_usd": 44_500.0,
        "end_date_iso": "2026-09-30T23:59:59Z",
        "tags": ["crypto", "polymarket"],
        "slug": "polymarket-mau-500k-q3-2026",
    },
    {
        "market_id": "0x7c2d8e3f4a5b6c7d8e9f0a1b2c3d4e5f11111111111111111111111111111111",
        "question": "Will BTC trade above $120,000 on any day in Q4 2026?",
        "description": "Resolves YES if the daily high on Coinbase BTC/USD exceeds $120,000 on any day from 2026-10-01 to 2026-12-31.",
        "yes_price": 0.34,
        "no_price": 0.66,
        "volume_24h_usd": 712_400.0,
        "liquidity_usd": 283_000.0,
        "end_date_iso": "2026-12-31T23:59:59Z",
        "tags": ["crypto", "btc"],
        "slug": "btc-120k-q4-2026",
    },
    {
        "market_id": "0x8d3e4f5a6b7c8d9e0f1a2b3c4d5e6f7a22222222222222222222222222222222",
        "question": "Will US-listed ETH spot ETFs net >$1B inflows during Q3 2026?",
        "description": "Resolves YES if the sum of net inflows across all US-listed ETH spot ETFs from 2026-07-01 to 2026-09-30 exceeds $1.0B.",
        "yes_price": 0.58,
        "no_price": 0.42,
        "volume_24h_usd": 124_700.0,
        "liquidity_usd": 96_500.0,
        "end_date_iso": "2026-09-30T23:59:59Z",
        "tags": ["crypto", "eth", "etf"],
        "slug": "eth-etf-q3-2026-inflows",
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
