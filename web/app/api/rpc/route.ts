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
import { UNLOCK_MARKET, USDC } from "@/lib/contracts";
import { clientIp, rateLimit } from "@/lib/server/rate-limit";
import { trustedRequestHost, utf8ByteLength } from "@/lib/server/request-security";

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
  "eth_getTransactionByHash",
  "eth_getTransactionReceipt",
  "net_version",
]);

const MAX_BODY_BYTES = 25_000;
const MAX_RPC_RESPONSE_BYTES = 100_000;
const MAX_BATCH_CALLS = 10;
const UNLOCK_MARKET_READ_SELECTORS = new Set([
  "0x8d5555f2", // priceFor(uint256)
  "0x413a3842", // isUnlocked(uint256,address)
]);
const USDC_READ_SELECTORS = new Set([
  "0x70a08231", // balanceOf(address)
  "0xdd62ed3e", // allowance(address,address)
]);

function isAllowedEthCall(call: unknown): boolean {
  const params =
    call && typeof call === "object"
      ? (call as { params?: unknown }).params
      : undefined;
  if (!Array.isArray(params) || !params[0] || typeof params[0] !== "object") {
    return false;
  }
  const request = params[0] as { to?: unknown; data?: unknown; input?: unknown };
  const to = typeof request.to === "string" ? request.to.toLowerCase() : "";
  const data =
    typeof request.data === "string"
      ? request.data.toLowerCase()
      : typeof request.input === "string"
        ? request.input.toLowerCase()
        : "";
  if (!/^0x[0-9a-f]*$/.test(data) || data.length < 10) return false;
  const selector = data.slice(0, 10);

  if (to === UNLOCK_MARKET.toLowerCase()) {
    return UNLOCK_MARKET_READ_SELECTORS.has(selector);
  }
  if (to === USDC.toLowerCase()) {
    return USDC_READ_SELECTORS.has(selector);
  }
  return false;
}

export async function POST(req: NextRequest) {
  if (!trustedRequestHost(req)) {
    return NextResponse.json({ error: "host-not-allowed" }, { status: 400 });
  }

  const limit = await rateLimit(`rpc:${clientIp(req.headers)}`, 120, 60_000);
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
  if (utf8ByteLength(body) > MAX_BODY_BYTES) {
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
    if (method === "eth_call" && !isAllowedEthCall(call)) {
      return NextResponse.json({ error: "eth-call-not-allowed" }, { status: 403 });
    }
  }

  // Bound how long we wait on the Canteen-issued RPC. The 10s budget is
  // larger than any allowed read under normal load,
  // and small enough that a hung upstream cannot tie up our Vercel function
  // budget. We return 504 on timeout so the caller can distinguish "upstream
  // is slow" from "upstream returned an error" (502).
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 10_000);
  try {
    const resp = await fetch(upstream, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body,
      signal: controller.signal,
    });
    const respBody = await resp.text();
    if (utf8ByteLength(respBody) > MAX_RPC_RESPONSE_BYTES) {
      return NextResponse.json({ error: "upstream-response-too-large" }, { status: 502 });
    }
    return new NextResponse(respBody, {
      status: resp.status,
      headers: { "content-type": "application/json" },
    });
  } catch (err) {
    if (err instanceof Error && err.name === "AbortError") {
      return NextResponse.json({ error: "upstream-timeout" }, { status: 504 });
    }
    return NextResponse.json(
      {
        error: "upstream-failed",
      },
      { status: 502 },
    );
  } finally {
    clearTimeout(timeout);
  }
}
