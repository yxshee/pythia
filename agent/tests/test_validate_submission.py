from __future__ import annotations

import contextlib
import base64
import hashlib
import http.server
import json
import os
import socketserver
import tempfile
import threading
import unittest
from pathlib import Path
from typing import Iterator
from unittest import mock

from Crypto.Cipher import AES

from pythia.scripts.validate_submission import validate_repo


def _entry(trace_id: int, *, question: str | None = None, decision: str = "BUY_YES") -> dict:
    q = question or f"Will live market {trace_id} resolve yes?"
    return {
        "trace_id": trace_id,
        "generated_at": f"2026-05-23T00:{trace_id:02d}:00+00:00",
        "market_id": f"0x{trace_id:064x}",
        "model": "claude-sonnet-4-6",
        "theme": "crypto",
        "vault": None,
        "onchain": {
            "tx_hash": f"0x{trace_id:064x}",
            "block_number": trace_id,
            "trace_id": trace_id,
            "publisher": "0x0000000000000000000000000000000000000001",
            "contract": "0x0000000000000000000000000000000000000002",
            "chain_id": 5042002,
        },
        "preview": {
            "trace_id": trace_id,
            "trace_hash": f"0x{trace_id + 1:064x}",
            "market_id": f"0x{trace_id:064x}",
            "question": q,
            "current_implied_yes": 0.42,
            "agent_probability_yes": 0.48,
            "decision": decision,
            "confidence": "medium",
            "risk": "balanced",
            "model": "claude-sonnet-4-6",
            "generated_at": f"2026-05-23T00:{trace_id:02d}:00+00:00",
            "end_date_iso": "2026-12-31T23:59:59Z",
        },
    }


def _full_entry(
    trace_id: int,
    *,
    decision: str = "BUY_YES",
    fixture_source: bool = False,
    source_name: str | None = None,
    reasoning_text: str | None = None,
) -> dict:
    entry = _entry(trace_id, decision=decision)
    market_source_name = source_name or (("Offline market " + "fixture") if fixture_source else "Polymarket Gamma")
    reasoning = reasoning_text or "Resolution timing can still surprise the market."
    entry["full"] = {
        **entry["preview"],
        "edge_bps": 600,
        "expected_value_pct": 4.2,
        "suggested_size_usdc": 12.0 if decision != "HOLD" else 0.0,
        "suggested_size_by_profile": {"conservative": 4.8, "balanced": 12.0, "aggressive": 19.2},
        "reasoning": [{"kind": "risk", "text": reasoning}],
        "sources": [
            {"kind": "model", "name": "claude-sonnet-4-6", "observed_at": "2026-05-23T00:00:00+00:00"},
            {
                "kind": "market_data",
                "name": market_source_name,
                "url": "https://polymarket.com/event/live-market",
                "observed_at": "2026-05-23T00:00:00+00:00",
            },
            {
                "kind": "resolution_criteria",
                "name": "Market resolution text",
                "url": "https://polymarket.com/event/live-market",
                "observed_at": "2026-05-23T00:00:00+00:00",
            },
            {
                "kind": "event_data",
                "name": "Official resolution source",
                "url": "https://example.com/event-source",
                "observed_at": "2026-05-23T00:00:00+00:00",
                "credibility": 0.9,
                "relevance": 0.95,
                "recency": 0.9,
            },
        ],
        "risk_factors": ["Resolution timing can still surprise the market."],
        "market_url": "https://polymarket.com/event/live-market",
        "copy_trade_url": None if decision == "HOLD" else "https://polymarket.com/event/live-market?side=yes",
        "market_volume_24h_usd": 100_000,
        "market_liquidity_usd": 100_000,
    }
    return entry


def _scaffold(root: Path) -> None:
    (root / "web" / "data").mkdir(parents=True)
    (root / "web" / "components").mkdir(parents=True)
    (root / "agent").mkdir()
    (root / "README.md").write_text("Public README")
    (root / "STATUS.md").write_text("Production paid traces are private.")
    (root / "docs").mkdir()
    (root / "web" / "components" / "pick-card.tsx").write_text("Unlock 0.10 DevUSDC")


class ValidateSubmissionDeployModeTests(unittest.TestCase):
    def test_accepts_private_full_snapshot_and_public_preview_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _scaffold(root)
            preview = [_entry(i) for i in range(1, 9)]
            full = [_full_entry(i) for i in range(1, 9)]
            (root / "web" / "data" / "picks-preview.json").write_text(json.dumps(preview))
            (root / "web" / "data" / "picks-full.private.json").write_text(json.dumps(full))

            self.assertEqual(validate_repo(root, mode="deploy"), [])

    def test_accepts_blob_url_when_local_file_absent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _scaffold(root)
            preview = [_entry(i) for i in range(1, 9)]
            (root / "web" / "data" / "picks-preview.json").write_text(json.dumps(preview))

            with mock.patch.dict(os.environ, {"PRIVATE_TRACES_BLOB_URL": "https://blob.example/abc"}):
                self.assertEqual(validate_repo(root, mode="deploy"), [])

    def test_rejects_when_both_private_file_and_blob_url_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _scaffold(root)
            preview = [_entry(i) for i in range(1, 9)]
            (root / "web" / "data" / "picks-preview.json").write_text(json.dumps(preview))

            env = {k: v for k, v in os.environ.items() if k != "PRIVATE_TRACES_BLOB_URL"}
            with mock.patch.dict(os.environ, env, clear=True):
                failures = validate_repo(root, mode="deploy")
            self.assertTrue(
                any("picks-full.private.json is missing" in f for f in failures),
                failures,
            )

    def test_rejects_full_payload_without_non_market_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _scaffold(root)
            preview = [_entry(i) for i in range(1, 9)]
            full = [_full_entry(i) for i in range(1, 9)]
            # Drop the non-market source from entry #1 to trigger the check.
            full[0]["full"]["sources"] = [
                source for source in full[0]["full"]["sources"]
                if source.get("kind") != "event_data"
            ]
            (root / "web" / "data" / "picks-preview.json").write_text(json.dumps(preview))
            (root / "web" / "data" / "picks-full.private.json").write_text(json.dumps(full))

            failures = validate_repo(root, mode="deploy")
            self.assertTrue(
                any("lack a non-market kind" in f for f in failures),
                failures,
            )

    def test_rejects_hold_payload_with_buy_recommendation_language(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _scaffold(root)
            preview = [_entry(i, decision="HOLD" if i == 1 else "BUY_YES") for i in range(1, 9)]
            full = [
                _full_entry(
                    i,
                    decision="HOLD" if i == 1 else "BUY_YES",
                    reasoning_text="A BUY YES is justifiable despite the final action.",
                )
                if i == 1
                else _full_entry(i)
                for i in range(1, 9)
            ]
            (root / "web" / "data" / "picks-preview.json").write_text(json.dumps(preview))
            (root / "web" / "data" / "picks-full.private.json").write_text(json.dumps(full))

            failures = validate_repo(root, mode="deploy")

            self.assertTrue(
                any("HOLD payload contains actionable recommendation language" in f for f in failures),
                failures,
            )

    def test_rejects_hold_payload_with_buy_language_outside_served_full(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _scaffold(root)
            preview = [_entry(i, decision="HOLD" if i == 1 else "BUY_YES") for i in range(1, 9)]
            full = [
                _full_entry(i, decision="HOLD" if i == 1 else "BUY_YES")
                if i == 1
                else _full_entry(i)
                for i in range(1, 9)
            ]
            full[0]["analyst"] = {
                "reasoning": [
                    {
                        "kind": "conclusion",
                        "text": "A BUY YES is justifiable despite the final action.",
                    }
                ]
            }
            (root / "web" / "data" / "picks-preview.json").write_text(json.dumps(preview))
            (root / "web" / "data" / "picks-full.private.json").write_text(json.dumps(full))

            failures = validate_repo(root, mode="deploy")

            self.assertTrue(
                any("HOLD payload contains actionable recommendation language" in f for f in failures),
                failures,
            )

    def test_rejects_synthetic_fixture_market_data_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _scaffold(root)
            preview = [_entry(i) for i in range(1, 9)]
            full = [
                _full_entry(i, source_name=("Synthetic fixture " + "market data") if i == 1 else None)
                for i in range(1, 9)
            ]
            (root / "web" / "data" / "picks-preview.json").write_text(json.dumps(preview))
            (root / "web" / "data" / "picks-full.private.json").write_text(json.dumps(full))

            failures = validate_repo(root, mode="deploy")

            self.assertTrue(any("fixture source marker" in failure for failure in failures), failures)

    def test_rejects_public_full_snapshot_fixture_source_wrong_dates_and_stale_copy(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _scaffold(root)
            (root / "agent" / "fixtures.py").write_text("June " + "17-18 2026-06-" + "18")
            (root / "web" / "components" / "pick-card.tsx").write_text("Unlock 0.10 " + "USDC")

            preview = [_entry(i) for i in range(1, 9)]
            full = [_full_entry(i, fixture_source=i == 1) for i in range(1, 9)]
            (root / "web" / "data" / "picks-preview.json").write_text(json.dumps(preview))
            (root / "web" / "data" / "picks-full.json").write_text(json.dumps(full))

            failures = validate_repo(root, mode="deploy")

            self.assertTrue(any("public paid snapshot" in failure for failure in failures))
            self.assertTrue(any("fixture source" in failure for failure in failures))
            self.assertTrue(any("wrong FOMC" in failure for failure in failures))
            self.assertTrue(any("stale unlock-price copy" in failure for failure in failures))

    def test_rejects_stale_test_count_claims(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _scaffold(root)
            preview = [_entry(i) for i in range(1, 9)]
            full = [_full_entry(i) for i in range(1, 9)]
            (root / "web" / "data" / "picks-preview.json").write_text(json.dumps(preview))
            (root / "web" / "data" / "picks-full.private.json").write_text(json.dumps(full))
            (root / "README.md").write_text("tests 61/61 passing")

            failures = validate_repo(root, mode="deploy")

            self.assertTrue(any("stale test-count claim" in failure for failure in failures), failures)


@contextlib.contextmanager
def _serve_blob(routes: dict[str, tuple[int, str, bytes]]) -> Iterator[str]:
    """Run a stdlib HTTP server on a random local port that maps paths to
    (status, content-type, body). Paths not in `routes` return 404."""

    class _Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 (stdlib API)
            entry = routes.get(self.path)
            if entry is None:
                self.send_response(404)
                self.send_header("Content-Type", "text/plain")
                self.end_headers()
                self.wfile.write(b"not found")
                return
            status, ctype, body = entry
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_args, **_kwargs) -> None:  # silence
            return

    server = socketserver.TCPServer(("127.0.0.1", 0), _Handler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def _encrypted_blob_payload(entries: list[dict], key: str) -> bytes:
    nonce = bytes(range(12))
    cipher = AES.new(hashlib.sha256(key.encode()).digest(), AES.MODE_GCM, nonce=nonce)
    cipher.update(b"pythia-private-traces-v1")
    ciphertext, tag = cipher.encrypt_and_digest(json.dumps(entries).encode())
    return json.dumps(
        {
            "pythia_private_traces_encrypted": 1,
            "alg": "AES-256-GCM",
            "kdf": "sha256",
            "aad": "pythia-private-traces-v1",
            "nonce": _b64url(nonce),
            "tag": _b64url(tag),
            "ciphertext": _b64url(ciphertext),
        }
    ).encode()


class ValidateSubmissionCheckBlobTests(unittest.TestCase):
    """`--check-blob` flag: live HEAD/GET against PRIVATE_TRACES_BLOB_URL."""

    def _scaffold_deploy_tree(self, root: Path) -> None:
        _scaffold(root)
        preview = [_entry(i) for i in range(1, 9)]
        (root / "web" / "data" / "picks-preview.json").write_text(json.dumps(preview))

    def test_check_blob_flag_fails_when_url_is_404(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._scaffold_deploy_tree(root)
            with _serve_blob({}) as base:
                url = f"{base}/picks-full.private.json"
                with mock.patch.dict(os.environ, {"PRIVATE_TRACES_BLOB_URL": url}):
                    failures = validate_repo(root, mode="deploy", check_blob=True)
            self.assertTrue(
                any("PRIVATE_TRACES_BLOB_URL" in failure and "404" in failure for failure in failures),
                failures,
            )
            self.assertFalse(any(url in failure for failure in failures), failures)

    def test_check_blob_flag_fails_when_url_is_not_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._scaffold_deploy_tree(root)
            with _serve_blob(
                {"/picks-full.private.json": (200, "text/html", b"<html>oops</html>")}
            ) as base:
                url = f"{base}/picks-full.private.json"
                with mock.patch.dict(os.environ, {"PRIVATE_TRACES_BLOB_URL": url}):
                    failures = validate_repo(root, mode="deploy", check_blob=True)
            self.assertTrue(
                any("PRIVATE_TRACES_BLOB_URL" in failure and "content-type" in failure for failure in failures),
                failures,
            )
            self.assertFalse(any(url in failure for failure in failures), failures)

    def test_check_blob_flag_fails_when_url_is_empty_list(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._scaffold_deploy_tree(root)
            key = "test-private-traces-key-with-32-bytes-minimum"
            body = _encrypted_blob_payload([], key)
            with _serve_blob(
                {"/picks-full.private.json.enc": (200, "application/json", body)}
            ) as base:
                url = f"{base}/picks-full.private.json.enc"
                with mock.patch.dict(
                    os.environ,
                    {
                        "PRIVATE_TRACES_BLOB_URL": url,
                        "PRIVATE_TRACES_ENCRYPTION_KEY": key,
                    },
                ):
                    failures = validate_repo(root, mode="deploy", check_blob=True)
            self.assertTrue(
                any("PRIVATE_TRACES_BLOB_URL" in failure and "empty" in failure for failure in failures),
                failures,
            )
            self.assertFalse(any(url in failure for failure in failures), failures)

    def test_check_blob_flag_rejects_plaintext_json_blob(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._scaffold_deploy_tree(root)
            body = json.dumps([_full_entry(i) for i in range(1, 9)]).encode()
            with _serve_blob(
                {"/picks-full.private.json": (200, "application/json", body)}
            ) as base:
                url = f"{base}/picks-full.private.json"
                with mock.patch.dict(os.environ, {"PRIVATE_TRACES_BLOB_URL": url}):
                    failures = validate_repo(root, mode="deploy", check_blob=True)
            self.assertTrue(
                any("must be encrypted" in failure for failure in failures),
                failures,
            )

    def test_check_blob_flag_decrypts_encrypted_blob_when_key_set(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._scaffold_deploy_tree(root)
            key = "test-private-traces-key-with-32-bytes-minimum"
            body = _encrypted_blob_payload([_full_entry(i) for i in range(1, 9)], key)
            with _serve_blob(
                {"/picks-full.private.json.enc": (200, "application/json", body)}
            ) as base:
                url = f"{base}/picks-full.private.json.enc"
                with mock.patch.dict(
                    os.environ,
                    {
                        "PRIVATE_TRACES_BLOB_URL": url,
                        "PRIVATE_TRACES_ENCRYPTION_KEY": key,
                    },
                ):
                    failures = validate_repo(root, mode="deploy", check_blob=True)
            self.assertEqual(failures, [])

    def test_check_blob_flag_rejects_encrypted_blob_without_key(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._scaffold_deploy_tree(root)
            key = "test-private-traces-key-with-32-bytes-minimum"
            body = _encrypted_blob_payload([_full_entry(i) for i in range(1, 9)], key)
            with _serve_blob(
                {"/picks-full.private.json.enc": (200, "application/json", body)}
            ) as base:
                url = f"{base}/picks-full.private.json.enc"
                env = {k: v for k, v in os.environ.items() if k != "PRIVATE_TRACES_ENCRYPTION_KEY"}
                env["PRIVATE_TRACES_BLOB_URL"] = url
                with mock.patch.dict(os.environ, env, clear=True):
                    failures = validate_repo(root, mode="deploy", check_blob=True)
            self.assertTrue(
                any("PRIVATE_TRACES_ENCRYPTION_KEY" in failure for failure in failures),
                failures,
            )

    def test_check_blob_flag_fails_when_blob_trace_ids_do_not_match_preview(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _scaffold(root)
            preview = [_entry(i) for i in range(24, 32)]
            local_full = [_full_entry(i) for i in range(24, 32)]
            old_blob_full = [_full_entry(i) for i in range(9, 17)]
            (root / "web" / "data" / "picks-preview.json").write_text(json.dumps(preview))
            (root / "web" / "data" / "picks-full.private.json").write_text(json.dumps(local_full))
            key = "test-private-traces-key-with-32-bytes-minimum"
            body = _encrypted_blob_payload(old_blob_full, key)

            with _serve_blob(
                {"/picks-full.private.json.enc": (200, "application/json", body)}
            ) as base:
                url = f"{base}/picks-full.private.json.enc"
                with mock.patch.dict(
                    os.environ,
                    {
                        "PRIVATE_TRACES_BLOB_URL": url,
                        "PRIVATE_TRACES_ENCRYPTION_KEY": key,
                    },
                ):
                    failures = validate_repo(root, mode="deploy", check_blob=True)

            self.assertTrue(
                any("do not match preview ids" in failure for failure in failures),
                failures,
            )

    def test_check_blob_flag_compares_against_raw_preview_ids_not_home_projection(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _scaffold(root)
            preview = [_entry(i) for i in range(24, 33)]
            preview[0]["onchain"]["tx_hash"] = ""
            blob_full = [_full_entry(i) for i in range(25, 33)]
            (root / "web" / "data" / "picks-preview.json").write_text(json.dumps(preview))
            key = "test-private-traces-key-with-32-bytes-minimum"
            body = _encrypted_blob_payload(blob_full, key)

            with _serve_blob(
                {"/picks-full.private.json.enc": (200, "application/json", body)}
            ) as base:
                url = f"{base}/picks-full.private.json.enc"
                with mock.patch.dict(
                    os.environ,
                    {
                        "PRIVATE_TRACES_BLOB_URL": url,
                        "PRIVATE_TRACES_ENCRYPTION_KEY": key,
                    },
                ):
                    failures = validate_repo(root, mode="deploy", check_blob=True)

            self.assertTrue(
                any("do not match preview ids" in failure for failure in failures),
                failures,
            )

    def test_check_blob_flag_runs_full_payload_quality_checks_on_blob_entries(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _scaffold(root)
            preview = [_entry(i) for i in range(24, 32)]
            local_full = [_full_entry(i) for i in range(24, 32)]
            blob_full = [_full_entry(i) for i in range(24, 32)]
            blob_full[0]["full"]["sources"] = [
                source for source in blob_full[0]["full"]["sources"]
                if source.get("kind") != "event_data"
            ]
            (root / "web" / "data" / "picks-preview.json").write_text(json.dumps(preview))
            (root / "web" / "data" / "picks-full.private.json").write_text(json.dumps(local_full))
            key = "test-private-traces-key-with-32-bytes-minimum"
            body = _encrypted_blob_payload(blob_full, key)

            with _serve_blob(
                {"/picks-full.private.json.enc": (200, "application/json", body)}
            ) as base:
                url = f"{base}/picks-full.private.json.enc"
                with mock.patch.dict(
                    os.environ,
                    {
                        "PRIVATE_TRACES_BLOB_URL": url,
                        "PRIVATE_TRACES_ENCRYPTION_KEY": key,
                    },
                ):
                    failures = validate_repo(root, mode="deploy", check_blob=True)

            self.assertTrue(
                any("lack a non-market kind" in failure for failure in failures),
                failures,
            )

    def test_check_blob_flag_fails_when_env_var_unset(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._scaffold_deploy_tree(root)
            env = {k: v for k, v in os.environ.items() if k != "PRIVATE_TRACES_BLOB_URL"}
            with mock.patch.dict(os.environ, env, clear=True):
                failures = validate_repo(root, mode="deploy", check_blob=True)
            self.assertTrue(
                any("PRIVATE_TRACES_BLOB_URL" in failure and "--check-blob" in failure for failure in failures),
                failures,
            )


class ValidateSubmissionPackageModeTests(unittest.TestCase):
    def test_accepts_preview_only_zip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _scaffold(root)
            preview = [_entry(i) for i in range(1, 9)]
            (root / "web" / "data" / "picks-preview.json").write_text(json.dumps(preview))

            self.assertEqual(validate_repo(root, mode="package"), [])

    def test_ignores_private_full_in_working_tree(self) -> None:
        # The operator's working directory always contains the private bundle
        # after `publish_live_feed`. Package mode must not flag it as a
        # failure — the exclusion guarantee lives in `scripts/package_submission.py`
        # (see `should_exclude` rule for `web/data/picks-full*`), so the
        # shipped zip never includes the private file even when the working
        # tree does.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _scaffold(root)
            preview = [_entry(i) for i in range(1, 9)]
            full = [_full_entry(i) for i in range(1, 9)]
            (root / "web" / "data" / "picks-preview.json").write_text(json.dumps(preview))
            (root / "web" / "data" / "picks-full.private.json").write_text(json.dumps(full))

            self.assertEqual(validate_repo(root, mode="package"), [])

    def test_rejects_public_full_present_in_package(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _scaffold(root)
            preview = [_entry(i) for i in range(1, 9)]
            full = [_full_entry(i) for i in range(1, 9)]
            (root / "web" / "data" / "picks-preview.json").write_text(json.dumps(preview))
            (root / "web" / "data" / "picks-full.json").write_text(json.dumps(full))

            failures = validate_repo(root, mode="package")
            self.assertTrue(
                any("public paid snapshot" in f for f in failures),
                failures,
            )


class ValidateSubmissionModeAliasTests(unittest.TestCase):
    """Old mode names ('deploy', 'package') remain aliases for the canonical
    names ('private-deploy', 'public-package') so STATUS.md / README.md
    examples keep working while docs are updated."""

    def _staged_repo(self, root: Path) -> None:
        _scaffold(root)
        preview = [_entry(i) for i in range(1, 9)]
        full = [_full_entry(i) for i in range(1, 9)]
        (root / "web" / "data" / "picks-preview.json").write_text(json.dumps(preview))
        (root / "web" / "data" / "picks-full.private.json").write_text(json.dumps(full))

    def test_private_deploy_matches_deploy_alias(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._staged_repo(root)
            self.assertEqual(
                validate_repo(root, mode="private-deploy"),
                validate_repo(root, mode="deploy"),
            )

    def test_public_package_matches_package_alias(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._staged_repo(root)
            self.assertEqual(
                validate_repo(root, mode="public-package"),
                validate_repo(root, mode="package"),
            )

    def test_unknown_mode_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._staged_repo(root)
            with self.assertRaisesRegex(ValueError, "unknown mode"):
                validate_repo(root, mode="not-a-real-mode")


if __name__ == "__main__":
    unittest.main()
