"""Recompute ``web/data/metrics.json`` from the per-trace JSONs on disk.

The traction strip on the home page reads this file. Keeping the metric
derivation deterministic and scripted (rather than hand-edited) is the
post-audit fix for the "what does Paper volume actually measure" gap.

Definitions
-----------
- ``published``: count of trace files whose ``onchain.tx_hash`` is set.
  Mirrors what the strip labels "on-chain traces".
- ``paper_volume_usdc``: sum of ``plan.size_usdc`` for the same set of
  on-chain-anchored traces. Aligning the population means a viewer
  can verify the dollar figure by walking the TraceLog events on
  Arcscan — the off-chain heuristic-only picks no longer inflate this
  number.
- ``latest_trace_id`` / ``latest_tx_hash`` / ``latest_block``: from
  the trace JSON with the highest ``trace_id`` that has an on-chain
  receipt.
- ``contract`` / ``chain_id`` / ``explorer_url``: passed through as
  static constants (the TraceLog address on Arc testnet).

Usage:
    cd agent
    uv run python -m pythia.scripts.regen_metrics

Idempotent.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_TRACE_LOG_ADDRESS = "0x48Af95Ed6F1E4dF73Dd62CE17731084a5E98AFB4"
_CHAIN_ID = 5042002
_EXPLORER_URL = "https://testnet.arcscan.app"


def main() -> int:
    repo_root = Path(__file__).resolve().parents[3]
    traces_dir = repo_root / "traces"
    out = repo_root / "web" / "data" / "metrics.json"

    files = sorted(traces_dir.glob("trace-*.json"))
    if not files:
        print(f"no traces found under {traces_dir}", file=sys.stderr)
        return 1

    anchored: list[dict] = []
    for f in files:
        t = json.loads(f.read_text())
        if (t.get("onchain") or {}).get("tx_hash"):
            anchored.append(t)

    if not anchored:
        print("no anchored traces — refusing to write all-zero metrics.json", file=sys.stderr)
        return 1

    published = len(anchored)
    paper_volume = round(
        sum(float(t.get("plan", {}).get("size_usdc", 0.0)) for t in anchored),
        2,
    )

    latest = max(anchored, key=lambda t: int(t["trace_id"]))
    metrics = {
        "published": published,
        "paper_volume_usdc": paper_volume,
        "latest_trace_id": int(latest["trace_id"]),
        "latest_tx_hash": latest["onchain"]["tx_hash"],
        "latest_block": int(latest["onchain"]["block_number"]),
        "contract": _TRACE_LOG_ADDRESS,
        "chain_id": _CHAIN_ID,
        "explorer_url": _EXPLORER_URL,
    }

    out.write_text(json.dumps(metrics, indent=2) + "\n")
    print(f"wrote {out.relative_to(repo_root)}")
    for k, v in metrics.items():
        print(f"  {k}: {v}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
