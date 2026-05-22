import { randomUUID } from "node:crypto";
import { arc } from "@/lib/arc-chain";
import { UNLOCK_MARKET } from "@/lib/contracts";

const NONCE_TTL_MS = 5 * 60 * 1000;

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

export function issueUnlockNonce(input: {
  host: string;
  traceId: number;
  address: string;
}): { nonce: string; issuedAt: string; expiresAt: string; message: string } {
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
  active.set(nonce, record);
  return { nonce, issuedAt, expiresAt, message: record.message };
}

export function validateUnlockNonce(input: {
  nonce: string;
  host: string;
  traceId: number;
  address: string;
  message: string;
}): { ok: true } | { ok: false; reason: string } {
  const now = Date.now();
  cleanup(now);

  if (used.has(input.nonce)) {
    return { ok: false, reason: "nonce-used" };
  }

  const record = active.get(input.nonce);
  if (!record) {
    return { ok: false, reason: "nonce-not-found" };
  }
  if (record.expiresAt <= now) {
    active.delete(input.nonce);
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

export function consumeUnlockNonce(input: {
  nonce: string;
  host: string;
  traceId: number;
  address: string;
  message: string;
}): { ok: true } | { ok: false; reason: string } {
  const valid = validateUnlockNonce(input);
  if (!valid.ok) return valid;

  const now = Date.now();
  active.delete(input.nonce);
  used.set(input.nonce, now + NONCE_TTL_MS);
  return { ok: true };
}
