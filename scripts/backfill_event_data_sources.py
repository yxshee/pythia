#!/usr/bin/env python3
"""Backfill the non-market `event_data` / `official_data` / `news` source on
existing entries in ``web/data/picks-full.private.json``.

Idempotent. Skips entries that already have a source whose ``kind`` is in
``_NON_MARKET_SOURCE_KINDS`` (event_data, news, sentiment, official_data).

Usage::

    python scripts/backfill_event_data_sources.py

The categorization logic mirrors ``pythia.preview._event_data_source`` and is
duplicated here intentionally so this one-off script does not need to import
the agent package or carry a Python dependency tail. Whenever the canonical
helper changes, copy the new categories into this script and re-run it (or
regenerate the snapshot from scratch via ``publish_live_feed.py``).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = REPO_ROOT / "web" / "data" / "picks-full.private.json"

_NON_MARKET_SOURCE_KINDS = frozenset({"event_data", "news", "sentiment", "official_data"})

_CATEGORIES: tuple[tuple[tuple[str, ...], dict[str, Any]], ...] = (
    (
        ("nba", "nfl", "nhl", "mlb", "ufc", "boxing", "tennis", "basketball", "hockey", "baseball"),
        {
            "kind": "official_data",
            "name": "Official league scoreboard / event feed",
            "url": "https://www.espn.com/",
            "credibility": 0.9,
        },
    ),
    (
        ("fifa", "world cup", "soccer", "champions league", "premier league", "uefa"),
        {
            "kind": "official_data",
            "name": "FIFA / UEFA official results",
            "url": "https://www.fifa.com/tournaments",
            "credibility": 0.92,
        },
    ),
    (
        ("bitcoin", "btc", "ethereum", "eth", "solana", "crypto", "stablecoin", "altcoin"),
        {
            "kind": "event_data",
            "name": "Centralized exchange price oracle (Binance / Coinbase reference)",
            "url": "https://www.binance.com/en/markets",
            "credibility": 0.88,
        },
    ),
    (
        ("fomc", "fed ", "federal reserve", "interest rate", "cpi", "inflation"),
        {
            "kind": "official_data",
            "name": "Federal Reserve calendar + FOMC statements",
            "url": "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm",
            "credibility": 0.96,
        },
    ),
    (
        ("election", "primary", "senate", "house", "president", "congress", "governor"),
        {
            "kind": "official_data",
            "name": "Associated Press election results + state election boards",
            "url": "https://apnews.com/hub/election-2024",
            "credibility": 0.93,
        },
    ),
    (
        ("treaty", "peace", "ceasefire", "diplomatic", "summit", "g7", "g20", "un security"),
        {
            "kind": "news",
            "name": "Reuters / AP wire on diplomatic events",
            "url": "https://www.reuters.com/world/",
            "credibility": 0.85,
        },
    ),
)

_FALLBACK: dict[str, Any] = {
    "kind": "event_data",
    "name": "Polymarket resolution policy + UMA optimistic oracle",
    "url": "https://docs.polymarket.com/polymarket-learn/resolutions",
    "credibility": 0.85,
}


def _event_data_source(question: str, observed_at: str) -> dict[str, Any]:
    haystack = question.lower()
    for needles, source in _CATEGORIES:
        if any(needle in haystack for needle in needles):
            return {
                **source,
                "observed_at": observed_at,
                "relevance": 0.9,
                "recency": 0.85,
            }
    return {
        **_FALLBACK,
        "observed_at": observed_at,
        "relevance": 0.8,
        "recency": 0.85,
    }


def main() -> int:
    if not SNAPSHOT.exists():
        print(f"FAIL: {SNAPSHOT.relative_to(REPO_ROOT)} not present", file=sys.stderr)
        return 1

    entries = json.loads(SNAPSHOT.read_text())
    patched = 0
    for entry in entries:
        full = entry.get("full") or {}
        sources = full.get("sources") or []
        kinds = {str(s.get("kind") or "") for s in sources if isinstance(s, dict)}
        if _NON_MARKET_SOURCE_KINDS & kinds:
            continue
        question = str((entry.get("preview") or {}).get("question") or "")
        observed_at = str(entry.get("generated_at") or "2026-05-23T00:00:00+00:00")
        sources.append(_event_data_source(question, observed_at))
        full["sources"] = sources
        entry["full"] = full
        patched += 1

    SNAPSHOT.write_text(json.dumps(entries, indent=2, sort_keys=False) + "\n")
    print(f"backfilled {patched}/{len(entries)} entries with non-market source")
    return 0


if __name__ == "__main__":
    sys.exit(main())
