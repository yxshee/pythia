/**
 * Lazy Vercel KV client. Returns `null` when the runtime is not configured
 * for KV (no `KV_REST_API_URL` / `KV_REST_API_TOKEN`), so callers fall back
 * to per-instance in-memory state.
 *
 * Why lazy: the `@vercel/kv` module reads env vars at import time. Importing
 * it in environments without those vars set (local dev, unit tests, CI)
 * raises. Wrapping the import behind a getter keeps this file safe to
 * import everywhere.
 */
import type { VercelKV } from "@vercel/kv";

let cached: VercelKV | null | undefined;

export function getKv(): VercelKV | null {
  if (cached !== undefined) return cached;
  if (!process.env.KV_REST_API_URL || !process.env.KV_REST_API_TOKEN) {
    cached = null;
    return cached;
  }
  // Lazy require keeps the import out of the module graph when KV is
  // unset — avoids '@vercel/kv' crashing at import in plain Node.
  // eslint-disable-next-line @typescript-eslint/no-require-imports
  const mod = require("@vercel/kv") as typeof import("@vercel/kv");
  cached = mod.kv;
  return cached;
}
