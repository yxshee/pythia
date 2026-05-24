import "server-only";
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
import { createDecipheriv, createHash } from "node:crypto";
import path from "node:path";
import { utf8ByteLength } from "@/lib/server/request-security";
import type { Trace } from "@/lib/traces";

const TTL_MS = 30_000;
const FETCH_TIMEOUT_MS = 8_000;
const MAX_PRIVATE_TRACE_BYTES = 1_000_000;
const MAX_ENCRYPTED_PRIVATE_TRACE_BYTES = 2_000_000;
const MIN_PRIVATE_TRACES_ENCRYPTION_KEY_BYTES = 32;
const PRIVATE_TRACE_AAD = "pythia-private-traces-v1";

let cached: { at: number; traces: Trace[] } | null = null;

function localSnapshotPath(): string {
  return path.resolve(process.cwd(), "data", "picks-full.private.json");
}

function parseTraceArrayValue(parsed: unknown): Trace[] {
  if (!Array.isArray(parsed) || !parsed.every((entry) => entry && typeof entry === "object")) {
    throw new Error("private trace payload must be an array of trace objects");
  }
  return parsed as Trace[];
}

function parseTraceArray(body: string): Trace[] {
  if (utf8ByteLength(body) > MAX_PRIVATE_TRACE_BYTES) {
    throw new Error(`private trace payload exceeds ${MAX_PRIVATE_TRACE_BYTES} bytes`);
  }
  const parsed = JSON.parse(body) as unknown;
  return parseTraceArrayValue(parsed);
}

function decodeBase64Url(value: unknown, label: string): Buffer {
  if (typeof value !== "string" || !value) {
    throw new Error(`encrypted private trace payload is missing ${label}`);
  }
  return Buffer.from(value, "base64url");
}

function privateTraceEncryptionKey(): Buffer {
  const secret = process.env.PRIVATE_TRACES_ENCRYPTION_KEY?.trim();
  if (!secret) {
    throw new Error("PRIVATE_TRACES_ENCRYPTION_KEY is required for encrypted private traces");
  }
  if (Buffer.byteLength(secret, "utf8") < MIN_PRIVATE_TRACES_ENCRYPTION_KEY_BYTES) {
    throw new Error(
      `PRIVATE_TRACES_ENCRYPTION_KEY must be at least ${MIN_PRIVATE_TRACES_ENCRYPTION_KEY_BYTES} bytes`,
    );
  }
  return createHash("sha256").update(secret, "utf8").digest();
}

function decryptPrivateTraceBundle(payload: Record<string, unknown>): string {
  if (
    payload.pythia_private_traces_encrypted !== 1 ||
    payload.alg !== "AES-256-GCM" ||
    payload.kdf !== "sha256"
  ) {
    throw new Error("unsupported encrypted private trace payload");
  }
  if (payload.aad !== PRIVATE_TRACE_AAD) {
    throw new Error("encrypted private trace payload has unexpected aad");
  }
  const nonce = decodeBase64Url(payload.nonce, "nonce");
  const tag = decodeBase64Url(payload.tag, "tag");
  const ciphertext = decodeBase64Url(payload.ciphertext, "ciphertext");
  const decipher = createDecipheriv("aes-256-gcm", privateTraceEncryptionKey(), nonce);
  decipher.setAAD(Buffer.from(PRIVATE_TRACE_AAD, "utf8"));
  decipher.setAuthTag(tag);
  return Buffer.concat([decipher.update(ciphertext), decipher.final()]).toString("utf8");
}

function parsePrivateTracePayload(body: string, options: { source: "blob" | "local" }): Trace[] {
  if (utf8ByteLength(body) > MAX_ENCRYPTED_PRIVATE_TRACE_BYTES) {
    throw new Error(`private trace blob exceeds ${MAX_ENCRYPTED_PRIVATE_TRACE_BYTES} bytes`);
  }
  const parsed = JSON.parse(body) as unknown;
  if (Array.isArray(parsed)) {
    if (options.source === "blob" && process.env.VERCEL_ENV === "production") {
      throw new Error("production private trace Blob must be encrypted");
    }
    return parseTraceArrayValue(parsed);
  }
  if (parsed && typeof parsed === "object" && "pythia_private_traces_encrypted" in parsed) {
    return parseTraceArray(decryptPrivateTraceBundle(parsed as Record<string, unknown>));
  }
  throw new Error("private trace payload must be an array or encrypted bundle");
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
    return parsePrivateTracePayload(await res.text(), { source: "blob" });
  } finally {
    clearTimeout(t);
  }
}

async function loadFromLocal(): Promise<Trace[]> {
  const file = localSnapshotPath();
  const raw = await readFile(file, "utf-8");
  return parseTraceArray(raw);
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
