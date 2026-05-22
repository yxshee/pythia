"""Regenerate specific trace JSONs in place.

Why this exists
---------------
The agent's normal loop (`pythia-loop --once [--mock]`) only ever appends
new traces — `TracePublisher._init_counter()` reads the highest existing
trace id and starts from `+1`. That's the right behaviour for daily
operation but the wrong tool when an audit finds stale reasoning in
already-published traces and we need to rewrite the canonical content
without orphaning the trace ids the web feed and pitch video reference.

This script:

  1. Reads the existing trace JSON for each requested id.
  2. Looks up the matching `MarketCandidate` from the mock fixtures
     (every existing LLM trace was produced from one of three fixtures —
     ETH $4,000 / BTC new ATH / BTC $120k Q4).
  3. Runs the LLM analyst with the hardened system prompt (see
     `analyst.py:_score_with_llm`).
  4. Sizes the plan via PortfolioManager (HOLDs get a zero-size plan
     so the trace JSON still gets a fresh canonical body).
  5. Calls `Publisher.publish()` to compose the builder-code link.
  6. Calls `TracePublisher.publish(..., trace_id=<id>)` which overwrites
     the JSON in place and emits a brand-new `TraceLog.publish(...)` tx
     on Arc. The old tx hashes stay in TraceLog (append-only by design)
     but no off-chain file references them — honest historical artifact.

The script intentionally requires `ANTHROPIC_API_KEY` and a real
`PRIVATE_KEY` + `ARC_RPC_URL` in `.env`. There's no `--dry-run` because
the whole point is to actually re-anchor.

Usage
-----
    cd agent
    uv run python -m pythia.scripts.regen_specific 5 6 9 10 11 12 13 14 15

Idempotent against the same set of trace ids: re-running the script
overwrites the same files (and emits another batch of tx hashes).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from ..analyst import Analyst, AnalystReport
from ..config import SETTINGS
from ..fixtures import mock_candidates
from ..pm import PortfolioManager, TradePlan
from ..publisher import Publisher
from ..scout import MarketCandidate
from ..trace import TracePublisher


def _candidate_by_market_id() -> dict[str, MarketCandidate]:
    return {c.market_id: c for c in mock_candidates()}


def _read_existing(trace_id: int, traces_dir: Path) -> dict:
    path = traces_dir / f"trace-{trace_id:06d}.json"
    if not path.exists():
        raise SystemExit(f"trace-{trace_id:06d}.json does not exist at {path}")
    return json.loads(path.read_text())


def _hold_plan(report: AnalystReport) -> TradePlan:
    """Stub TradePlan for a HOLD report so the trace still serializes.

    The default loop drops HOLDs at the PM stage; for regen we want the
    canonical body to be rewritten regardless so the trace file is
    self-consistent with the new analyst output.
    """
    return TradePlan(
        market_id=report.market_id,
        question=report.question,
        decision="HOLD",
        size_usdc=0.0,
        confidence_bps=report.confidence_bps,
        edge_bps=report.edge_bps,
    )


def regen_trace(
    trace_id: int,
    *,
    candidates: dict[str, MarketCandidate],
    analyst: Analyst,
    pm: PortfolioManager,
    publisher: Publisher,
    tracer: TracePublisher,
    traces_dir: Path,
) -> None:
    existing = _read_existing(trace_id, traces_dir)
    market_id = existing["analyst"]["market_id"]
    candidate = candidates.get(market_id)
    if candidate is None:
        raise SystemExit(
            f"no fixture matches market_id {market_id!r} for trace #{trace_id}. "
            f"Available fixtures: {sorted(candidates.keys())}"
        )

    print(f"[regen] trace #{trace_id:03d}: scoring {market_id[:14]}... ", end="", flush=True)
    report = analyst.score(candidate)
    print(f"-> {report.decision} edge={report.edge_bps:+d}bps conf={report.confidence_bps/100:.1f}% model={report.model}")

    if report.decision == "HOLD":
        plan = _hold_plan(report)
    else:
        plans = pm.plan([report])
        if not plans:
            # PM dropped the BUY (edge floor / liquidity floor / size=0).
            # Fall back to a HOLD plan so the trace still rewrites.
            plan = _hold_plan(report)
        else:
            plan = plans[0]

    publication = publisher.publish(plan, candidate)
    result = tracer.publish(report, plan, candidate, publication, trace_id=trace_id)
    tx = result.tx_hash[:14] + "…" if result.tx_hash else "<local-only>"
    print(
        f"[regen] trace #{trace_id:03d}: wrote {Path(result.local_path).name} "
        f"cid={result.ipfs_cid[:14]}… tx={tx}"
    )


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2

    try:
        trace_ids = [int(x) for x in argv]
    except ValueError:
        print(f"usage: regen_specific <trace_id> [<trace_id> ...]\n got: {argv!r}", file=sys.stderr)
        return 2

    settings = SETTINGS
    if not settings.anthropic_api_key:
        print("ANTHROPIC_API_KEY is required for regen (the whole point is to re-run the LLM).", file=sys.stderr)
        return 2

    analyst = Analyst(settings)
    # Sanity: confirm we wired the LLM, not the heuristic fallback.
    if analyst._client is None:  # noqa: SLF001 - one-off script
        print("Analyst initialised without anthropic client. Check the .env key.", file=sys.stderr)
        return 2

    pm = PortfolioManager(settings)
    publisher = Publisher(settings)
    tracer = TracePublisher(settings)

    # Sanity print for on-chain wiring. The TracePublisher logs this too,
    # but a one-line console echo before any LLM tokens are spent is a
    # cheap safeguard against a misconfigured run.
    if tracer._contract is None:  # noqa: SLF001
        print(
            "[regen] WARNING: TraceLog wiring is not active (missing TRACE_LOG_ADDRESS, "
            "RPC URL, or PRIVATE_KEY). Traces will be rewritten locally but NOT anchored.",
            file=sys.stderr,
        )

    traces_dir = Path(__file__).resolve().parents[3] / "traces"
    candidates = _candidate_by_market_id()

    for tid in trace_ids:
        regen_trace(
            tid,
            candidates=candidates,
            analyst=analyst,
            pm=pm,
            publisher=publisher,
            tracer=tracer,
            traces_dir=traces_dir,
        )

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
