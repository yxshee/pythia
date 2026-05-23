/**
 * Server-side paywall: returns the full trace payload only after
 * verifying the caller signed a host/chain/contract-bound message AND that their
 * wallet has called UnlockMarket.unlock(traceId) on Arc.
 *
 * Threat model:
 *   - Hide `trace.full` from random scrapers and view-source. The
 *     public SSR pages (loadPicks → picks-preview.json) never include
 *     full reasoning, sources, sizing, or risk factors.
 *   - The wallet signature proves the caller controls `address`.
 *   - The on-chain isUnlocked read proves `address` paid 0.10 USDC.
 *   - Replay is blocked by a short-lived server-issued nonce consumed
 *     after a successful full-payload response.
 *
 * What we explicitly do NOT promise:
 *   - We do not prevent an already-paid user from sharing their
 *     unlocked content. The paywall is "buy or read someone else's".
 *
 * ARC_RPC_URL is server-only (NOT NEXT_PUBLIC_*). It contains a
 * Canteen-issued token and must never reach the client bundle.
 */
import { NextResponse } from "next/server";
import { createPublicClient, http, isAddress, type Hex } from "viem";
import { arc } from "@/lib/arc-chain";
import { UNLOCK_MARKET, unlockMarketAbi } from "@/lib/contracts";
import { loadPickFull } from "@/lib/traces";
import { clientIp, rateLimit } from "@/lib/server/rate-limit";
import {
  consumeUnlockNonce,
  issueUnlockNonce,
  validateUnlockNonce,
} from "@/lib/server/paywall-nonce";

export const runtime = "nodejs";

const MAX_ISSUED_AGE_MS = 5 * 60 * 1000; // 5 minutes
const MAX_BODY_BYTES = 4 * 1024; // 4 KB hard cap on the unlock-POST body.

type Body = {
  address?: string;
  nonce?: string;
  signature?: string;
  message?: string;
};

function bad(reason: string, status = 400): NextResponse {
  return NextResponse.json({ error: reason }, { status });
}

function rateLimited(retryAfterSeconds: number): NextResponse {
  return NextResponse.json(
    { error: "rate-limited" },
    { status: 429, headers: { "Retry-After": String(retryAfterSeconds) } },
  );
}

function getRequestHost(req: Request): string {
  return (
    req.headers.get("x-forwarded-host") ??
    req.headers.get("host") ??
    ""
  ).toLowerCase();
}

function parseIssuedTimestamp(message: string): number | null {
  // Message shape (see web/components/unlock-button.tsx):
  //   agoraalpha.vercel.app — unlock trace
  //   Trace ID: <id>
  //   Address: 0x...
  //   Issued: <ISO timestamp>
  const m = message.match(/^Issued:\s*(\S+)$/m);
  if (!m) return null;
  const ms = Date.parse(m[1]);
  return Number.isFinite(ms) ? ms : null;
}

function messageMatchesContext(message: string, traceId: number, address: string, host: string): boolean {
  // We lowercase the haystack so that EIP-55 mixed-case addresses in
  // the message body still match. Needles must therefore also be
  // lowercase literals — historically `Address:` (capital A) was used
  // here and silently never matched the lowercased haystack, so every
  // valid signature 401'd with `message-context-mismatch`.
  const traceLine = `trace id: ${traceId}`;
  const addressLine = `address: ${address.toLowerCase()}`;
  const hostLine = host.toLowerCase();
  const chainLine = `chain id: ${arc.id}`;
  const contractLine = `unlockmarket: ${UNLOCK_MARKET.toLowerCase()}`;
  const nonceLine = "nonce:";
  const expiresLine = "expires:";
  const lower = message.toLowerCase();
  return (
    lower.includes(hostLine) &&
    lower.includes(traceLine) &&
    lower.includes(addressLine) &&
    lower.includes(chainLine) &&
    lower.includes(contractLine) &&
    lower.includes(nonceLine) &&
    lower.includes(expiresLine)
  );
}

export async function GET(
  req: Request,
  ctx: { params: Promise<{ traceId: string }> },
): Promise<NextResponse> {
  const limit = await rateLimit(`nonce:${clientIp(req.headers)}`, 20, 60_000);
  if (!limit.ok) return rateLimited(limit.retryAfterSeconds);

  const { traceId: traceIdParam } = await ctx.params;
  const traceId = Number(traceIdParam);
  if (!Number.isFinite(traceId) || traceId <= 0) {
    return bad("invalid-trace-id");
  }

  const url = new URL(req.url);
  const address = url.searchParams.get("address") ?? "";
  if (!isAddress(address)) {
    return bad("invalid-address");
  }

  const host = getRequestHost(req);
  if (!host) return bad("missing-host", 400);

  return NextResponse.json(await issueUnlockNonce({ host, traceId, address }), {
    headers: { "Cache-Control": "private, no-store, max-age=0" },
  });
}

export async function POST(
  req: Request,
  ctx: { params: Promise<{ traceId: string }> },
): Promise<NextResponse> {
  const limit = await rateLimit(`full:${clientIp(req.headers)}`, 30, 60_000);
  if (!limit.ok) return rateLimited(limit.retryAfterSeconds);

  const rpcUrl = process.env.ARC_RPC_URL;
  if (!rpcUrl) {
    // Misconfigured deploy — fail closed.
    return bad("server-not-configured", 503);
  }

  const { traceId: traceIdParam } = await ctx.params;
  const traceId = Number(traceIdParam);
  // trace_id counter starts at 1; reject 0 explicitly so that
  // `priceFor(0)` (which silently returns defaultPrice) cannot be
  // exploited to look up a phantom unlock against trace #0.
  if (!Number.isFinite(traceId) || traceId <= 0) {
    return bad("invalid-trace-id");
  }

  let body: Body;
  try {
    const raw = await req.text();
    if (raw.length > MAX_BODY_BYTES) {
      return bad("payload-too-large", 413);
    }
    body = JSON.parse(raw) as Body;
  } catch {
    return bad("invalid-json");
  }

  const { address, nonce, signature, message } = body;
  if (!address || !nonce || !signature || !message) {
    return bad("missing-fields");
  }
  if (!isAddress(address)) {
    return bad("invalid-address");
  }
  if (!signature.startsWith("0x")) {
    return bad("invalid-signature");
  }

  // 1. Message must be bound to (host, traceId, address, chain, contract).
  //    Prevents reusing a signature meant for one trace/deploy to unlock another.
  const requestHost = getRequestHost(req);
  if (!requestHost || !messageMatchesContext(message, traceId, address, requestHost)) {
    return bad("message-context-mismatch", 401);
  }

  const nonceValid = await validateUnlockNonce({
    nonce,
    host: requestHost,
    traceId,
    address,
    message,
  });
  if (!nonceValid.ok) {
    return bad(nonceValid.reason, 401);
  }

  // 2. Message must be fresh enough. Bounds replay window.
  const issuedAt = parseIssuedTimestamp(message);
  if (issuedAt === null) {
    return bad("missing-issued-timestamp", 401);
  }
  const ageMs = Date.now() - issuedAt;
  if (ageMs < -60_000 || ageMs > MAX_ISSUED_AGE_MS) {
    return bad("stale-signature", 401);
  }

  // 3. Verify the signature via viem. publicClient.verifyMessage handles
  //    both EOA ECDSA recovery and EIP-1271 contract-wallet checks.
  const publicClient = createPublicClient({
    chain: arc,
    transport: http(rpcUrl),
  });

  let signatureValid: boolean;
  try {
    signatureValid = await publicClient.verifyMessage({
      address: address as `0x${string}`,
      message,
      signature: signature as Hex,
    });
  } catch {
    return bad("signature-verify-failed", 401);
  }
  if (!signatureValid) {
    return bad("bad-signature", 401);
  }

  // 4. On-chain payment check: UnlockMarket.isUnlocked(traceId, buyer).
  let isUnlocked: boolean;
  try {
    isUnlocked = (await publicClient.readContract({
      address: UNLOCK_MARKET,
      abi: unlockMarketAbi,
      functionName: "isUnlocked",
      args: [BigInt(traceId), address as `0x${string}`],
    })) as boolean;
  } catch {
    return bad("onchain-read-failed", 502);
  }
  if (!isUnlocked) {
    return bad("not-unlocked", 402);
  }

  // 5. Authorized. Load the full payload from the server-only bundle.
  //    `loadPickFull` returns the OUTER `Trace` wrapper (with .preview /
  //    .full / .analyst / ...); the client only needs the inner
  //    `TraceFull` and casts the body as `TraceFull`. Returning the
  //    wrapper here made the client crash with
  //    `Cannot read properties of undefined (reading 'toFixed')` because
  //    fields like expected_value_pct sit on .full, not the wrapper.
  //    We also guard `!trace.full` so a malformed snapshot 404s here
  //    instead of leaking an empty body that crashes downstream.
  const trace = await loadPickFull(traceId);
  if (!trace || !trace.full) {
    return bad("trace-not-found", 404);
  }

  const nonceConsumed = await consumeUnlockNonce({
    nonce,
    host: requestHost,
    traceId,
    address,
    message,
  });
  if (!nonceConsumed.ok) {
    return bad(nonceConsumed.reason, 401);
  }

  return NextResponse.json(trace.full, {
    headers: {
      // Don't let anyone (CDN, browser) cache the gated payload.
      "Cache-Control": "private, no-store, max-age=0",
    },
  });
}
