import "server-only";
import { createHash, randomUUID } from "node:crypto";
import { getBlobStateClient, productionRequiresDurableState, STATE_BLOB_ACCESS } from "@/lib/server/blob-state";
import { getKv } from "@/lib/server/kv";

type Bucket = {
  count: number;
  resetAt: number;
};

const buckets = new Map<string, Bucket>();
const IP_RE = /^[a-z0-9:.%-]{1,64}$/i;

function cleanIp(value: string | null): string | null {
  const ip = value?.trim() ?? "";
  return IP_RE.test(ip) ? ip : null;
}

export function clientIp(headers: Headers): string {
  for (const name of ["x-vercel-forwarded-for", "x-real-ip", "x-forwarded-for"]) {
    const value = headers.get(name);
    if (!value) continue;
    for (const part of value.split(",")) {
      const ip = cleanIp(part);
      if (ip) return ip;
    }
  }
  return "unknown";
}

function blobBucketPath(key: string): string {
  const digest = createHash("sha256").update(key).digest("hex");
  return `paywall/rate-limit/${digest}/`;
}

async function blobRateLimit(
  key: string,
  limit: number,
  windowMs: number,
): Promise<{ ok: true } | { ok: false; retryAfterSeconds: number }> {
  const blob = getBlobStateClient();
  if (!blob) {
    if (productionRequiresDurableState()) {
      return { ok: false, retryAfterSeconds: Math.max(1, Math.ceil(windowMs / 1000)) };
    }
    throw new Error("blobRateLimit called without a Blob state client");
  }

  const now = Date.now();
  const prefix = blobBucketPath(key);
  await blob.put(`${prefix}${now}-${randomUUID()}.json`, "1", {
    access: STATE_BLOB_ACCESS,
    allowOverwrite: false,
    cacheControlMaxAge: 60,
    contentType: "application/json",
  });

  const cutoff = now - windowMs;
  let cursor: string | undefined;
  let count = 0;
  let oldestInWindow = now;
  do {
    const page = await blob.list({ prefix, cursor, limit: 1000 });
    for (const item of page.blobs) {
      const uploadedAt = item.uploadedAt.getTime();
      if (uploadedAt >= cutoff) {
        count += 1;
        oldestInWindow = Math.min(oldestInWindow, uploadedAt);
      }
    }
    cursor = page.cursor;
  } while (cursor && count <= limit);

  if (count <= limit) return { ok: true };
  return {
    ok: false,
    retryAfterSeconds: Math.max(1, Math.ceil((oldestInWindow + windowMs - now) / 1000)),
  }
}

export async function rateLimit(
  key: string,
  limit: number,
  windowMs: number,
): Promise<{ ok: true } | { ok: false; retryAfterSeconds: number }> {
  const kv = getKv();
  if (kv) {
    const ttlSeconds = Math.max(1, Math.ceil(windowMs / 1000));
    const kvKey = `rl:${key}`;
    const count = await kv.incr(kvKey);
    if (count === 1) {
      // First hit in the window: arm the TTL so the bucket resets.
      await kv.expire(kvKey, ttlSeconds);
    }
    if (count <= limit) return { ok: true };
    const remainingTtl = await kv.ttl(kvKey);
    const retryAfterSeconds = remainingTtl > 0 ? remainingTtl : ttlSeconds;
    return { ok: false, retryAfterSeconds };
  }

  if (getBlobStateClient() || productionRequiresDurableState()) {
    try {
      return await blobRateLimit(key, limit, windowMs);
    } catch (err) {
      console.error("rate limit durable state failed", err);
      return { ok: false, retryAfterSeconds: Math.max(1, Math.ceil(windowMs / 1000)) };
    }
  }

  const now = Date.now();
  const current = buckets.get(key);
  if (!current || current.resetAt <= now) {
    buckets.set(key, { count: 1, resetAt: now + windowMs });
    return { ok: true };
  }

  current.count += 1;
  if (current.count <= limit) return { ok: true };

  return {
    ok: false,
    retryAfterSeconds: Math.max(1, Math.ceil((current.resetAt - now) / 1000)),
  };
}
