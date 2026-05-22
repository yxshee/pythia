/**
 * Server-side JSON-RPC proxy for the Arc testnet.
 *
 * The wallet flow needs an RPC URL the client can dial — for viem's
 * `http()` transport (read calls before tx send) and for MetaMask's
 * `wallet_addEthereumChain` payload (the `rpcUrls` array must be
 * non-empty or the request is rejected). But our upstream URL is a
 * Canteen-issued token-bearing endpoint that must NOT ship to the
 * browser.
 *
 * This route is a thin pass-through. The client points at
 * `${NEXT_PUBLIC_SITE_URL}/api/rpc`; we forward the JSON-RPC body to
 * `ARC_RPC_URL` server-side and return the upstream response verbatim.
 *
 * Method allowlist
 * ----------------
 * The proxy is a public POST endpoint, so any browser could send any
 * JSON-RPC request through it — including `eth_sendRawTransaction`,
 * which would let an attacker shift the cost of broadcasting their own
 * unrelated transactions onto our Canteen-issued RPC quota.
 *
 * We enforce a read-only method allowlist before forwarding. Writes
 * still go through the user's wallet on their own RPC; this proxy
 * never needs to carry a `send*` method.
 *
 * Other notes:
 * - No auth. Arc reads are public information; the proxy adds no risk
 *   beyond what any public Arc RPC provider would already expose.
 * - 400 on unparseable body, 403 on disallowed method.
 * - 503 if `ARC_RPC_URL` is missing (mirrors `/api/traces/[id]/full`).
 * - 502 if the upstream fetch errors (network, timeout).
 */
import { NextRequest, NextResponse } from "next/server";
import { clientIp, rateLimit } from "@/lib/server/rate-limit";

export const runtime = "nodejs";

/**
 * Read-only methods needed by the wallet flow and the home / pick pages.
 * Add to this set only after confirming the method cannot mutate state
 * or initiate a transaction on the user's behalf.
 */
const ALLOWED_METHODS = new Set([
  "eth_chainId",
  "eth_blockNumber",
  "eth_call",
  "eth_getBalance",
  "eth_getCode",
  "eth_getLogs",
  "eth_getTransactionByHash",
  "eth_getTransactionReceipt",
  "net_version",
]);

const MAX_BODY_CHARS = 25_000;
const MAX_BATCH_CALLS = 10;

export async function POST(req: NextRequest) {
  const limit = rateLimit(`rpc:${clientIp(req.headers)}`, 120, 60_000);
  if (!limit.ok) {
    return NextResponse.json(
      { error: "rate-limited" },
      { status: 429, headers: { "Retry-After": String(limit.retryAfterSeconds) } },
    );
  }

  const upstream = process.env.ARC_RPC_URL;
  if (!upstream) {
    return NextResponse.json({ error: "server-not-configured" }, { status: 503 });
  }

  const body = await req.text();
  if (body.length > MAX_BODY_CHARS) {
    return NextResponse.json({ error: "body-too-large" }, { status: 413 });
  }

  // Parse + validate method(s) before forwarding. A JSON-RPC body is
  // either a single call object or an array of call objects (batch).
  let parsed: unknown;
  try {
    parsed = JSON.parse(body);
  } catch {
    return NextResponse.json({ error: "invalid-json" }, { status: 400 });
  }

  if (Array.isArray(parsed) && (parsed.length === 0 || parsed.length > MAX_BATCH_CALLS)) {
    return NextResponse.json(
      { error: "batch-size-not-allowed", max: MAX_BATCH_CALLS },
      { status: 400 },
    );
  }

  const calls = Array.isArray(parsed) ? parsed : [parsed];
  for (const call of calls) {
    const method =
      call && typeof call === "object"
        ? (call as { method?: unknown }).method
        : undefined;
    if (typeof method !== "string" || !ALLOWED_METHODS.has(method)) {
      return NextResponse.json(
        {
          error: "method-not-allowed",
          detail:
            "This proxy only forwards a read-only allowlist. Writes go through the wallet, not this endpoint.",
        },
        { status: 403 },
      );
    }
  }

  try {
    const resp = await fetch(upstream, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body,
    });
    const respBody = await resp.text();
    return new NextResponse(respBody, {
      status: resp.status,
      headers: { "content-type": "application/json" },
    });
  } catch (err) {
    return NextResponse.json(
      {
        error: "upstream-failed",
        detail: err instanceof Error ? err.message : String(err),
      },
      { status: 502 },
    );
  }
}
