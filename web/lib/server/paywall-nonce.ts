import "server-only";
import { randomUUID } from "node:crypto";
import { arc } from "@/lib/arc-chain";
import { UNLOCK_MARKET } from "@/lib/contracts";
import {
  blobStreamToText,
  getBlobStateClient,
  isBlobWriteConflict,
  productionRequiresDurableState,
  STATE_BLOB_ACCESS,
  StateStoreUnavailableError,
} from "@/lib/server/blob-state";
import { getKv } from "@/lib/server/kv";

const NONCE_TTL_MS = 5 * 60 * 1000;
const NONCE_TTL_SECONDS = NONCE_TTL_MS / 1000;

type NonceRecord = {
  nonce: string;
  host: string;
  traceId: number;
  address: string;
  issuedAt: number;
  expiresAt: number;
  message: string;
};

const active = new Map<string, NonceRecord>();
const used = new Map<string, number>();

function cleanup(now = Date.now()): void {
  for (const [nonce, record] of active) {
    if (record.expiresAt <= now) active.delete(nonce);
  }
  for (const [nonce, expiresAt] of used) {
    if (expiresAt <= now) used.delete(nonce);
  }
}

function activeKey(nonce: string): string {
  return `nonce:active:${nonce}`;
}

function usedKey(nonce: string): string {
  return `nonce:used:${nonce}`;
}

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const MAX_NONCE_RECORD_BYTES = 8 * 1024;

function blobActivePath(nonce: string): string {
  return `paywall/nonces/active/${nonce}.json`;
}

function blobUsedPath(nonce: string): string {
  return `paywall/nonces/used/${nonce}.json`;
}

function assertSafeNonce(nonce: string): boolean {
  return UUID_RE.test(nonce);
}

function parseNonceRecord(raw: string): NonceRecord | null {
  try {
    const parsed = JSON.parse(raw) as Partial<NonceRecord>;
    if (
      typeof parsed.nonce === "string" &&
      typeof parsed.host === "string" &&
      typeof parsed.traceId === "number" &&
      typeof parsed.address === "string" &&
      typeof parsed.issuedAt === "number" &&
      typeof parsed.expiresAt === "number" &&
      typeof parsed.message === "string"
    ) {
      return parsed as NonceRecord;
    }
  } catch {
    // Invalid durable-state payload: treat as missing and fail closed later.
  }
  return null;
}

function putOptions() {
  return {
    access: STATE_BLOB_ACCESS,
    allowOverwrite: false,
    cacheControlMaxAge: 60,
    contentType: "application/json",
  };
}

export function buildUnlockMessage(input: {
  host: string;
  traceId: number;
  address: string;
  nonce: string;
  issuedAtIso: string;
  expiresAtIso: string;
}): string {
  return (
    `${input.host} — unlock trace\n` +
    `Trace ID: ${input.traceId}\n` +
    `address: ${input.address.toLowerCase()}\n` +
    `Chain ID: ${arc.id}\n` +
    `UnlockMarket: ${UNLOCK_MARKET.toLowerCase()}\n` +
    `Nonce: ${input.nonce}\n` +
    `Issued: ${input.issuedAtIso}\n` +
    `Expires: ${input.expiresAtIso}`
  );
}

export async function issueUnlockNonce(input: {
  host: string;
  traceId: number;
  address: string;
}): Promise<{ nonce: string; issuedAt: string; expiresAt: string; message: string }> {
  cleanup();
  const now = Date.now();
  const nonce = randomUUID();
  const issuedAt = new Date(now).toISOString();
  const expiresAtMs = now + NONCE_TTL_MS;
  const expiresAt = new Date(expiresAtMs).toISOString();
  const record: NonceRecord = {
    nonce,
    host: input.host.toLowerCase(),
    traceId: input.traceId,
    address: input.address.toLowerCase(),
    issuedAt: now,
    expiresAt: expiresAtMs,
    message: buildUnlockMessage({
      host: input.host.toLowerCase(),
      traceId: input.traceId,
      address: input.address,
      nonce,
      issuedAtIso: issuedAt,
      expiresAtIso: expiresAt,
    }),
  };

  const kv = getKv();
  if (kv) {
    await kv.set(activeKey(nonce), record, { ex: NONCE_TTL_SECONDS });
  } else if (getBlobStateClient()) {
    await getBlobStateClient()!.put(blobActivePath(nonce), JSON.stringify(record), putOptions());
  } else if (productionRequiresDurableState()) {
    throw new StateStoreUnavailableError();
  } else {
    active.set(nonce, record);
  }
  return { nonce, issuedAt, expiresAt, message: record.message };
}

async function loadActive(nonce: string): Promise<NonceRecord | null> {
  if (!assertSafeNonce(nonce)) return null;

  const kv = getKv();
  if (kv) {
    return (await kv.get<NonceRecord>(activeKey(nonce))) ?? null;
  }
  const blob = getBlobStateClient();
  if (blob) {
    const result = await blob.get(blobActivePath(nonce), {
      access: STATE_BLOB_ACCESS,
      useCache: false,
    });
    if (!result || result.statusCode !== 200) return null;
    return parseNonceRecord(await blobStreamToText(result.stream, MAX_NONCE_RECORD_BYTES));
  }
  if (productionRequiresDurableState()) {
    throw new StateStoreUnavailableError();
  }
  return active.get(nonce) ?? null;
}

async function isUsed(nonce: string): Promise<boolean> {
  if (!assertSafeNonce(nonce)) return false;

  const kv = getKv();
  if (kv) {
    return (await kv.get(usedKey(nonce))) !== null;
  }
  const blob = getBlobStateClient();
  if (blob) {
    const result = await blob.get(blobUsedPath(nonce), {
      access: STATE_BLOB_ACCESS,
      useCache: false,
    });
    if (result?.stream) await result.stream.cancel().catch(() => undefined);
    return result !== null;
  }
  if (productionRequiresDurableState()) {
    throw new StateStoreUnavailableError();
  }
  return used.has(nonce);
}

async function markUsed(nonce: string): Promise<boolean> {
  if (!assertSafeNonce(nonce)) return false;

  const kv = getKv();
  if (kv) {
    const stored = await kv.set(usedKey(nonce), 1, {
      ex: NONCE_TTL_SECONDS,
      nx: true,
    });
    if (stored !== "OK") return false;
    await kv.del(activeKey(nonce));
    return true;
  }

  const blob = getBlobStateClient();
  if (blob) {
    try {
      await blob.put(
        blobUsedPath(nonce),
        JSON.stringify({ nonce, usedAt: new Date().toISOString() }),
        putOptions(),
      );
    } catch (err) {
      if (isBlobWriteConflict(err)) return false;
      throw err;
    }
    await blob.del(blobActivePath(nonce)).catch(() => undefined);
    return true;
  }

  if (productionRequiresDurableState()) {
    throw new StateStoreUnavailableError();
  }

  if (used.has(nonce)) return false;
  active.delete(nonce);
  used.set(nonce, Date.now() + NONCE_TTL_MS);
  return true;
}

export async function validateUnlockNonce(input: {
  nonce: string;
  host: string;
  traceId: number;
  address: string;
  message: string;
}): Promise<{ ok: true } | { ok: false; reason: string }> {
  const now = Date.now();
  cleanup(now);

  if (await isUsed(input.nonce)) {
    return { ok: false, reason: "nonce-used" };
  }

  const record = await loadActive(input.nonce);
  if (!record) {
    return { ok: false, reason: "nonce-not-found" };
  }
  if (record.expiresAt <= now) {
    const kv = getKv();
    if (kv) {
      await kv.del(activeKey(input.nonce));
    } else if (getBlobStateClient() && assertSafeNonce(input.nonce)) {
      await getBlobStateClient()!.del(blobActivePath(input.nonce)).catch(() => undefined);
    } else {
      active.delete(input.nonce);
    }
    return { ok: false, reason: "nonce-expired" };
  }
  if (record.host !== input.host.toLowerCase()) {
    return { ok: false, reason: "nonce-host-mismatch" };
  }
  if (record.traceId !== input.traceId) {
    return { ok: false, reason: "nonce-trace-mismatch" };
  }
  if (record.address !== input.address.toLowerCase()) {
    return { ok: false, reason: "nonce-address-mismatch" };
  }
  if (record.message !== input.message) {
    return { ok: false, reason: "nonce-message-mismatch" };
  }

  return { ok: true };
}

export async function consumeUnlockNonce(input: {
  nonce: string;
  host: string;
  traceId: number;
  address: string;
  message: string;
}): Promise<{ ok: true } | { ok: false; reason: string }> {
  const valid = await validateUnlockNonce(input);
  if (!valid.ok) return valid;
  if (!(await markUsed(input.nonce))) {
    return { ok: false, reason: "nonce-used" };
  }
  return { ok: true };
}
