import pathlib
import re
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]


class SecretHandlingTests(unittest.TestCase):
    def test_private_blob_uploader_does_not_print_secret_url(self) -> None:
        source = (ROOT / "scripts" / "upload-private-blob.mjs").read_text()

        self.assertNotRegex(source, re.compile(r"console\.log\([^)]*result\.url"))
        self.assertIn("URL_CACHE", source)
        self.assertIn("writeFile(URL_CACHE", source)

    def test_publish_live_feed_does_not_reprint_blob_url(self) -> None:
        source = (ROOT / "agent" / "pythia" / "scripts" / "publish_live_feed.py").read_text()

        self.assertNotIn("blob_url = result.stdout.strip()", source)
        self.assertNotIn("uploaded picks-full.private.json to:", source)
        self.assertIn("web/data/.blob-url", source)

    def test_paywall_nonce_uses_dedicated_hmac_secret(self) -> None:
        source = (ROOT / "web" / "lib" / "server" / "paywall-nonce.ts").read_text()
        nonce_secret = re.search(
            r"function nonceSecret\(\): string \{(?P<body>.*?)\n\}",
            source,
            re.DOTALL,
        )
        self.assertIsNotNone(nonce_secret)
        body = nonce_secret.group("body")

        self.assertIn("process.env.PAYWALL_NONCE_SECRET", body)
        self.assertIn("productionRequiresDurableState()", body)
        self.assertNotIn("BLOB_READ_WRITE_TOKEN", body)
        self.assertNotIn("KV_REST_API_TOKEN", body)

    def test_paywall_nonce_rejects_weak_hmac_secret(self) -> None:
        source = (ROOT / "web" / "lib" / "server" / "paywall-nonce.ts").read_text()
        nonce_secret = re.search(
            r"function nonceSecret\(\): string \{(?P<body>.*?)\n\}",
            source,
            re.DOTALL,
        )
        self.assertIsNotNone(nonce_secret)
        body = nonce_secret.group("body")

        self.assertIn("MIN_PAYWALL_NONCE_SECRET_BYTES", source)
        self.assertRegex(source, r"MIN_PAYWALL_NONCE_SECRET_BYTES\s*=\s*32")
        self.assertIn('Buffer.byteLength(secret, "utf8")', body)
        self.assertIn("StateStoreUnavailableError", body)
