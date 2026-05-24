import "server-only";
import { createHash, createHmac, randomUUID, timingSafeEqual } from "node:crypto";
import { arc } from "@/lib/arc-chain";
import { UNLOCK_MARKET } from "@/lib/contracts";
import {
  getBlobStateClient,
  isBlobWriteConflict,
  productionRequiresDurableState,
  STATE_BLOB_ACCESS,
  StateStoreUnavailableError,
} from "@/lib/server/blob-state";
import { getKv } from "@/lib/server/kv";

const NONCE_TTL_MS = 5 * 60 * 1000;
const NONCE_TTL_SECONDS = NONCE_TTL_MS / 1000;

type NonceTokenPayload = {
  v: 1;
  jti: string;
  host: string;
  traceId: number;
  address: string;
  issuedAt: string;
  expiresAt: string;
};

const used = new Map<string, number>();

function cleanup(now = Date.now()): void {
  for (const [nonceHash, expiresAt] of used) {
    if (expiresAt <= now) used.delete(nonceHash);
  }
}

function nonceHash(nonce: string): string {
  return createHash("sha256").update(nonce).digest("hex");
}

function usedKey(nonce: string): string {
  return `nonce:used:${nonceHash(nonce)}`;
}

function blobUsedPath(nonce: string): string {
  return `paywall/nonces/used/${nonceHash(nonce)}.json`;
}

function nonceSecret(): string {
  const secret =
    process.env.PAYWALL_NONCE_SECRET ??
    process.env.KV_REST_API_TOKEN ??
    process.env.BLOB_READ_WRITE_TOKEN;
  if (secret) return secret;
  if (productionRequiresDurableState()) throw new StateStoreUnavailableError();
  return "local-dev-paywall-nonce-secret";
}

function encodePayload(payload: NonceTokenPayload): string {
  return Buffer.from(JSON.stringify(payload), "utf8").toString("base64url");
}

function signPayload(encodedPayload: string): string {
  return createHmac("sha256", nonceSecret()).update(encodedPayload).digest("base64url");
}

function verifySignature(encodedPayload: string, signature: string): boolean {
  const expected = Buffer.from(signPayload(encodedPayload), "utf8");
  const actual = Buffer.from(signature, "utf8");
  return expected.length === actual.length && timingSafeEqual(expected, actual);
}

function decodeNonce(nonce: string): NonceTokenPayload | null {
  const [encodedPayload, signature] = nonce.split(".");
  if (!encodedPayload || !signature || !verifySignature(encodedPayload, signature)) {
    return null;
  }
  try {
    const payload = JSON.parse(Buffer.from(encodedPayload, "base64url").toString("utf8")) as Partial<NonceTokenPayload>;
    if (
      payload.v === 1 &&
      typeof payload.jti === "string" &&
      typeof payload.host === "string" &&
      typeof payload.traceId === "number" &&
      typeof payload.address === "string" &&
      typeof payload.issuedAt === "string" &&
      typeof payload.expiresAt === "string"
    ) {
      return payload as NonceTokenPayload;
    }
  } catch {
    // Invalid token body.
  }
  return null;
}

function buildNonce(payload: NonceTokenPayload): string {
  const encodedPayload = encodePayload(payload);
  return `${encodedPayload}.${signPayload(encodedPayload)}`;
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
  const issuedAt = new Date(now).toISOString();
  const expiresAt = new Date(now + NONCE_TTL_MS).toISOString();
  const payload: NonceTokenPayload = {
    v: 1,
    jti: randomUUID(),
    host: input.host.toLowerCase(),
    traceId: input.traceId,
    address: input.address.toLowerCase(),
    issuedAt,
    expiresAt,
  };
  const nonce = buildNonce(payload);
  const message = buildUnlockMessage({
    host: payload.host,
    traceId: payload.traceId,
    address: payload.address,
    nonce,
    issuedAtIso: payload.issuedAt,
    expiresAtIso: payload.expiresAt,
  });
  return { nonce, issuedAt, expiresAt, message };
}

export async function validateUnlockNonce(input: {
  nonce: string;
  host: string;
  traceId: number;
  address: string;
  message: string;
}): Promise<{ ok: true } | { ok: false; reason: string }> {
  cleanup();
  const payload = decodeNonce(input.nonce);
  if (!payload) return { ok: false, reason: "nonce-not-found" };

  if (payload.host !== input.host.toLowerCase()) {
    return { ok: false, reason: "nonce-host-mismatch" };
  }
  if (payload.traceId !== input.traceId) {
    return { ok: false, reason: "nonce-trace-mismatch" };
  }
  if (payload.address !== input.address.toLowerCase()) {
    return { ok: false, reason: "nonce-address-mismatch" };
  }
  const expectedMessage = buildUnlockMessage({
    host: payload.host,
    traceId: payload.traceId,
    address: payload.address,
    nonce: input.nonce,
    issuedAtIso: payload.issuedAt,
    expiresAtIso: payload.expiresAt,
  });
  if (expectedMessage !== input.message) {
    return { ok: false, reason: "nonce-message-mismatch" };
  }
  const expiresAtMs = Date.parse(payload.expiresAt);
  if (!Number.isFinite(expiresAtMs) || expiresAtMs <= Date.now()) {
    return { ok: false, reason: "nonce-expired" };
  }

  return { ok: true };
}

async function markUsed(nonce: string): Promise<boolean> {
  const kv = getKv();
  if (kv) {
    const stored = await kv.set(usedKey(nonce), 1, {
      ex: NONCE_TTL_SECONDS,
      nx: true,
    });
    return stored === "OK";
  }

  const blob = getBlobStateClient();
  if (blob) {
    try {
      await blob.put(
        blobUsedPath(nonce),
        JSON.stringify({ nonceHash: nonceHash(nonce), usedAt: new Date().toISOString() }),
        putOptions(),
      );
      return true;
    } catch (err) {
      if (isBlobWriteConflict(err)) return false;
      throw err;
    }
  }

  if (productionRequiresDurableState()) {
    throw new StateStoreUnavailableError();
  }

  const hash = nonceHash(nonce);
  if (used.has(hash)) return false;
  used.set(hash, Date.now() + NONCE_TTL_MS);
  return true;
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
