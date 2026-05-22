"""Trace publishing: persist analyst output privately and anchor on Arc via TraceLog.

The JSON written by release scripts is the server-side source of truth for replay
and web unlocks. The on-chain ``TraceLog.publish`` emit is best-effort additive
evidence — when it succeeds, the tx hash and the contract-assigned trace id get
appended to the JSON. When the on-chain leg is unavailable (missing key, missing
contract address, or a network error) we keep writing locally so development
runs still produce inspectable traces.

Activation: set ``TRACE_LOG_ADDRESS``, a real ``ARC_RPC_URL`` (not the ``REPLACE_ME``
placeholder), and a non-zero ``PRIVATE_KEY`` in ``.env``. The publisher must already
be authorized via ``TraceLog.setPublisher`` — the deploy script does this for the
operator address.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import structlog

from .analyst import AnalystReport
from .config import Settings
from .pm import TradePlan
from .preview import to_full, to_preview
from .publisher import PublishResult
from .scout import MarketCandidate

log = structlog.get_logger(__name__)

# Minimal ABI: just the functions we call. Keeps trace.py free of the full artifact.
TRACE_LOG_ABI: list[dict[str, Any]] = [
    {
        "type": "function",
        "name": "publish",
        "stateMutability": "nonpayable",
        "inputs": [
            {"name": "marketId", "type": "bytes32"},
            {"name": "decision", "type": "uint8"},
            {"name": "positionUsdc", "type": "uint256"},
            {"name": "confidenceBps", "type": "uint16"},
            {"name": "ipfsCid", "type": "bytes32"},
            {"name": "parentTraceId", "type": "uint256"},
        ],
        "outputs": [{"name": "traceId", "type": "uint256"}],
    },
    {
        "type": "function",
        "name": "nextTraceId",
        "stateMutability": "view",
        "inputs": [],
        "outputs": [{"name": "", "type": "uint256"}],
    },
]

# Map agent decision strings to the TraceLog.Decision enum.
_DECISION_TO_ENUM = {"HOLD": 0, "BUY_YES": 1, "BUY_NO": 2}


@dataclass(slots=True)
class PublishedTrace:
    """Receipt for a published trace."""

    trace_id: int  # local counter; matches the JSON filename
    ipfs_cid: str  # sha256-of-canonical-body today; real CIDv1 once Irys lands
    local_path: str
    tx_hash: str | None = None
    onchain_trace_id: int | None = None  # id assigned by TraceLog.publish


class TracePublisher:
    """Persist + anchor reasoning traces.

    On-chain anchoring fires only when ALL of these are true:
        - ``settings.trace_log_address`` is set
        - ``settings.arc_rpc_url`` does not contain ``REPLACE_ME``
        - ``settings.private_key`` is not the zero default
        - ``web3`` and ``eth_account`` are importable

    Otherwise the publisher is local-only — same JSON output, no tx, no warning spam.
    """

    def __init__(self, settings: Settings, traces_dir: Path | None = None):
        self._settings = settings
        self._dir = traces_dir or (Path(__file__).resolve().parents[2] / "traces")
        self._dir.mkdir(parents=True, exist_ok=True)
        self._counter = self._init_counter()
        self._w3 = None
        self._account = None
        self._contract = None
        self._maybe_init_onchain()

    # ------------------------------------------------------------------
    #  Wiring
    # ------------------------------------------------------------------
    def _maybe_init_onchain(self) -> None:
        """Wire a web3 client + the TraceLog contract if config and key are present."""
        address = self._settings.trace_log_address
        rpc_url = self._settings.arc_rpc_url
        pk = self._settings.private_key
        if not address:
            return
        if not rpc_url or "REPLACE_ME" in rpc_url:
            return
        if not pk or pk == "0x" + "0" * 64:
            return
        try:
            from eth_account import Account
            from web3 import Web3
        except ImportError:
            log.info("trace.web3_unavailable")
            return
        try:
            w3 = Web3(Web3.HTTPProvider(rpc_url))
            account = Account.from_key(pk)
            contract = w3.eth.contract(
                address=Web3.to_checksum_address(address),
                abi=TRACE_LOG_ABI,
            )
            self._w3 = w3
            self._account = account
            self._contract = contract
            log.info(
                "trace.onchain_ready",
                publisher=account.address,
                contract=address,
                chain_id=int(self._settings.arc_chain_id),
            )
        except Exception as exc:  # noqa: BLE001 - local-only mode is the safety net
            log.warning("trace.onchain_init_failed", error=str(exc))

    def _init_counter(self) -> int:
        existing = sorted(self._dir.glob("trace-*.json"))
        if not existing:
            return 1
        last = existing[-1].stem  # trace-NNNNNN
        try:
            return int(last.split("-")[-1]) + 1
        except ValueError:
            return len(existing) + 1

    # ------------------------------------------------------------------
    #  Publish
    # ------------------------------------------------------------------
    def publish(
        self,
        report: AnalystReport,
        plan: TradePlan,
        market: MarketCandidate,
        publication: PublishResult | None = None,
        *,
        trace_id: int | None = None,
    ) -> PublishedTrace:
        # Default: monotonically increment the local counter. Regen scripts
        # pass an explicit `trace_id` to overwrite an existing file (e.g.
        # `agent/pythia/scripts/regen_specific.py`) without bumping the
        # counter — the canonical body changes, the file is rewritten, and
        # a new on-chain anchor is emitted. The old on-chain trace remains
        # in TraceLog (append-only) but is no longer referenced off-chain.
        if trace_id is None:
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
        # Today's "CID" is the sha256 of the canonical body. When Irys pinning lands
        # this becomes the real CIDv1 returned by the pinning service.
        cid_hex = "0x" + hashlib.sha256(body).hexdigest()

        preview = to_preview(report, plan, market, trace_id=trace_id, trace_hash=cid_hex)
        full = to_full(
            report,
            plan,
            market,
            trace_id=trace_id,
            trace_hash=cid_hex,
            builder_code=self._settings.polymarket_builder_code,
        )
        payload: dict[str, Any] = {
            **canonical,
            "preview": preview,
            "full": full,
        }
        path = self._dir / f"trace-{trace_id:06d}.json"
        path.write_text(json.dumps(payload, indent=2, sort_keys=True))

        onchain = self._maybe_publish_onchain(plan, cid_hex)
        if onchain is not None:
            # Re-write with the on-chain receipt appended. The canonical (hashed) body
            # is unchanged — only metadata is added, kept outside the cid pre-image.
            payload["onchain"] = onchain
            path.write_text(json.dumps(payload, indent=2, sort_keys=True))

        log.info(
            "trace.published",
            trace_id=trace_id,
            cid=cid_hex[:12],
            path=str(path),
            tx_hash=(onchain or {}).get("tx_hash"),
        )
        return PublishedTrace(
            trace_id=trace_id,
            ipfs_cid=cid_hex,
            local_path=str(path),
            tx_hash=(onchain or {}).get("tx_hash"),
            onchain_trace_id=(onchain or {}).get("trace_id"),
        )

    # ------------------------------------------------------------------
    #  On-chain anchor (best effort)
    # ------------------------------------------------------------------
    def _maybe_publish_onchain(self, plan: TradePlan, cid_hex: str) -> dict[str, Any] | None:
        """Emit ``TraceLog.publish`` for the plan. Returns None in local-only mode."""
        if self._w3 is None or self._account is None or self._contract is None:
            return None
        try:
            from web3 import Web3

            market_id_b32 = _str_to_bytes32(plan.market_id)
            decision_enum = _DECISION_TO_ENUM.get(plan.decision, 0)
            position_usdc_base = int(round(max(0.0, plan.size_usdc) * 1_000_000))
            confidence = max(0, min(10_000, int(plan.confidence_bps)))
            cid_b32 = Web3.to_bytes(hexstr=cid_hex)
            parent_id = int(plan.parent_trace_id or 0)

            # Read the to-be-assigned id BEFORE we send so we can record it in metadata.
            assigned_id = int(self._contract.functions.nextTraceId().call())

            tx = self._contract.functions.publish(
                market_id_b32,
                decision_enum,
                position_usdc_base,
                confidence,
                cid_b32,
                parent_id,
            ).build_transaction(
                {
                    "from": self._account.address,
                    "nonce": self._w3.eth.get_transaction_count(self._account.address),
                    "gas": 200_000,
                    "gasPrice": self._w3.eth.gas_price,
                    "chainId": int(self._settings.arc_chain_id),
                }
            )
            signed = self._account.sign_transaction(tx)
            raw = getattr(signed, "raw_transaction", None) or getattr(signed, "rawTransaction")
            tx_hash_bytes = self._w3.eth.send_raw_transaction(raw)
            receipt = self._w3.eth.wait_for_transaction_receipt(tx_hash_bytes, timeout=30)
            tx_hash_hex = tx_hash_bytes.hex() if isinstance(tx_hash_bytes, bytes) else str(tx_hash_bytes)
            if not tx_hash_hex.startswith("0x"):
                tx_hash_hex = "0x" + tx_hash_hex
            return {
                "tx_hash": tx_hash_hex,
                "block_number": int(receipt.blockNumber),
                "trace_id": assigned_id,
                "publisher": self._account.address,
                "contract": self._contract.address,
                "chain_id": int(self._settings.arc_chain_id),
            }
        except Exception as exc:  # noqa: BLE001 — local file is the source of truth
            log.warning("trace.onchain_failed", error=str(exc), market_id=plan.market_id)
            return None


def _str_to_bytes32(s: str) -> bytes:
    """Normalize an agent market_id string into a bytes32 the contract accepts.

    Polymarket condition IDs are already 0x-prefixed 32-byte hex. Slugs and other
    short strings get keccak256-hashed so we still emit a deterministic, collision-
    resistant identifier on chain.
    """
    from web3 import Web3

    if isinstance(s, str) and s.startswith("0x") and len(s) == 66:
        try:
            return Web3.to_bytes(hexstr=s)
        except (ValueError, TypeError):
            pass
    return Web3.keccak(text=s or "")
