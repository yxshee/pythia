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
 * Notes:
 * - No auth. Arc reads are public information; the proxy adds no risk
 *   beyond what any public Arc RPC provider would already expose.
 * - Writes still go through the user's wallet, not this proxy.
 * - 503 if `ARC_RPC_URL` is missing (mirrors `/api/traces/[id]/full`).
 * - 502 if the upstream fetch errors (network, timeout).
 */
import { NextRequest, NextResponse } from "next/server";

export const runtime = "nodejs";

export async function POST(req: NextRequest) {
  const upstream = process.env.ARC_RPC_URL;
  if (!upstream) {
    return NextResponse.json({ error: "server-not-configured" }, { status: 503 });
  }
  const body = await req.text();
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
