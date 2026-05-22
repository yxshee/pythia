# Pythia — delivery status

> Honest, current-state status for the hackathon submission. Pairs with
> [`README.md`](README.md) which describes the architecture and intended
> behaviour. When the README and this file disagree about *what is shipping
> today*, this file wins.

Last updated: 2026-05-22.

## Works today

- **4 contracts deployed to Arc testnet** (chain ID `5042002`):
  `PythiaVault`, `TraceLog`, `UnlockMarket`, `DevUSDC`. Addresses in the
  README Deployments table.
- **39/39 forge tests green** across the four contracts (`via_ir = true`).
- **Agent loop wired end-to-end**: Scout → Analyst → PM → Publisher → Trace.
  Runs in `--mock` mode with bundled fixtures so the pipeline is
  reproducible offline.
- **LLM analyst code path** (`agent/pythia/analyst.py`): Claude
  Sonnet 4.6 via forced tool-use with a deterministic heuristic-v1
  fallback. The LLM is the primary path when `ANTHROPIC_API_KEY` is set
  in `.env`; the heuristic ships as a safety net for offline demos.
- **TraceLog on-chain anchoring**: `trace.py` calls `TraceLog.publish(...)`
  when `TRACE_LOG_ADDRESS` is set in `.env`. Trace receipts (tx hash,
  block, contract address) are written back into the trace JSON and
  surfaced as the "On-chain anchor" card on `/pick/[id]`.
- **Wallet flow on `/pick/[id]`**: injected-wallet connect (wagmi v2 +
  viem v2) → approve exact 0.10 USDC → `UnlockMarket.unlock(traceId)`
  on Arc. Inline `DevUSDC.mint()` faucet for first-time visitors. Real
  USDC moves to the treasury on each unlock.
- **Vercel deploy live** at <https://agoraalpha.vercel.app>. Home, pick
  feed, and pick-detail pages all serve.
- **builderCode threaded** into copy-trade URLs: `to_full()` emits
  `copy_trade_url` with `?builderCode=…` so the paid CTA carries the
  attribution string.
- **Preview / full data-model split**: `preview.py` projects every trace
  into a free `preview` payload and a paid `full` payload; the split is
  enforced at the source-of-truth level, not bolted on at render time.

## Partially works

- **Paywall is a visual UI gate, not a cryptographic fetch.** The
  full reasoning payload is rendered into the pick page's SSR HTML and
  hidden until `UnlockMarket.isUnlocked(traceId, wallet)` returns true
  for the visitor. View-source bypasses the UI gate. A SIWE-signed
  server-side fetch (`/api/traces/[id]/full`) is the v2 path tracked in
  the master plan as PR-19B.
- **builderCode is a URL query parameter**, not a bytes32 attached
  to V2 CLOB orders. Polymarket attributes order-level fees via the
  `builderCode` field on the official `py-clob-client-v2` SDK; the URL
  form is a placeholder until the bytes32 builder code is registered
  in Polymarket's builder portal. The publisher's
  `copy_trade_url` helper is structured so the registered bytes32
  form drops in with a one-line change.
- **Trace hashes are sha256, not CIDv1.** The on-chain field stored
  by `TraceLog` is named `ipfsCid` and is forward-compatible (string
  bytes), but the value written today is a local sha256 of the
  canonical trace JSON. Once IPFS/Irys pinning lands, the CIDv1 string
  drops into the same field with no migration.
- **LLM analyst requires `ANTHROPIC_API_KEY`** in `.env` to activate.
  Without it, the deterministic heuristic is the live runtime path
  (and is calibrated never to over-claim confidence > 6000 bps).
- **`sources` and `risk_factors`** in the paid `full` payload are
  derived from the analyst's own `ReasoningStep` items
  (`kind == "risk"`) plus the canonical Polymarket market URL. Live
  ingestion from external sources (news, Cambrian, etc.) is
  post-submission work.

## Does not yet work

- **EIP-3009 gasless unlock.** `DevUSDC` ships
  `transferWithAuthorization` + `cancelAuthorization` + an EIP-712
  domain — the primitives are in place — but `UnlockMarket.unlock()`
  calls plain `transferFrom`. Wiring the gasless authorization path
  through the unlock flow is post-submission work.
- **CCTP revenue bridge.** The README references Circle CCTP for
  bridging accrued builder fees Polygon → Arc. The integration is
  planned, not wired.
- **`PythiaVault.recordTrade` resolver close-out.**
  `agent/pythia/resolver.py` does not exist. Paper PnL is computed and
  written into the trace JSON when the publisher decides; the on-chain
  `recordTrade` call from a resolved market is post-submission.
- **Telegram broadcast at scale.** `pythia-bot broadcast …` works on a
  single trace JSON, but there is no production channel or scheduled
  broadcast loop. The pitch video uses a manual broadcast against a
  dev channel.
- **`UnlockMarket` hardening for mainnet.** The contract is testnet-only
  by intent: no `nonReentrant` modifier, no registry against `TraceLog`
  for trace-id existence, no per-trace price ceiling. Mainnet readiness
  requires both, plus an external review pass.

## Why "partially works" is the right framing

Every item in *Works today* runs in production against the live Arc
deployment. Every item in *Partially works* ships real on-chain
behaviour but a meaningful capability is conceded (visual gate, URL
param vs. bytes32, sha256 vs. pinned CID). Items in *Does not yet
work* are tracked as post-submission deliverables and explicitly *not*
claimed as shipping in the pitch video or README scoring table.
