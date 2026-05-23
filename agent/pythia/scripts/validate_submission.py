"""Validate judge-visible Pythia submission data.

Two modes:

* ``deploy`` (default): for the live Vercel deploy. Requires the paid
  full bundle to exist locally (``web/data/picks-full.private.json``) OR
  a Vercel Blob URL (``PRIVATE_TRACES_BLOB_URL``) to be configured. Runs
  full-payload quality checks against the local file when present.

* ``package``: for the public submission zip. Forbids the paid full
  bundle and the legacy public full snapshot. Runs only public-surface
  checks.

Both modes share the public-surface invariants: preview cleanliness,
wrong FOMC date patterns, stale unlock-price copy, fixture source
markers, public ``traces/`` absence, and home-feed dedup.

Usage::

    cd agent
    uv run python -m pythia.scripts.validate_submission --mode deploy
    uv run python -m pythia.scripts.validate_submission --mode package
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from pathlib import Path
from typing import Any

_PREVIEW_FORBIDDEN_KEYS = frozenset({
    "analyst",
    "canonical",
    "full",
    "plan",
    "publication",
})
_WRONG_FOMC_PATTERNS = (
    "June " + "17-18",
    "July " + "29-30",
    "2026-06-" + "18",
    "2026-07-" + "30",
)
_STALE_USDC_COPY = "Unlock 0.10 " + "USDC"
_FIXTURE_SOURCE = "Offline market " + "fixture"


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text())


def _eligible_home_entries(preview_entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        entry
        for entry in preview_entries
        if (entry.get("preview") or {}).get("model") != "heuristic-v1-placeholder"
        and bool((entry.get("onchain") or {}).get("tx_hash"))
    ]


def _latest_by_market(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_market: dict[str, dict[str, Any]] = {}
    for entry in entries:
        preview = entry.get("preview") or {}
        market_id = str(preview.get("market_id") or entry.get("market_id") or "")
        previous = by_market.get(market_id)
        if previous is None or str(preview.get("generated_at")) > str((previous.get("preview") or {}).get("generated_at")):
            by_market[market_id] = entry
    return sorted(
        by_market.values(),
        key=lambda entry: str((entry.get("preview") or {}).get("generated_at")),
        reverse=True,
    )


def _text_files(root: Path, rel_roots: tuple[str, ...]) -> list[Path]:
    files: list[Path] = []
    for rel in rel_roots:
        path = root / rel
        if not path.exists():
            continue
        if path.is_file():
            files.append(path)
            continue
        for candidate in path.rglob("*"):
            if not candidate.is_file():
                continue
            if any(part in {".git", ".next", ".venv", "node_modules", "cache", "out"} for part in candidate.parts):
                continue
            if candidate.suffix.lower() in {".json", ".md", ".py", ".ts", ".tsx", ".sol", ".example", ".txt"}:
                files.append(candidate)
    return files


def _scan_text(root: Path, pattern: str, rel_roots: tuple[str, ...]) -> list[str]:
    matches: list[str] = []
    for path in _text_files(root, rel_roots):
        try:
            text = path.read_text()
        except UnicodeDecodeError:
            continue
        if pattern in text:
            matches.append(str(path.relative_to(root)))
    return sorted(matches)


_NON_MARKET_SOURCE_KINDS = frozenset({
    "event_data",
    "news",
    "sentiment",
    "official_data",
})


def validate_repo(repo_root: Path, *, mode: str = "deploy") -> list[str]:
    if mode not in {"deploy", "package"}:
        raise ValueError(f"unknown mode: {mode!r}; expected 'deploy' or 'package'")

    preview_path = repo_root / "web" / "data" / "picks-preview.json"
    public_full_path = repo_root / "web" / "data" / "picks-full.json"
    private_full_path = repo_root / "web" / "data" / "picks-full.private.json"

    preview_entries = _load_json(preview_path)
    failures: list[str] = []

    if public_full_path.exists():
        failures.append("public paid snapshot web/data/picks-full.json must not ship")

    full_entries: list[dict[str, Any]] = []
    if mode == "deploy":
        if private_full_path.exists():
            full_entries = _load_json(private_full_path)
        elif os.environ.get("PRIVATE_TRACES_BLOB_URL"):
            # Operator says the paid bundle lives in Vercel Blob; we cannot
            # fetch it here (validator is offline), but we trust the env var.
            # Full-payload quality checks are skipped in this branch — they
            # must be enforced upstream by publish_live_feed.py before upload.
            pass
        else:
            failures.append(
                "deploy mode: web/data/picks-full.private.json is missing AND "
                "PRIVATE_TRACES_BLOB_URL is unset"
            )
    # package mode intentionally ignores private_full_path: the operator's
    # working directory always has it after `publish_live_feed`, but the
    # zip builder in `scripts/package_submission.py` excludes everything
    # matching `web/data/picks-full*`. The shipped zip will not contain
    # the private bundle even when the working tree does.

    scan_roots = ("agent", "web", "traces", "README.md", "STATUS.md", "VERIFY.md", "docs")
    for pattern in _WRONG_FOMC_PATTERNS:
        paths = _scan_text(repo_root, pattern, scan_roots)
        if paths:
            failures.append(f"wrong FOMC date pattern {pattern!r} appears in {paths}")
    stale_copy_paths = _scan_text(repo_root, _STALE_USDC_COPY, scan_roots)
    if stale_copy_paths:
        failures.append(f"stale unlock-price copy appears in {stale_copy_paths}")
    fixture_paths = _scan_text(repo_root, _FIXTURE_SOURCE, scan_roots)
    if fixture_paths:
        failures.append(f"fixture source marker appears in {fixture_paths}")

    for entry in preview_entries:
        trace_id = entry.get("trace_id")
        leaked = _PREVIEW_FORBIDDEN_KEYS & set(entry)
        if leaked:
            failures.append(f"trace {trace_id}: preview bundle leaks {sorted(leaked)}")
        if _FIXTURE_SOURCE in json.dumps(entry):
            failures.append(f"trace {trace_id}: preview bundle contains fixture source marker")

    eligible = _eligible_home_entries(preview_entries)
    home = _latest_by_market(eligible)
    questions = Counter((entry.get("preview") or {}).get("question") for entry in home)
    duplicate_questions = sorted(q for q, count in questions.items() if count > 1)
    if len(home) < 8:
        failures.append(f"home feed has {len(home)} unique anchored LLM markets; expected >= 8")
    if duplicate_questions:
        failures.append(f"home feed has duplicate questions: {duplicate_questions}")

    for entry in full_entries:
        full = entry.get("full") or {}
        trace_id = entry.get("trace_id")
        if _FIXTURE_SOURCE in json.dumps(entry):
            failures.append(f"trace {trace_id}: full payload contains fixture source marker")
        if full.get("decision") == "HOLD" and full.get("copy_trade_url"):
            failures.append(f"trace {trace_id}: HOLD full payload still has copy_trade_url")
        sources = full.get("sources") or []
        if len(sources) < 3:
            failures.append(f"trace {trace_id}: full payload has only {len(sources)} sources")
        if not any(isinstance(source, dict) and source.get("observed_at") for source in sources):
            failures.append(f"trace {trace_id}: full payload sources lack observed_at")
        kinds = {str(source.get("kind") or "") for source in sources if isinstance(source, dict)}
        if not (_NON_MARKET_SOURCE_KINDS & kinds):
            failures.append(
                f"trace {trace_id}: full payload sources lack a non-market kind "
                f"(have {sorted(kinds)}; need one of {sorted(_NON_MARKET_SOURCE_KINDS)})"
            )
        risks = full.get("risk_factors") or []
        if not risks:
            failures.append(f"trace {trace_id}: full payload has no risk_factors")

    public_trace_files = sorted((repo_root / "traces").glob("trace-*.json")) if (repo_root / "traces").exists() else []
    if public_trace_files:
        names = [str(path.relative_to(repo_root)) for path in public_trace_files[:5]]
        more = "" if len(public_trace_files) <= 5 else f" and {len(public_trace_files) - 5} more"
        failures.append(f"public traces/ contains production trace JSON: {names}{more}")

    full_ids = {entry.get("trace_id") for entry in full_entries}
    home_ids = {entry.get("trace_id") for entry in home}
    if full_entries and home_ids != full_ids:
        failures.append(f"private full trace ids {sorted(full_ids)} do not match preview ids {sorted(home_ids)}")

    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mode",
        choices=("deploy", "package"),
        default="deploy",
        help="deploy: live Vercel state (default). package: contents of the public submission zip.",
    )
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[3]
    failures = validate_repo(repo_root, mode=args.mode)
    if failures:
        for failure in failures:
            print(f"FAIL: {failure}", file=sys.stderr)
        return 1

    preview_entries = _load_json(repo_root / "web" / "data" / "picks-preview.json")
    home = _latest_by_market(_eligible_home_entries(preview_entries))
    private_full_path = repo_root / "web" / "data" / "picks-full.private.json"
    if args.mode == "deploy" and private_full_path.exists():
        full_entries = _load_json(private_full_path)
        print(
            f"submission data ok (deploy): {len(home)} home markets, "
            f"{len(full_entries)} private full traces"
        )
    elif args.mode == "deploy":
        print(
            f"submission data ok (deploy): {len(home)} home markets, "
            "private bundle served from PRIVATE_TRACES_BLOB_URL"
        )
    else:
        print(f"submission data ok (package): {len(home)} home markets, no paid bundle present")
    return 0


if __name__ == "__main__":
    sys.exit(main())
