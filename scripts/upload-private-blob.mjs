#!/usr/bin/env node
/**
 * Upload `web/data/picks-full.private.json` to Vercel Blob.
 *
 * The Blob URL embeds a random suffix, but it is not the only access control:
 * the payload is AES-256-GCM encrypted with PRIVATE_TRACES_ENCRYPTION_KEY
 * before upload. The URL is written only to the gitignored `web/data/.blob-url`
 * cache; stdout prints a redacted status message so shell logs do not leak it.
 *
 * Usage (from repo root):
 *   BLOB_READ_WRITE_TOKEN=... PRIVATE_TRACES_ENCRYPTION_KEY=... \
 *     node scripts/upload-private-blob.mjs
 *
 * Or invoked indirectly by `publish_live_feed.py --upload-blob`.
 *
 * Exit codes:
 *   0  uploaded; URL written to web/data/.blob-url
 *   2  token missing
 *   3  source file missing or unreadable
 *   4  upload failed
 */
import { put } from "@vercel/blob";
import { createCipheriv, createHash, randomBytes } from "node:crypto";
import { chmod, readFile, writeFile } from "node:fs/promises";
import { existsSync } from "node:fs";
import { resolve } from "node:path";

const REPO_ROOT = resolve(new URL("..", import.meta.url).pathname);
const SOURCE = resolve(REPO_ROOT, "web/data/picks-full.private.json");
const URL_CACHE = resolve(REPO_ROOT, "web/data/.blob-url");
const AAD = Buffer.from("pythia-private-traces-v1", "utf8");
const MIN_PRIVATE_TRACES_ENCRYPTION_KEY_BYTES = 32;

function base64url(bytes) {
  return Buffer.from(bytes).toString("base64url");
}

function encryptionKey() {
  const secret = process.env.PRIVATE_TRACES_ENCRYPTION_KEY?.trim();
  if (!secret) {
    console.error("PRIVATE_TRACES_ENCRYPTION_KEY is required");
    process.exit(2);
  }
  if (Buffer.byteLength(secret, "utf8") < MIN_PRIVATE_TRACES_ENCRYPTION_KEY_BYTES) {
    console.error(
      `PRIVATE_TRACES_ENCRYPTION_KEY must be at least ${MIN_PRIVATE_TRACES_ENCRYPTION_KEY_BYTES} bytes`,
    );
    process.exit(2);
  }
  return createHash("sha256").update(secret, "utf8").digest();
}

function encryptPrivateBundle(data) {
  const nonce = randomBytes(12);
  const cipher = createCipheriv("aes-256-gcm", encryptionKey(), nonce);
  cipher.setAAD(AAD);
  const ciphertext = Buffer.concat([cipher.update(data), cipher.final()]);
  const tag = cipher.getAuthTag();
  return Buffer.from(
    JSON.stringify({
      pythia_private_traces_encrypted: 1,
      alg: "AES-256-GCM",
      kdf: "sha256",
      aad: AAD.toString("utf8"),
      nonce: base64url(nonce),
      tag: base64url(tag),
      ciphertext: base64url(ciphertext),
    }),
  );
}

async function main() {
  const token = process.env.BLOB_READ_WRITE_TOKEN;
  if (!token) {
    console.error("BLOB_READ_WRITE_TOKEN is required");
    process.exit(2);
  }
  if (!existsSync(SOURCE)) {
    console.error(`source not found: ${SOURCE}`);
    process.exit(3);
  }
  const data = await readFile(SOURCE);
  const encrypted = encryptPrivateBundle(data);
  try {
    const result = await put("picks-full.private.enc.json", encrypted, {
      access: "public",
      addRandomSuffix: true,
      contentType: "application/json",
      token,
    });
    await writeFile(URL_CACHE, result.url + "\n", { encoding: "utf-8", mode: 0o600 });
    await chmod(URL_CACHE, 0o600);
    console.log("uploaded encrypted picks-full.private.json; wrote secret URL to web/data/.blob-url");
    process.exit(0);
  } catch (err) {
    console.error("blob put failed:", err?.message ?? err);
    process.exit(4);
  }
}

main();
