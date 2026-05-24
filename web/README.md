# web — Agora Alpha frontend

The Next.js 16 app that renders the public picks feed, the per-trace pick page,
and the paid-unlock paywall against the `UnlockMarket` contract on Arc testnet.

- Live: https://agoraalpha.vercel.app
- Root README: [../README.md](../README.md)
- Submission status: [../STATUS.md](../STATUS.md)
- Reproducible verification: [../VERIFY.md](../VERIFY.md)
- Working-with-this-codebase rules: [./AGENTS.md](./AGENTS.md) (read first)

## Stack

- Next.js 16.2.6 (App Router, Turbopack, file-based metadata)
- React 19, TypeScript 5, Tailwind 4
- viem 2 + wagmi 2 for wallet + chain reads
- `@vercel/blob` for the private full-trace payload plus nonce replay markers
- `@vercel/kv` for durable paywall nonce storage + rate limiting when configured

## Paywall flow

```
1. Visitor opens /pick/[traceId]
   → SSR renders preview + on-chain anchor only.
2. Visitor connects wallet → mints DevUSDC if needed → approves → calls
   UnlockMarket.unlock(traceId).
3. Client GETs /api/traces/[traceId]/full?address=… → server issues a
   nonce bound to (host, traceId, address, chainId, contract, expiresAt).
4. Wallet signs the EIP-191 message containing that nonce.
5. Client POSTs { address, nonce, signature, message } to the same route.
6. Server validates message context, freshness, nonce, signature
   (EOA + EIP-1271), and UnlockMarket.isUnlocked(traceId, address). On
   pass, returns trace.full and consumes the nonce. Replay returns
   `nonce-used`.
```

Server-only routes:
- `/api/traces/[traceId]/full` — paywall
- `/api/rpc` — read-only JSON-RPC proxy over the Canteen-issued upstream

## Env vars

See [./.env.local.example](./.env.local.example) for the full annotated list.
Two contracts you must respect:

- **Never prefix server-only vars with `NEXT_PUBLIC_`.** `ARC_RPC_URL`,
  `PRIVATE_TRACES_BLOB_URL`, `BLOB_READ_WRITE_TOKEN`, `KV_REST_API_URL`,
  and `KV_REST_API_TOKEN` are server-only. They appear only in Node.js
  runtime bundles, never in the browser.
- **The Blob URL itself is the secret.** `PRIVATE_TRACES_BLOB_URL` carries
  a random suffix that is the only access control on the paid payload.
  Treat it like a token: never log, never commit.
- **Durable nonce replay state is required in production.** The API prefers
  `KV_REST_API_URL` / `KV_REST_API_TOKEN` when present, otherwise it uses
  write-once Vercel Blob markers through `BLOB_READ_WRITE_TOKEN`. Rate limiting
  uses KV when configured and otherwise falls back to per-instance counters.

## Scripts

```bash
pnpm dev          # next dev
pnpm build        # next build (Turbopack)
pnpm start        # serve the production build
pnpm exec tsc --noEmit   # standalone typecheck
```

Use `pnpm install --frozen-lockfile` in CI (see [.github/workflows/ci.yml](../.github/workflows/ci.yml)).

## Operator pre-deploy gate

Before promoting a build that depends on `PRIVATE_TRACES_BLOB_URL`, run the
validator's `--check-blob` mode to confirm the URL actually serves the full
trace bundle whose IDs exactly match `web/data/picks-preview.json` and whose
entries pass full-payload quality checks:

```bash
cd ../agent
PRIVATE_TRACES_BLOB_URL=https://…  uv run python -m pythia.scripts.validate_submission \
  --mode private-deploy --check-blob
```

Exit code 0 means the URL is reachable, served as JSON, parsed to a
non-empty trace array, ID-matched to the public preview file, and passes
source/risk/HOLD-copy-trade checks. Any other case prints a `FAIL:` line
with the reason while redacting the URL itself.

## Wallet smoke (operator)

`scripts/cli-unlock.mjs` is a viem-based one-command flow that mirrors the
in-browser `UnlockButton`: mint DevUSDC → approve → unlock → GET nonce →
sign EIP-191 → POST → replay (expect `nonce-used`). Use it to capture a
clean transcript for VERIFY.md §5 without screenshots.

```bash
cd ..
npm install                                # one-time install (repo-root deps)
PRIVATE_KEY=0xREPLACE_WITH_64_HEX ARC_RPC_URL=https://REPLACE_WITH_ARC_RPC_URL \
  node scripts/cli-unlock.mjs --base=https://agoraalpha.vercel.app --trace-id=24
```

Pre-flight `--dry-run` flag stops after reading the on-chain unlock price
— useful for confirming RPC + private-key wiring without spending gas.
The script logs the wallet address (public) but **never** the private key
or any signature secret.

## Notes for AI coding tools

This is Next.js 16. APIs, conventions, and file structure differ from
training-data Next.js. Read the relevant guide in `node_modules/next/dist/docs/`
before writing code. The rules in [./AGENTS.md](./AGENTS.md) take precedence
over generic Next.js patterns.
