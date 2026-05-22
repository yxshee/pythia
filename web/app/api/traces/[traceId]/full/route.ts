/**
 * Server-side paywall: returns the full trace payload only after
 * verifying the caller signed a domain-bound message AND that their
 * wallet has called UnlockMarket.unlock(traceId) on Arc.
 *
 * Threat model:
 *   - Hide `trace.full` from random scrapers and view-source. The
 *     public SSR pages (loadPicks → picks-preview.json) never include
 *     full reasoning, sources, sizing, or risk factors.
 *   - The wallet signature proves the caller controls `address`.
 *   - The on-chain isUnlocked read proves `address` paid 0.10 USDC.
 *   - Replay is bounded by the message's `Issued` timestamp window;
 *     a stricter nonce store is out of scope (anyone who can replay a
 *     signature could also just unlock for $0.10 themselves).
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

export const runtime = "nodejs";

const MAX_ISSUED_AGE_MS = 5 * 60 * 1000; // 5 minutes

type Body = {
  address?: string;
  signature?: string;
  message?: string;
};

function bad(reason: string, status = 400): NextResponse {
  return NextResponse.json({ error: reason }, { status });
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

function messageMatchesContext(
  message: string,
  traceId: number,
  address: string,
): boolean {
  const traceLine = `Trace ID: ${traceId}`;
  const addressLine = `Address: ${address.toLowerCase()}`;
  const lower = message.toLowerCase();
  return (
    lower.includes(traceLine.toLowerCase()) &&
    lower.includes(addressLine)
  );
}

export async function POST(
  req: Request,
  ctx: { params: Promise<{ traceId: string }> },
): Promise<NextResponse> {
  const rpcUrl = process.env.ARC_RPC_URL;
  if (!rpcUrl) {
    // Misconfigured deploy — fail closed.
    return bad("server-not-configured", 503);
  }

  const { traceId: traceIdParam } = await ctx.params;
  const traceId = Number(traceIdParam);
  if (!Number.isFinite(traceId) || traceId < 0) {
    return bad("invalid-trace-id");
  }

  let body: Body;
  try {
    body = (await req.json()) as Body;
  } catch {
    return bad("invalid-json");
  }

  const { address, signature, message } = body;
  if (!address || !signature || !message) {
    return bad("missing-fields");
  }
  if (!isAddress(address)) {
    return bad("invalid-address");
  }
  if (!signature.startsWith("0x")) {
    return bad("invalid-signature");
  }

  // 1. Message must be bound to (traceId, address). Prevents reusing a
  //    signature meant for one trace to unlock another.
  if (!messageMatchesContext(message, traceId, address)) {
    return bad("message-context-mismatch", 401);
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
  const full = await loadPickFull(traceId);
  if (!full) {
    return bad("trace-not-found", 404);
  }

  return NextResponse.json(full, {
    headers: {
      // Don't let anyone (CDN, browser) cache the gated payload.
      "Cache-Control": "private, no-store, max-age=0",
    },
  });
}
