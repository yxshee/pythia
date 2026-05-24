import "server-only";
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
