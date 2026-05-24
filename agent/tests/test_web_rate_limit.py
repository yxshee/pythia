import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]


class WebRateLimitStateTests(unittest.TestCase):
    def test_rate_limit_does_not_use_blob_as_counter_store(self) -> None:
        source = (ROOT / "web" / "lib" / "server" / "rate-limit.ts").read_text()

        self.assertNotIn("getBlobStateClient", source)
        self.assertNotIn("productionRequiresDurableState", source)
        self.assertNotIn("paywall/rate-limit", source)

    def test_docs_do_not_claim_blob_backed_rate_limit_fallback(self) -> None:
        for rel_path in ["web/README.md", "web/.env.local.example", "web/lib/server/kv.ts"]:
            with self.subTest(path=rel_path):
                text = (ROOT / rel_path).read_text()
                self.assertNotIn("durable Blob fallback", text)
                self.assertNotIn("durable nonce/rate-limit fallback", text)
                self.assertNotIn("durable Blob-backed state store", text)

