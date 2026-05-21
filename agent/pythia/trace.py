"""Trace publishing: pin the analyst report to IPFS, log the CID on Arc.

Day-1 implementation writes traces to local JSON files under ``./traces/`` so the loop
runs end-to-end without any cloud dependencies. On Day 6 the pinning swaps to Irys and
the on-chain log call to ``TraceLog.publish`` goes live.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

import structlog

from .analyst import AnalystReport
from .config import Settings
from .pm import TradePlan
from .preview import to_full, to_preview
from .publisher import PublishResult
from .scout import MarketCandidate

log = structlog.get_logger(__name__)


@dataclass(slots=True)
class PublishedTrace:
    """Receipt for a published trace."""

    trace_id: int  # incremental, mirrors the on-chain id once live
    ipfs_cid: str  # placeholder hex in dry-run mode
    local_path: str
    tx_hash: str | None = None  # populated once on-chain log lands


class TracePublisher:
    """Persist + anchor reasoning traces.

    The on-chain anchor will be:

        trace_log.publish(
            market_id,
            decision_code,
            position_usdc,
            confidence_bps,
            ipfs_cid_bytes32,
            parent_trace_id,
        )

    For Day 1 we mirror the structure to local disk so the rest of the loop is exercised.
    """

    def __init__(self, settings: Settings, traces_dir: Path | None = None):
        self._settings = settings
        self._dir = traces_dir or (Path(__file__).resolve().parents[2] / "traces")
        self._dir.mkdir(parents=True, exist_ok=True)
        self._counter = self._init_counter()

    def _init_counter(self) -> int:
        existing = sorted(self._dir.glob("trace-*.json"))
        if not existing:
            return 1
        last = existing[-1].stem  # trace-NNNN
        try:
            return int(last.split("-")[-1]) + 1
        except ValueError:
            return len(existing) + 1

    def publish(
        self,
        report: AnalystReport,
        plan: TradePlan,
        market: MarketCandidate,
        publication: PublishResult | None = None,
    ) -> PublishedTrace:
        trace_id = self._counter
        self._counter += 1
        # Build the canonical payload first to compute the deterministic CID.
        canonical = {
            "trace_id": trace_id,
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "model": report.model,
            "analyst": asdict(report),
            "plan": asdict(plan),
            "publication": asdict(publication) if publication is not None else None,
            "theme": self._settings.pythia_theme,
            "vault": self._settings.pythia_vault_address,
            "builder_code": self._settings.polymarket_builder_code or "pythia",
        }
        body = json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode("utf-8")
        # Day-1 "CID" is just the sha256 of the body; once Irys is wired this becomes the real CIDv1.
        cid_hex = "0x" + hashlib.sha256(body).hexdigest()

        # Layered payload written to disk:
        #   - `preview`: free-tier projection (safe to expose unauthenticated).
        #   - `full`: paid-tier projection (gated by UnlockMarket).
        #   - `canonical`: raw analyst/plan/publication, for replayability + debugging.
        preview = to_preview(report, plan, market, trace_id=trace_id, trace_hash=cid_hex)
        full = to_full(report, plan, market, trace_id=trace_id, trace_hash=cid_hex)
        payload = {
            **canonical,
            "preview": preview,
            "full": full,
        }
        path = self._dir / f"trace-{trace_id:06d}.json"
        path.write_text(json.dumps(payload, indent=2, sort_keys=True))
        log.info("trace.published", trace_id=trace_id, cid=cid_hex[:12], path=str(path))
        return PublishedTrace(trace_id=trace_id, ipfs_cid=cid_hex, local_path=str(path))
