# x402 and Session-Key Roadmap

This document captures the **planned** evolution of Pythia's paid-trace
delivery. The current shipped path is `UnlockMarket` + DevUSDC + nonce-bound
server-side verification. x402 and session keys are *not* claimed as shipped
in this submission.

## Current shipped path

```text
1. User opens /pick/:id.
2. Public preview loads (free, byte-replayable from web/data/picks-preview.json).
3. User connects wallet.
4. User mints DevUSDC if needed (open faucet on testnet only).
5. User approves UnlockMarket for the exact unlock price.
6. User calls UnlockMarket.unlock(traceId) on Arc.
7. Server issues a short-lived nonce bound to host + trace + address + chain.
8. User signs the EIP-191 nonce-bound message.
9. Server verifies the signature against the connected wallet.
10. Server verifies UnlockMarket.isUnlocked(traceId, user) on Arc.
11. Server decrypts the private trace from the AES-256-GCM blob.
12. Server returns the full trace.
```

The unlock has on-chain finality and the paywall fails closed on Arc read
errors. The flow is what reviewers should evaluate today.

## Planned x402 path

x402 is an HTTP-native payment standard: an unpaid request receives HTTP
402 with structured payment requirements; the client pays out-of-band and
retries with proof, then the server verifies and returns the resource.
See [x402.org](https://x402.org/) for the canonical challenge/retry
semantics.

```text
GET /api/x402/traces/:id

(no payment header)
HTTP/1.1 402 Payment Required
Content-Type: application/json
{
  "x402Version": "experimental",
  "asset": "DevUSDC",
  "network": "arc-testnet",
  "amount": "0.10",
  "traceId": 26,
  "description": "Unlock private Pythia reasoning trace",
  "note": "Experimental; judged paywall remains UnlockMarket."
}

(retry with valid payment proof)
HTTP/1.1 200 OK
{ ...full trace... }
```

What "real x402" needs before we claim it as shipped:

- HTTP 402 response with a complete payment-requirements payload.
- Client retry semantics matching the standard.
- Server-side verification of the payment proof (not just the format).
- A passing test that proves unpaid fails and paid succeeds end-to-end.

Until those are in place, the route ships as a docs-only roadmap so the
sponsor primitive is surfaced without an overclaim.

## Planned read-only session grant

Distinct from full session keys. The proposed grant scope:

```text
Trigger:  user unlocks a trace once via the shipped UnlockMarket path.
Sign:     "Allow this browser session to read already-unlocked traces
           for 15 minutes."
Server:   issues httpOnly session cookie scoped to (address, expires).
Allows:   GET /api/traces/:id/full for traces already unlocked on-chain.
Denies:   any approve / transfer / unlock / order / payment call.
Expires:  15 minutes; cannot be refreshed without a fresh wallet sign.
```

This is **not** delegated signing. It does not authorize spending and does
not let the server place trades. It exists to remove the "sign every page
load" UX friction while preserving on-chain auditability for unlock
decisions.

A true session-key implementation (delegated signing with spending caps)
is **not** in scope for this submission. The wording "session key" is
reserved for that future work to avoid implying capabilities that don't
exist today.

## Cross-references

- Shipped paywall code: [web/app/api/traces/[traceId]/full/route.ts](../web/app/api/traces/%5BtraceId%5D/full/route.ts)
- Shipped unlock contract: [contracts/src/UnlockMarket.sol](../contracts/src/UnlockMarket.sol)
- Status of sponsor-stack integrations: [STATUS.md](../STATUS.md)
