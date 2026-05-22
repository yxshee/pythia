"""Regenerate the two web snapshot bundles from the per-trace JSONs on disk.

Inputs:
  ``traces/trace-*.json``        canonical per-trace files (analyst + plan +
                                  full + publication + canonical + onchain)

Outputs:
  ``web/data/picks-full.json``    every per-trace JSON, verbatim, sorted by
                                  ``trace_id`` ascending. Read only by the
                                  paywall route handler after SIWE + onchain
                                  ``isUnlocked`` verification.
  ``web/data/picks-preview.json`` preview-only projection: drop
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
    out_full = repo_root / "web" / "data" / "picks-full.json"
    out_preview = repo_root / "web" / "data" / "picks-preview.json"

    files = sorted(traces_dir.glob("trace-*.json"))
    if not files:
        print(f"no traces found under {traces_dir}", file=sys.stderr)
        return 1

    traces: list[dict] = []
    for f in files:
        traces.append(json.loads(f.read_text()))

    # picks-full: verbatim, sorted by trace_id desc (newest first — same
    # convention as `loadPicks()` after its in-memory sort).
    full_sorted = sorted(traces, key=lambda t: int(t.get("trace_id", 0)), reverse=True)
    out_full.write_text(json.dumps(full_sorted, indent=2, sort_keys=True))

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
