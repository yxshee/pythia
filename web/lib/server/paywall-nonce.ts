import { randomUUID } from "node:crypto";
import { arc } from "@/lib/arc-chain";
import { UNLOCK_MARKET } from "@/lib/contracts";
import { requireKvInProduction } from "@/lib/server/kv";

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

  const kv = requireKvInProduction();
  if (kv) {
    await kv.set(activeKey(nonce), record, { ex: NONCE_TTL_SECONDS });
  } else {
    active.set(nonce, record);
  }
  return { nonce, issuedAt, expiresAt, message: record.message };
}

async function loadActive(nonce: string): Promise<NonceRecord | null> {
  const kv = requireKvInProduction();
  if (kv) {
    return (await kv.get<NonceRecord>(activeKey(nonce))) ?? null;
  }
  return active.get(nonce) ?? null;
}

async function isUsed(nonce: string): Promise<boolean> {
  const kv = requireKvInProduction();
  if (kv) {
    return (await kv.get(usedKey(nonce))) !== null;
  }
  return used.has(nonce);
}

async function markUsed(nonce: string): Promise<void> {
  const kv = requireKvInProduction();
  if (kv) {
    await kv.set(usedKey(nonce), 1, { ex: NONCE_TTL_SECONDS });
    await kv.del(activeKey(nonce));
  } else {
    active.delete(nonce);
    used.set(nonce, Date.now() + NONCE_TTL_MS);
  }
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
    const kv = requireKvInProduction();
    if (kv) {
      await kv.del(activeKey(input.nonce));
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
  await markUsed(input.nonce);
  return { ok: true };
}
