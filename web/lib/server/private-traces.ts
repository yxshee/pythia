/**
 * Server-only loader for the paid full-trace bundle.
 *
 * Production path: read from Vercel Blob via `PRIVATE_TRACES_BLOB_URL`. The
 * URL points at an unguessable blob (random suffix) and the access gate is
 * the paywall route, not the URL itself.
 *
 * Local-dev path: read from `web/data/picks-full.private.json` when the
 * Blob URL is unset. This keeps `next dev` working without provisioning
 * Blob storage.
 *
 * Either way, the result is held behind the same paywall validation chain
 * in `/api/traces/[traceId]/full/route.ts`. This module is server-only and
 * must never be imported into a client component.
 */
import { readFile } from "node:fs/promises";
import { existsSync } from "node:fs";
import path from "node:path";
import type { Trace } from "@/lib/traces";

const TTL_MS = 30_000;
const FETCH_TIMEOUT_MS = 8_000;

let cached: { at: number; traces: Trace[] } | null = null;

function localSnapshotPath(): string {
  return path.resolve(process.cwd(), "data", "picks-full.private.json");
}

async function loadFromBlob(url: string): Promise<Trace[]> {
  const controller = new AbortController();
  const t = setTimeout(() => controller.abort(), FETCH_TIMEOUT_MS);
  try {
    const res = await fetch(url, {
      signal: controller.signal,
      cache: "no-store",
    });
    if (!res.ok) {
      throw new Error(`blob fetch ${res.status}`);
    }
    return (await res.json()) as Trace[];
  } finally {
    clearTimeout(t);
  }
}

async function loadFromLocal(): Promise<Trace[]> {
  const file = localSnapshotPath();
  const raw = await readFile(file, "utf-8");
  return JSON.parse(raw) as Trace[];
}

/**
 * Returns the full paid bundle, or `null` when neither source is available.
 * The caller (typically `loadPickFull`) is expected to handle `null` by
 * returning a 404 to the client — never by leaking a partial response.
 */
export async function loadPrivateTraces(): Promise<Trace[] | null> {
  if (cached && Date.now() - cached.at < TTL_MS) return cached.traces;

  const blobUrl = process.env.PRIVATE_TRACES_BLOB_URL;
  try {
    let traces: Trace[] | null = null;
    if (blobUrl) {
      traces = await loadFromBlob(blobUrl);
    } else if (existsSync(localSnapshotPath())) {
      traces = await loadFromLocal();
    }
    if (!traces) return null;
    cached = { at: Date.now(), traces };
    return traces;
  } catch (err) {
    // Fail closed: a Blob outage must not silently downgrade to "no payload"
    // for paid users. Logging here lets us see the cause in Vercel logs.
    console.error("private-traces load failed", err);
    return null;
  }
}

/** Test-only hook so unit tests can reset the in-memory cache. */
export function _resetPrivateTracesCacheForTests(): void {
  cached = null;
}
