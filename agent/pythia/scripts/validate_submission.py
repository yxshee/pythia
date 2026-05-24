"""Validate judge-visible Pythia submission data.

Two modes:

* ``private-deploy`` (default; alias ``deploy``): for the live Vercel
  deploy. Requires the paid full bundle to exist locally
  (``web/data/picks-full.private.json``) OR a Vercel Blob URL
  (``PRIVATE_TRACES_BLOB_URL``) to be configured. Runs full-payload
  quality checks against the local file when present.

* ``public-package`` (alias ``package``): for the public submission
  zip. Forbids the paid full bundle and the legacy public full
  snapshot. Runs only public-surface checks.

Both modes share the public-surface invariants: preview cleanliness,
wrong FOMC date patterns, stale unlock-price copy, fixture source
markers, public ``traces/`` absence, and home-feed dedup.

Usage::

    cd agent
    uv run python -m pythia.scripts.validate_submission --mode private-deploy
    uv run python -m pythia.scripts.validate_submission --mode public-package
"""

from __future__ import annotations

import argparse
import base64
import binascii
import hashlib
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from collections import Counter
from pathlib import Path
from typing import Any

_BLOB_FETCH_TIMEOUT_S = 5.0
_PRIVATE_TRACE_AAD = b"pythia-private-traces-v1"
_MIN_PRIVATE_TRACES_ENCRYPTION_KEY_BYTES = 32

# Old names accepted as aliases so STATUS.md / README.md examples keep working
# while docs are updated. Canonical names are 'private-deploy' / 'public-package'.
_MODE_ALIASES: dict[str, str] = {
    "deploy": "private-deploy",
    "package": "public-package",
    "private-deploy": "private-deploy",
    "public-package": "public-package",
}

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
_FIXTURE_SOURCE_MARKERS = (
    "Offline market " + "fixture",
    "Synthetic fixture " + "market data",
)
_HOLD_ACTIONABLE_RECOMMENDATION_MARKERS = (
    "buy yes is justifiable",
    "buy no is justifiable",
    "take the position",
    "copy trade",
)
_STALE_TEST_COUNT_PATTERNS = (
    "61%2F61",
    "61/61",
    "42/42",
    "42 forge",
    "42 tests",
    "19 agent",
    "33 tests",
    "35 tests",
    "37 tests passed",
)


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


def _fetch_blob_entries(url: str, failures: list[str]) -> list[dict[str, Any]]:
    """Fetch the private Blob trace bundle without echoing its secret URL."""
    request = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=_BLOB_FETCH_TIMEOUT_S) as response:
            status = response.status
            content_type = (response.headers.get("Content-Type") or "").lower()
            body = response.read()
    except urllib.error.HTTPError as exc:
        exc.close()
        failures.append(f"PRIVATE_TRACES_BLOB_URL returned HTTP {exc.code} (expected 200)")
        return []
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        failures.append(f"PRIVATE_TRACES_BLOB_URL unreachable: {exc}")
        return []

    if status != 200:
        failures.append(f"PRIVATE_TRACES_BLOB_URL returned HTTP {status} (expected 200)")
        return []
    if "json" not in content_type:
        failures.append(
            f"PRIVATE_TRACES_BLOB_URL has content-type {content_type!r}; expected JSON"
        )
        return []
    try:
        payload = json.loads(body)
    except json.JSONDecodeError as exc:
        failures.append(f"PRIVATE_TRACES_BLOB_URL body does not parse as JSON: {exc}")
        return []
    if isinstance(payload, dict) and payload.get("pythia_private_traces_encrypted") == 1:
        payload = _decrypt_blob_payload(payload, failures)
        if payload is None:
            return []
    if not isinstance(payload, list) or not payload:
        failures.append("PRIVATE_TRACES_BLOB_URL body is empty or not a JSON array")
        return []
    if not all(isinstance(entry, dict) for entry in payload):
        failures.append("PRIVATE_TRACES_BLOB_URL body must be an array of trace objects")
        return []
    return payload


def _b64url_decode(value: Any, label: str, failures: list[str]) -> bytes | None:
    if not isinstance(value, str) or not value:
        failures.append(f"PRIVATE_TRACES_BLOB_URL encrypted payload missing {label}")
        return None
    try:
        padding = "=" * (-len(value) % 4)
        return base64.urlsafe_b64decode(value + padding)
    except (ValueError, binascii.Error) as exc:
        failures.append(f"PRIVATE_TRACES_BLOB_URL encrypted payload has invalid {label}: {exc}")
        return None


def _private_traces_encryption_key(failures: list[str]) -> bytes | None:
    secret = (os.environ.get("PRIVATE_TRACES_ENCRYPTION_KEY") or "").strip()
    if not secret:
        failures.append(
            "PRIVATE_TRACES_BLOB_URL is encrypted but PRIVATE_TRACES_ENCRYPTION_KEY is unset"
        )
        return None
    if len(secret.encode("utf-8")) < _MIN_PRIVATE_TRACES_ENCRYPTION_KEY_BYTES:
        failures.append(
            "PRIVATE_TRACES_ENCRYPTION_KEY must be at least "
            f"{_MIN_PRIVATE_TRACES_ENCRYPTION_KEY_BYTES} bytes"
        )
        return None
    return hashlib.sha256(secret.encode("utf-8")).digest()


def _decrypt_blob_payload(payload: dict[str, Any], failures: list[str]) -> Any | None:
    if payload.get("alg") != "AES-256-GCM" or payload.get("kdf") != "sha256":
        failures.append("PRIVATE_TRACES_BLOB_URL encrypted payload uses unsupported crypto metadata")
        return None
    if payload.get("aad") != _PRIVATE_TRACE_AAD.decode():
        failures.append("PRIVATE_TRACES_BLOB_URL encrypted payload has unexpected aad")
        return None

    key = _private_traces_encryption_key(failures)
    nonce = _b64url_decode(payload.get("nonce"), "nonce", failures)
    tag = _b64url_decode(payload.get("tag"), "tag", failures)
    ciphertext = _b64url_decode(payload.get("ciphertext"), "ciphertext", failures)
    if key is None or nonce is None or tag is None or ciphertext is None:
        return None
    try:
        plaintext = _decrypt_aes_gcm(key, nonce, tag, ciphertext)
    except ValueError as exc:
        failures.append(f"PRIVATE_TRACES_BLOB_URL encrypted payload failed authentication: {exc}")
        return None
    try:
        return json.loads(plaintext)
    except json.JSONDecodeError as exc:
        failures.append(f"PRIVATE_TRACES_BLOB_URL decrypted body does not parse as JSON: {exc}")
        return None


def _decrypt_aes_gcm(key: bytes, nonce: bytes, tag: bytes, ciphertext: bytes) -> bytes:
    try:
        from Crypto.Cipher import AES  # type: ignore[import-not-found]

        cipher = AES.new(key, AES.MODE_GCM, nonce=nonce)
        cipher.update(_PRIVATE_TRACE_AAD)
        return cipher.decrypt_and_verify(ciphertext, tag)
    except ModuleNotFoundError:
        return _decrypt_aes_gcm_with_node(key, nonce, tag, ciphertext)


def _decrypt_aes_gcm_with_node(key: bytes, nonce: bytes, tag: bytes, ciphertext: bytes) -> bytes:
    script = r"""
const { createDecipheriv } = require("node:crypto");
const chunks = [];
process.stdin.on("data", (chunk) => chunks.push(chunk));
process.stdin.on("end", () => {
  try {
    const payload = JSON.parse(Buffer.concat(chunks).toString("utf8"));
    const decipher = createDecipheriv(
      "aes-256-gcm",
      Buffer.from(payload.key, "base64url"),
      Buffer.from(payload.nonce, "base64url"),
    );
    decipher.setAAD(Buffer.from("pythia-private-traces-v1", "utf8"));
    decipher.setAuthTag(Buffer.from(payload.tag, "base64url"));
    const plaintext = Buffer.concat([
      decipher.update(Buffer.from(payload.ciphertext, "base64url")),
      decipher.final(),
    ]);
    process.stdout.write(plaintext);
  } catch (err) {
    process.stderr.write(err?.message || String(err));
    process.exit(1);
  }
});
"""
    proc = subprocess.run(
        ["node", "-e", script],
        input=json.dumps(
            {
                "key": base64.urlsafe_b64encode(key).decode().rstrip("="),
                "nonce": base64.urlsafe_b64encode(nonce).decode().rstrip("="),
                "tag": base64.urlsafe_b64encode(tag).decode().rstrip("="),
                "ciphertext": base64.urlsafe_b64encode(ciphertext).decode().rstrip("="),
            }
        ).encode(),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if proc.returncode != 0:
        raise ValueError(proc.stderr.decode("utf-8", "replace") or "node AES-GCM decrypt failed")
    return proc.stdout


def _check_full_entries(
    entries: list[dict[str, Any]], failures: list[str], *, source_label: str
) -> None:
    for entry in entries:
        full = entry.get("full") or {}
        trace_id = entry.get("trace_id")
        entry_text = json.dumps(entry).lower()
        if any(marker.lower() in entry_text for marker in _FIXTURE_SOURCE_MARKERS):
            failures.append(f"{source_label} trace {trace_id}: full payload contains fixture source marker")
        if full.get("decision") == "HOLD":
            hold_entry_text = json.dumps(entry, ensure_ascii=False).lower()
            if any(marker in hold_entry_text for marker in _HOLD_ACTIONABLE_RECOMMENDATION_MARKERS):
                failures.append(
                    f"{source_label} trace {trace_id}: HOLD payload contains actionable recommendation language"
                )
            if full.get("copy_trade_url"):
                failures.append(f"{source_label} trace {trace_id}: HOLD full payload still has copy_trade_url")
            if float(full.get("suggested_size_usdc") or 0) != 0:
                failures.append(f"{source_label} trace {trace_id}: HOLD full payload has nonzero suggested_size_usdc")
            profile_sizes = full.get("suggested_size_by_profile") or {}
            if any(float(size or 0) != 0 for size in profile_sizes.values()):
                failures.append(f"{source_label} trace {trace_id}: HOLD full payload has nonzero profile size")
        sources = full.get("sources") or []
        if len(sources) < 3:
            failures.append(f"{source_label} trace {trace_id}: full payload has only {len(sources)} sources")
        if not any(isinstance(source, dict) and source.get("observed_at") for source in sources):
            failures.append(f"{source_label} trace {trace_id}: full payload sources lack observed_at")
        kinds = {str(source.get("kind") or "") for source in sources if isinstance(source, dict)}
        if not (_NON_MARKET_SOURCE_KINDS & kinds):
            failures.append(
                f"{source_label} trace {trace_id}: full payload sources lack a non-market kind "
                f"(have {sorted(kinds)}; need one of {sorted(_NON_MARKET_SOURCE_KINDS)})"
            )
        risks = full.get("risk_factors") or []
        if not risks:
            failures.append(f"{source_label} trace {trace_id}: full payload has no risk_factors")


def validate_repo(
    repo_root: Path, *, mode: str = "private-deploy", check_blob: bool = False
) -> list[str]:
    canonical = _MODE_ALIASES.get(mode)
    if canonical is None:
        raise ValueError(
            f"unknown mode: {mode!r}; expected one of {sorted(_MODE_ALIASES)}"
        )
    mode = canonical

    preview_path = repo_root / "web" / "data" / "picks-preview.json"
    public_full_path = repo_root / "web" / "data" / "picks-full.json"
    private_full_path = repo_root / "web" / "data" / "picks-full.private.json"

    preview_entries = _load_json(preview_path)
    failures: list[str] = []

    if public_full_path.exists():
        failures.append("public paid snapshot web/data/picks-full.json must not ship")

    full_entries: list[dict[str, Any]] = []
    blob_entries: list[dict[str, Any]] = []
    blob_url = os.environ.get("PRIVATE_TRACES_BLOB_URL")
    if mode == "private-deploy":
        if private_full_path.exists():
            full_entries = _load_json(private_full_path)
        elif blob_url:
            # Operator says the paid bundle lives in Vercel Blob; the URL is
            # trusted as-set unless `--check-blob` was passed (see below).
            # Full-payload quality checks are skipped in this branch — they
            # must be enforced upstream by publish_live_feed.py before upload.
            pass
        else:
            failures.append(
                "private-deploy mode: web/data/picks-full.private.json is missing AND "
                "PRIVATE_TRACES_BLOB_URL is unset"
            )
        if check_blob:
            if not blob_url:
                failures.append(
                    "--check-blob requires PRIVATE_TRACES_BLOB_URL to be set in the environment"
                )
            else:
                blob_entries = _fetch_blob_entries(blob_url, failures)
    # public-package mode intentionally ignores private_full_path: the
    # operator's working directory always has it after `publish_live_feed`,
    # but the zip builder in `scripts/package_submission.py` excludes
    # everything matching `web/data/picks-full*`. The shipped zip will not
    # contain the private bundle even when the working tree does.

    scan_roots = ("agent", "web", "traces", "README.md", "STATUS.md", "VERIFY.md", "docs")
    for pattern in _WRONG_FOMC_PATTERNS:
        paths = _scan_text(repo_root, pattern, scan_roots)
        if paths:
            failures.append(f"wrong FOMC date pattern {pattern!r} appears in {paths}")
    stale_copy_paths = _scan_text(repo_root, _STALE_USDC_COPY, scan_roots)
    if stale_copy_paths:
        failures.append(f"stale unlock-price copy appears in {stale_copy_paths}")
    for marker in _FIXTURE_SOURCE_MARKERS:
        fixture_paths = _scan_text(repo_root, marker, scan_roots)
        if fixture_paths:
            failures.append(f"fixture source marker {marker!r} appears in {fixture_paths}")
    for pattern in _STALE_TEST_COUNT_PATTERNS:
        stale_test_paths = _scan_text(repo_root, pattern, ("README.md", "STATUS.md", "VERIFY.md", "docs"))
        if stale_test_paths:
            failures.append(f"stale test-count claim {pattern!r} appears in {stale_test_paths}")

    for entry in preview_entries:
        trace_id = entry.get("trace_id")
        leaked = _PREVIEW_FORBIDDEN_KEYS & set(entry)
        if leaked:
            failures.append(f"trace {trace_id}: preview bundle leaks {sorted(leaked)}")
        preview_text = json.dumps(entry).lower()
        if any(marker.lower() in preview_text for marker in _FIXTURE_SOURCE_MARKERS):
            failures.append(f"trace {trace_id}: preview bundle contains fixture source marker")

    eligible = _eligible_home_entries(preview_entries)
    home = _latest_by_market(eligible)
    questions = Counter((entry.get("preview") or {}).get("question") for entry in home)
    duplicate_questions = sorted(q for q, count in questions.items() if count > 1)
    if len(home) < 8:
        failures.append(f"home feed has {len(home)} unique anchored LLM markets; expected >= 8")
    if duplicate_questions:
        failures.append(f"home feed has duplicate questions: {duplicate_questions}")

    _check_full_entries(full_entries, failures, source_label="trace")
    if blob_entries:
        _check_full_entries(blob_entries, failures, source_label="PRIVATE_TRACES_BLOB_URL")

    public_trace_files = sorted((repo_root / "traces").glob("trace-*.json")) if (repo_root / "traces").exists() else []
    if public_trace_files:
        names = [str(path.relative_to(repo_root)) for path in public_trace_files[:5]]
        more = "" if len(public_trace_files) <= 5 else f" and {len(public_trace_files) - 5} more"
        failures.append(f"public traces/ contains production trace JSON: {names}{more}")

    preview_ids = {entry.get("trace_id") for entry in preview_entries}
    full_ids = {entry.get("trace_id") for entry in full_entries}
    if full_entries and preview_ids != full_ids:
        failures.append(f"private full trace ids {sorted(full_ids)} do not match preview ids {sorted(preview_ids)}")
    blob_ids = {entry.get("trace_id") for entry in blob_entries}
    if blob_entries and preview_ids != blob_ids:
        failures.append(
            f"PRIVATE_TRACES_BLOB_URL full trace ids {sorted(blob_ids)} "
            f"do not match preview ids {sorted(preview_ids)}"
        )

    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mode",
        choices=("private-deploy", "public-package", "deploy", "package"),
        default="private-deploy",
        help=(
            "private-deploy (default): live Vercel state — requires the paid full "
            "bundle locally OR PRIVATE_TRACES_BLOB_URL. "
            "public-package: contents of the public submission zip — forbids the "
            "paid bundle. "
            "'deploy'/'package' are accepted aliases for back-compat."
        ),
    )
    parser.add_argument(
        "--check-blob",
        action="store_true",
        help=(
            "private-deploy mode only: fetch PRIVATE_TRACES_BLOB_URL and assert it "
            "serves the same full trace IDs as web/data/picks-preview.json and "
            "passes full-payload quality checks. Catches typo'd, truncated, or "
            "stale Blob URLs in the Vercel env before promoting a deploy."
        ),
    )
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[3]
    failures = validate_repo(repo_root, mode=args.mode, check_blob=args.check_blob)
    if failures:
        for failure in failures:
            print(f"FAIL: {failure}", file=sys.stderr)
        return 1

    preview_entries = _load_json(repo_root / "web" / "data" / "picks-preview.json")
    home = _latest_by_market(_eligible_home_entries(preview_entries))
    private_full_path = repo_root / "web" / "data" / "picks-full.private.json"
    canonical_mode = _MODE_ALIASES[args.mode]
    if canonical_mode == "private-deploy" and private_full_path.exists():
        full_entries = _load_json(private_full_path)
        print(
            f"submission data ok (private-deploy): {len(home)} home markets, "
            f"{len(full_entries)} private full traces"
        )
    elif canonical_mode == "private-deploy":
        print(
            f"submission data ok (private-deploy): {len(home)} home markets, "
            "private bundle served from PRIVATE_TRACES_BLOB_URL"
        )
    else:
        print(
            f"submission data ok (public-package): {len(home)} home markets, "
            "no paid bundle present"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
