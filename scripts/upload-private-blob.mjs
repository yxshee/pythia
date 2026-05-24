#!/usr/bin/env node
/**
 * Upload `web/data/picks-full.private.json` to Vercel Blob.
 *
 * The Blob URL embeds a random suffix and IS the access secret. It is written
 * only to the gitignored `web/data/.blob-url` cache; stdout prints a redacted
 * status message so shell logs do not leak the URL.
 *
 * Usage (from repo root):
 *   BLOB_READ_WRITE_TOKEN=... node scripts/upload-private-blob.mjs
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
import { chmod, readFile, writeFile } from "node:fs/promises";
import { existsSync } from "node:fs";
import { resolve } from "node:path";

const REPO_ROOT = resolve(new URL("..", import.meta.url).pathname);
const SOURCE = resolve(REPO_ROOT, "web/data/picks-full.private.json");
const URL_CACHE = resolve(REPO_ROOT, "web/data/.blob-url");

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
  try {
    const result = await put("picks-full.private.json", data, {
      access: "public",
      addRandomSuffix: true,
      contentType: "application/json",
      token,
    });
    await writeFile(URL_CACHE, result.url + "\n", { encoding: "utf-8", mode: 0o600 });
    await chmod(URL_CACHE, 0o600);
    console.log("uploaded picks-full.private.json; wrote secret URL to web/data/.blob-url");
    process.exit(0);
  } catch (err) {
    console.error("blob put failed:", err?.message ?? err);
    process.exit(4);
  }
}

main();
