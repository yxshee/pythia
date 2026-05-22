"""Regenerate the two web snapshot bundles from the per-trace JSONs on disk.

Inputs:
  ``traces/trace-*.json``        canonical per-trace files (analyst + plan +
                                  full + publication + canonical + onchain)

Outputs:
  ``web/data/picks-full.private.json``
                                  latest anchored LLM trace per market,
                                  verbatim. Keep this server-only and out of
                                  public GitHub/submission zips.
  ``web/data/picks-preview.json`` preview-only projection of the same public
                                  trace set: drop
                                  ``analyst``/``plan``/``full``/``publication``/
                                  ``builder_code`` and lift ``preview.market_id``
                                  to a top-level ``market_id``. Safe to ship in
                                  the public SSR bundle.

The transforms here mirror what `web/lib/traces.ts:loadFromSnapshot` expects
(picks-preview is the input to `loadPicks()` on Vercel where the traces/
directory isn't shipped with the deploy).

Usage:
    cd agent
    uv run python -m pythia.scripts.regen_snapshots

Idempotent.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_PREVIEW_DROP_KEYS = frozenset({
    "analyst",
    "plan",
    "full",
    "publication",
    "builder_code",
})


def _is_public_trace(trace: dict) -> bool:
    preview = trace.get("preview") or {}
    return (
        preview.get("model") != "heuristic-v1-placeholder"
        and bool((trace.get("onchain") or {}).get("tx_hash"))
    )


def _latest_public_by_market(traces: list[dict]) -> list[dict]:
    by_market: dict[str, dict] = {}
    for trace in traces:
        if not _is_public_trace(trace):
            continue
        preview = trace.get("preview") or {}
        market_id = str(preview.get("market_id") or trace.get("market_id") or "")
        previous = by_market.get(market_id)
        if previous is None or str(preview.get("generated_at")) > str((previous.get("preview") or {}).get("generated_at")):
            by_market[market_id] = trace
    return sorted(by_market.values(), key=lambda t: int(t.get("trace_id", 0)), reverse=True)


def _to_preview_entry(trace: dict) -> dict:
    """Strip paid + canonical fields, add top-level market_id from preview."""
    out = {k: v for k, v in trace.items() if k not in _PREVIEW_DROP_KEYS}
    preview = trace.get("preview") or {}
    if "market_id" in preview:
        out["market_id"] = preview["market_id"]
    return out


def main() -> int:
    repo_root = Path(__file__).resolve().parents[3]
    traces_dir = repo_root / "traces"
    out_full = repo_root / "web" / "data" / "picks-full.private.json"
    out_preview = repo_root / "web" / "data" / "picks-preview.json"
    public_full = repo_root / "web" / "data" / "picks-full.json"

    files = sorted(traces_dir.glob("trace-*.json"))
    if not files:
        print(f"no traces found under {traces_dir}", file=sys.stderr)
        return 1

    traces: list[dict] = []
    for f in files:
        traces.append(json.loads(f.read_text()))

    # picks-full.private: server-only bundle. Historical traces stay on disk
    # for private audit/replay, but the judge-visible web app serves the
    # latest anchored LLM trace per market so old heuristic/stale duplicate
    # routes disappear.
    full_sorted = _latest_public_by_market(traces)
    if not full_sorted:
        print("no public anchored LLM traces found", file=sys.stderr)
        return 1
    out_full.write_text(json.dumps(full_sorted, indent=2, sort_keys=True))
    if public_full.exists():
        public_full.unlink()

    # picks-preview: stripped projection, also newest-first.
    preview_sorted = [_to_preview_entry(t) for t in full_sorted]
    out_preview.write_text(json.dumps(preview_sorted, indent=2, sort_keys=True))

    print(f"wrote {out_full.relative_to(repo_root)} ({len(full_sorted)} entries)")
    print(f"wrote {out_preview.relative_to(repo_root)} ({len(preview_sorted)} entries)")

    # Defensive cross-check: confirm no leaked paid fields in the preview bundle.
    for entry in preview_sorted:
        leaked = _PREVIEW_DROP_KEYS & set(entry.keys())
        if leaked:
            print(
                f"LEAK in trace #{entry.get('trace_id')}: {sorted(leaked)} survived the strip",
                file=sys.stderr,
            )
            return 2

    return 0


if __name__ == "__main__":
    sys.exit(main())
