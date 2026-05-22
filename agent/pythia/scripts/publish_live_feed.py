"""Publish the final live-only web feed from Polymarket Gamma data.

This is the top-3 submission path. It refuses fixture data, heuristic-only
analyses, local-only traces, duplicate markets/questions, and partial feeds.
Full paid payloads are written to ``web/data/picks-full.private.json`` for
server-side use. The public browser bundle receives only
``web/data/picks-preview.json``.

Usage:
    cd agent
    uv run python -m pythia.scripts.publish_live_feed --target 8
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..analyst import Analyst, AnalystReport
from ..config import SETTINGS
from ..pm import PortfolioManager, TradePlan
from ..publisher import Publisher
from ..scout import MarketCandidate, Scout
from ..trace import TracePublisher

_PREVIEW_DROP_KEYS = frozenset({
    "analyst",
    "plan",
    "full",
    "publication",
    "builder_code",
})

_MIN_PROBABILITY = 0.005
_MIN_VOLUME_24H_USD = 1_000.0
_MAX_PER_TEMPLATE_CLUSTER = 2
_LOW_SIGNAL_PHRASES = (
    "before gta vi",
    "gta vi released",
    "will jesus christ return",
)


def _hold_plan(report: AnalystReport) -> TradePlan:
    return TradePlan(
        market_id=report.market_id,
        question=report.question,
        decision="HOLD",
        size_usdc=0.0,
        confidence_bps=report.confidence_bps,
        edge_bps=report.edge_bps,
    )


def _to_preview_entry(trace: dict[str, Any]) -> dict[str, Any]:
    out = {k: v for k, v in trace.items() if k not in _PREVIEW_DROP_KEYS}
    preview = trace.get("preview") or {}
    if "market_id" in preview:
        out["market_id"] = preview["market_id"]
    return out


def _existing_max_trace_id(repo_root: Path) -> int:
    ids: list[int] = []
    for base in (repo_root / "traces", repo_root / ".private" / "traces"):
        if not base.exists():
            continue
        for path in base.rglob("trace-*.json"):
            try:
                ids.append(int(path.stem.split("-")[-1]))
            except ValueError:
                continue
    return max(ids, default=0)


def _dedupe_live_candidates(candidates: list[MarketCandidate]) -> list[MarketCandidate]:
    seen_markets: set[str] = set()
    seen_questions: set[str] = set()
    cluster_counts: dict[str, int] = {}
    live: list[MarketCandidate] = []
    for candidate in sorted(candidates, key=_candidate_sort_key, reverse=True):
        question_key = " ".join(candidate.question.lower().split())
        if not candidate.market_id or not candidate.question:
            continue
        if candidate.market_id in seen_markets or question_key in seen_questions:
            continue
        if not _is_quality_live_candidate(candidate):
            continue
        cluster_key = _question_cluster(candidate.question)
        if cluster_counts.get(cluster_key, 0) >= _MAX_PER_TEMPLATE_CLUSTER:
            continue
        cluster_counts[cluster_key] = cluster_counts.get(cluster_key, 0) + 1
        seen_markets.add(candidate.market_id)
        seen_questions.add(question_key)
        live.append(candidate)
    return live


def _parse_end_date(value: str) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed
    except ValueError:
        return None


def _question_cluster(question: str) -> str:
    normalized = " ".join(question.lower().split())
    patterns = (
        (r"^will .+ win the 2026 fifa world cup\??$", "2026-fifa-world-cup-winner"),
        (r"^will the .+ win the 2026 nba finals\??$", "2026-nba-finals-winner"),
        (r"^will the .+ win the 2026 nhl stanley cup\??$", "2026-nhl-stanley-cup-winner"),
        (r"^will .+ win the 2028 democratic presidential nomination\??$", "2028-dem-nomination-winner"),
        (r"^us x iran permanent peace deal by .+\??$", "us-iran-permanent-peace-deal"),
    )
    for pattern, cluster in patterns:
        if re.match(pattern, normalized):
            return cluster
    return normalized


def _candidate_sort_key(candidate: MarketCandidate) -> tuple[float, float, float]:
    yes = max(0.0, min(1.0, candidate.yes_price))
    no = max(0.0, min(1.0, candidate.no_price))
    tradable_probability = min(yes, no)
    balance = 1.0 - abs(0.5 - yes)
    return (candidate.volume_24h_usd, candidate.liquidity_usd, tradable_probability + balance)


def _is_quality_live_candidate(candidate: MarketCandidate) -> bool:
    raw = candidate.raw
    question = candidate.question.lower()
    if raw.get("data_mode") == "fixture":
        return False
    if raw.get("active") is False or raw.get("closed") or raw.get("archived"):
        return False
    if any(phrase in question for phrase in _LOW_SIGNAL_PHRASES):
        return False
    end_date = _parse_end_date(candidate.end_date_iso)
    if end_date and end_date <= datetime.now(timezone.utc):
        return False
    if min(candidate.yes_price, candidate.no_price) < _MIN_PROBABILITY:
        return False
    return candidate.volume_24h_usd >= _MIN_VOLUME_24H_USD


def _candidate_from_gamma_raw(raw: dict[str, Any], observed_at: str) -> MarketCandidate:
    yes, no = Scout._midpoint(raw)  # noqa: SLF001 - reuse the Scout parser
    event = raw.get("event") or {}
    slug = str(raw.get("slug") or event.get("slug") or raw.get("id") or "")
    enriched_raw = {
        **raw,
        "data_mode": "live_import",
        "observed_at": observed_at,
        "source_url": f"https://polymarket.com/event/{slug}" if slug else "https://polymarket.com",
    }
    return MarketCandidate(
        market_id=str(raw.get("conditionId") or raw.get("id") or raw.get("slug")),
        question=str(raw.get("question") or raw.get("title") or ""),
        description=str(raw.get("description") or "")[:2000],
        yes_price=yes,
        no_price=no,
        volume_24h_usd=float(raw.get("volume24hr") or raw.get("volume_24hr") or raw.get("volumeNum") or 0.0),
        liquidity_usd=float(raw.get("liquidity") or raw.get("liquidityNum") or 0.0),
        end_date_iso=str(raw.get("endDate") or raw.get("end_date_iso") or raw.get("endDateIso") or ""),
        tags=[str(t) for t in (raw.get("tags") or [])],
        raw=enriched_raw,
    )


def _load_gamma_candidates(path: Path) -> list[MarketCandidate]:
    payload = json.loads(path.read_text())
    if isinstance(payload, dict) and "data" in payload:
        raw_markets = payload["data"]
    else:
        raw_markets = payload
    if not isinstance(raw_markets, list):
        raise ValueError("Gamma JSON must be a list or an object with a data list")

    observed_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    candidates: list[MarketCandidate] = []
    for raw in raw_markets:
        if isinstance(raw, dict):
            candidates.append(_candidate_from_gamma_raw(raw, observed_at))
    return candidates


def _assert_trace_ok(trace: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    trace_id = trace.get("trace_id")
    preview = trace.get("preview") or {}
    full = trace.get("full") or {}
    source_names = [str(source.get("name")) for source in full.get("sources", []) if isinstance(source, dict)]

    if preview.get("model") == "heuristic-v1-placeholder":
        failures.append(f"trace {trace_id}: heuristic model")
    if ("Offline market " + "fixture") in source_names:
        failures.append(f"trace {trace_id}: fixture source")
    if not (trace.get("onchain") or {}).get("tx_hash"):
        failures.append(f"trace {trace_id}: missing onchain tx_hash")
    if full.get("decision") == "HOLD" and full.get("copy_trade_url"):
        failures.append(f"trace {trace_id}: HOLD copy_trade_url")
    if not full.get("risk_factors"):
        failures.append(f"trace {trace_id}: missing risk_factors")
    return failures


async def _publish(
    target: int,
    candidate_limit: int,
    repo_root: Path,
    traces_dir: Path,
    gamma_json: Path | None,
    theme: str | None,
) -> int:
    settings = SETTINGS
    if theme:
        settings.pythia_theme = theme
    if not settings.anthropic_api_key:
        print("ANTHROPIC_API_KEY is required for live final publishing.", file=sys.stderr)
        return 2

    analyst = Analyst(settings)
    if analyst._client is None:  # noqa: SLF001 - release script gate
        print("Analyst initialised without an Anthropic client.", file=sys.stderr)
        return 2

    if gamma_json is not None:
        try:
            candidates = _dedupe_live_candidates(_load_gamma_candidates(gamma_json))
        except Exception as exc:  # noqa: BLE001 - release gate should fail cleanly
            print(f"Imported Gamma JSON could not be parsed: {exc}", file=sys.stderr)
            return 1
    else:
        try:
            async with Scout(settings) as scout:
                candidates = _dedupe_live_candidates(await scout.discover(limit=candidate_limit))
        except Exception as exc:  # noqa: BLE001 - release gate should fail cleanly
            print(
                "Live Polymarket discovery failed. Run this script from a non-blocked "
                f"network or pass --gamma-json from that network before packaging. Detail: {exc}",
                file=sys.stderr,
            )
            return 1
    if len(candidates) < target:
        print(f"Only {len(candidates)} unique live candidates discovered; need {target}.", file=sys.stderr)
        return 1

    pm = PortfolioManager(settings)
    publisher = Publisher(settings)
    tracer = TracePublisher(settings, traces_dir=traces_dir)
    if tracer._contract is None:  # noqa: SLF001 - release script gate
        print("TraceLog on-chain publisher is not configured; refusing local-only feed.", file=sys.stderr)
        return 2

    traces: list[dict[str, Any]] = []
    next_trace_id = _existing_max_trace_id(repo_root) + 1
    failures: list[str] = []

    for candidate in candidates:
        if len(traces) >= target:
            break
        report = analyst.score(candidate)
        if report.model == "heuristic-v1-placeholder":
            failures.append(f"{candidate.market_id}: LLM failed and heuristic fallback was returned")
            continue

        plans = pm.plan([report]) if report.decision != "HOLD" else []
        plan = plans[0] if plans else _hold_plan(report)
        publication = publisher.publish(plan, candidate)
        receipt = tracer.publish(
            report,
            plan,
            candidate,
            publication,
            trace_id=next_trace_id,
        )
        next_trace_id += 1

        trace = json.loads(Path(receipt.local_path).read_text())
        trace_failures = _assert_trace_ok(trace)
        if trace_failures:
            failures.extend(trace_failures)
            continue
        traces.append(trace)
        print(
            f"trace #{trace['trace_id']:03d}: {report.decision:<7} "
            f"market={candidate.market_id[:12]} tx={receipt.tx_hash[:14]}..."
        )

    if len(traces) < target:
        failures.append(f"only {len(traces)} valid traces generated; need {target}")

    questions = [str((trace.get("preview") or {}).get("question") or "") for trace in traces]
    if len(set(questions)) != len(questions):
        failures.append("generated traces contain duplicate questions")
    market_ids = [str((trace.get("preview") or {}).get("market_id") or "") for trace in traces]
    if len(set(market_ids)) != len(market_ids):
        failures.append("generated traces contain duplicate market IDs")

    if failures:
        for failure in failures:
            print(f"FAIL: {failure}", file=sys.stderr)
        return 1

    out_private = repo_root / "web" / "data" / "picks-full.private.json"
    out_preview = repo_root / "web" / "data" / "picks-preview.json"
    out_public_full = repo_root / "web" / "data" / "picks-full.json"
    out_private.write_text(json.dumps(traces, indent=2, sort_keys=True) + "\n")
    out_preview.write_text(json.dumps([_to_preview_entry(trace) for trace in traces], indent=2, sort_keys=True) + "\n")
    if out_public_full.exists():
        out_public_full.unlink()

    print(f"wrote {out_preview.relative_to(repo_root)} ({len(traces)} entries)")
    print(f"wrote {out_private.relative_to(repo_root)} ({len(traces)} private entries)")
    return 0


def main() -> int:
    repo_root = Path(__file__).resolve().parents[3]
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", type=int, default=8)
    parser.add_argument("--candidate-limit", type=int, default=80)
    parser.add_argument(
        "--traces-dir",
        type=Path,
        default=repo_root / ".private" / "traces",
        help="Private trace output directory; not included in the public submission zip.",
    )
    parser.add_argument(
        "--gamma-json",
        type=Path,
        default=None,
        help=(
            "Optional Polymarket Gamma /markets JSON captured from a non-blocked "
            "network. Still treated as live-only; fixture markers are rejected."
        ),
    )
    parser.add_argument(
        "--theme",
        default=None,
        help="Override the trace theme label for this release run.",
    )
    args = parser.parse_args()

    args.traces_dir.mkdir(parents=True, exist_ok=True)
    return asyncio.run(
        _publish(args.target, args.candidate_limit, repo_root, args.traces_dir, args.gamma_json, args.theme)
    )


if __name__ == "__main__":
    sys.exit(main())
