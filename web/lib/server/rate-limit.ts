import "server-only";
import { createHash } from "node:crypto";
import {
  blobStreamToText,
  getBlobStateClient,
  isBlobWriteConflict,
  productionRequiresDurableState,
  STATE_BLOB_ACCESS,
} from "@/lib/server/blob-state";
import { getKv } from "@/lib/server/kv";

type Bucket = {
  count: number;
  resetAt: number;
};

const buckets = new Map<string, Bucket>();
const IP_RE = /^[a-z0-9:.%-]{1,64}$/i;
const MAX_BUCKET_BYTES = 1024;
const MAX_BLOB_ATTEMPTS = 4;

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
  return `paywall/rate-limit/${digest}.json`;
}

function parseBucket(raw: string): Bucket | null {
  try {
    const parsed = JSON.parse(raw) as Partial<Bucket>;
    if (
      typeof parsed.count === "number" &&
      Number.isFinite(parsed.count) &&
      typeof parsed.resetAt === "number" &&
      Number.isFinite(parsed.resetAt)
    ) {
      return parsed as Bucket;
    }
  } catch {
    // Malformed durable counter: reset the bucket on the next write attempt.
  }
  return null;
}

function retryAfter(resetAt: number, windowMs: number): number {
  const remaining = Math.ceil((resetAt - Date.now()) / 1000);
  return remaining > 0 ? remaining : Math.max(1, Math.ceil(windowMs / 1000));
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

  const path = blobBucketPath(key);
  for (let attempt = 0; attempt < MAX_BLOB_ATTEMPTS; attempt += 1) {
    const now = Date.now();
    const existing = await blob.get(path, { access: STATE_BLOB_ACCESS, useCache: false });
    if (!existing || existing.statusCode !== 200) {
      const next = { count: 1, resetAt: now + windowMs };
      try {
        await blob.put(path, JSON.stringify(next), {
          access: STATE_BLOB_ACCESS,
          allowOverwrite: false,
          cacheControlMaxAge: 60,
          contentType: "application/json",
        });
        return { ok: true };
      } catch (err) {
        if (isBlobWriteConflict(err)) continue;
        console.error("rate limit durable create failed", err);
        return { ok: false, retryAfterSeconds: Math.max(1, Math.ceil(windowMs / 1000)) };
      }
    }

    const current =
      parseBucket(await blobStreamToText(existing.stream, MAX_BUCKET_BYTES)) ?? {
        count: 0,
        resetAt: now,
      };
    const reset = current.resetAt <= now;
    const next = {
      count: reset ? 1 : current.count + 1,
      resetAt: reset ? now + windowMs : current.resetAt,
    };
    try {
      await blob.put(path, JSON.stringify(next), {
        access: STATE_BLOB_ACCESS,
        allowOverwrite: true,
        cacheControlMaxAge: 60,
        contentType: "application/json",
        ifMatch: existing.blob.etag,
      });
      if (next.count <= limit) return { ok: true };
      return { ok: false, retryAfterSeconds: retryAfter(next.resetAt, windowMs) };
    } catch (err) {
      if (isBlobWriteConflict(err)) continue;
      console.error("rate limit durable update failed", err);
      return { ok: false, retryAfterSeconds: Math.max(1, Math.ceil(windowMs / 1000)) };
    }
  }

  return { ok: false, retryAfterSeconds: 1 };
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
