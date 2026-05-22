# Pythia

> USDC-native marketplace for auditable AI reasoning traces.
> A non-custodial Polymarket recommendation agent. Picks include a placeholder builder-code deep link; production attribution requires Polymarket's V2 bytes32 order-level `builderCode`. Reasoning + paper PnL are verifiable on Arc.

Built for the **Agora Agents Hackathon** (Canteen × Circle × Arc, May 11–25 2026).

## What it does

Pythia is a **recommendation agent**. It never trades its own funds and never custodies user funds. The loop is:

1. **Scout** ingests Polymarket markets from the public Gamma API. Mock fixtures exist only for local development and are not acceptable for the final public feed.
2. **Analyst** scores each candidate market for +EV using LLM reasoning (Claude Sonnet 4.6; a deterministic heuristic-v1 placeholder is the fallback path).
3. **PM** sizes a *hypothetical* position against a virtual `paper_capital` balance.
4. **Publisher** emits a two-section trace: a free **preview** (thesis + edge) for the Telegram broadcast and web feed, and a paid **full** payload (sizing, alternatives, risks) gated by `UnlockMarket`. Copy-trade CTAs deep-link to Polymarket with a `?builderCode=pythia` URL parameter — a placeholder for the bytes32 builder code, which has to be registered via Polymarket's builder portal before fees route on-chain (see [STATUS.md](STATUS.md#partially-works) for the live attribution state).
5. **Trace** writes the paid reasoning to server-only storage and logs the canonical hash on Arc via `TraceLog`. IPFS/Irys pinning is planned.

A planned resolver will compute the paper PnL the published position would have realized and post it on Arc via `PythiaVault.recordTrade` after the market resolves. The vault holds no real user capital — outsiders cannot deposit (operator-gated). It becomes a public, monotonic, on-chain track-record once resolver close-out is wired.

## Why on Arc, not on Polymarket

- **Arc is testnet-only today.** It cannot bridge canonical production USDC to Polygon for live trades — wrong primitive for execution.
- **Arc is the right primitive for verifiable provenance.** Sub-second finality, ~$0.01 fees, USDC-denominated gas. A claimed track-record on Arc is auditable byte-by-byte; a track-record in a Google Sheet is not.

## Hackathon scoring (self-assessment)

| Axis | Weight | Pythia |
|---|---|---|
| Agentic sophistication | 30% | Real Scout → Analyst → PM → Publisher → Trace loop. Autonomous on pick, sizing, hold/exit, trace generation. |
| Traction | 30% | Telegram/web preview tier + Arc testnet unlock flow + paper recommendation volume. Builder-fee attribution is designed but not verified. |
| Circle tools | 20% | Arc contracts + DevUSDC/testnet USDC unlock flow. Circle Wallets/App Kit/CCTP/Gateway/Paymaster are planned integrations. EIP-3009 primitives ship on `DevUSDC` but are not wired into unlock. See [STATUS.md](STATUS.md) for the live delivery state. |
| Innovation | 20% | Paid, on-chain-anchored reasoning-trace marketplace. Traces are split into free-preview / paid-full at the data-model level, not bolted on. |

## Stack

- **Contracts:** Solidity 0.8.24, Foundry, `via_ir = true`. Deployed to Arc testnet (chain ID 5042002 / 0x4cef52).
- **Agent runtime:** Python 3.13, async, uv-managed.
- **LLM:** Claude Sonnet 4.6 for the analyst; deterministic `heuristic-v1-placeholder` fallback.
- **Data sources:** Polymarket V2 Gamma for live market metadata/prices; CLOB orderbook enrichment is planned for slippage-aware sizing; Envio HyperSync for Arc state.
- **Trace storage:** server-only/private full payload snapshot + content hash logged on Arc through `TraceLog` (the on-chain field is named `ipfsCid` and is forward-compatible); IPFS/Irys pinning is planned post-submission.
- **Bridging:** Circle CCTP / Gateway — planned revenue and liquidity integrations; not wired today (see [STATUS.md](STATUS.md)).
- **Bot:** python-telegram-bot 22+.
- **Web:** Next.js 16, App Router, Tailwind v4, Fraunces + JetBrains Mono. Pick feed, trace explorer, unlock CTAs.

## Repo layout

```
pythia/
├── contracts/                        # Foundry project (42 tests, via_ir)
│   ├── src/
│   │   ├── PythiaVault.sol           # ERC4626-shaped USDC vault, paper-PnL track-record
│   │   ├── TraceLog.sol              # event emitter for reasoning-trace hashes
│   │   ├── UnlockMarket.sol          # registered per-trace DevUSDC/testnet unlock
│   │   └── DevUSDC.sol               # EIP-3009 testnet USDC (open mint, gasless authz)
│   ├── test/                         # 12 + 6 + 16 + 8 = 42 forge tests
│   └── script/Deploy.s.sol           # deploys all 4
├── agent/                            # Python agent loop
│   └── pythia/
│       ├── config.py
│       ├── scout.py                  # Polymarket Gamma ingest
│       ├── analyst.py                # LLM scorer (Claude) → heuristic fallback
│       ├── pm.py                     # paper-portfolio sizing
│       ├── publisher.py              # preview/full split, broadcast hand-off
│       ├── preview.py                # to_preview() / to_full() projections
│       ├── trace.py                  # canonical/preview/full JSON writer
│       ├── fixtures.py
│       └── loop.py                   # `pythia-loop --once [--mock]`
├── bot/                              # Telegram publisher
│   └── pythia_bot/
│       └── bot.py                    # `pythia-bot run` / `pythia-bot broadcast …`
├── web/                              # Next.js 16 dashboard (parchment / oxblood / gold)
└── docs/
    ├── POLYMARKET-INTEGRATION.md
    └── ARC-INTEGRATION.md
```

## Quickstart

```bash
# 1. Authenticate Arc CLI and fetch RPC URL
arc-canteen login
export ARC_RPC_URL="$(arc-canteen rpc-url)"

# 2. Build + test contracts
cd contracts
forge build
forge test                  # expect 42/42 passing

# 3. Deploy to Arc testnet (set PRIVATE_KEY first)
export PRIVATE_KEY=0x...
forge script script/Deploy.s.sol --rpc-url "$ARC_RPC_URL" --broadcast

# 4. Publish the final live-only feed from a non-blocked network
cd ../agent
uv sync
uv run python -m pythia.scripts.publish_live_feed --target 8

# 5. Run the Telegram bot
cd ../bot
uv sync
export TELEGRAM_BOT_TOKEN=...
uv run pythia-bot run
uv run pythia-bot broadcast ../traces/sanitized-full-trace.example.json
```

## Deployments

Arc testnet (chain ID 5042002):

| Contract       | Address                                      |
|----------------|----------------------------------------------|
| `PythiaVault`  | `0x7383dF0f0F0822b380092C5D2204258Ce4C842B5` |
| `TraceLog`     | `0x48Af95Ed6F1E4dF73Dd62CE17731084a5E98AFB4` |
| `UnlockMarket` | `0xD8af5ebe36AC9eA736f40D749674FF1B0f4bd3cA` |
| `DevUSDC`      | `0x6d3bda6e93dd02a1c237642C5af837796bF47511` |

Web demo: `https://agoraalpha.vercel.app` (Vercel deploy alias).

## Status

Current submission state (May 2026): contracts are deployed to Arc testnet (addresses above), and the web demo is live at https://agoraalpha.vercel.app. The final public feed has 8 unique live Polymarket traces generated by the `claude-sonnet-4-6` analyst, each anchored on Arc and free of fixture-derived market data. Agent loop runs end-to-end with the live analyst when `ANTHROPIC_API_KEY` is set, with a deterministic heuristic fallback for local development only. The system prompt is hardened against pre-2026 temporal framing and against citing invented spot prices, so reasoning stays grounded in market parameters the agent actually receives. Post-LLM gates flip `BUY_*` → `HOLD` whenever edge falls below 200 bps or market liquidity is under $25k, and the PM caps size at 10 bps of available depth. Pick pages have a DevUSDC/testnet unlock flow against the registered-trace `UnlockMarket` on Arc (connect → mint demo funds if needed → approve → unlock). The `/api/traces/[id]/full` route enforces a nonce-bound signature plus on-chain `isUnlocked` gate before returning the full payload, so server-rendered HTML and the public picks bundle never carry `trace.full`.

Web env vars (all `NEXT_PUBLIC_*`, all address-shape data, none secret — see `web/.env.local.example`): `UNLOCK_MARKET_ADDRESS`, `USDC_ADDRESS_ARC`, `ARC_CHAIN_ID`, `ARC_EXPLORER_URL`. The wallet provides its own RPC once the user connects; `ARC_RPC_URL` stays server-side only (Canteen-issued token, set on the Vercel project for the paywall route).

Open work: resolver → `PythiaVault.recordTrade` close-out so resolved markets surface paper PnL on-chain; live paid-unlock counts on the home traction strip; registered Polymarket V2 bytes32 builder-code attribution proof; CCTP/Gateway revenue bridge wiring.

Direct Polymarket API access may be geo-blocked from some local networks — see `docs/POLYMARKET-INTEGRATION.md` for mitigations (`publish_live_feed --gamma-json`, cloud-region deploy, direct Polygon-RPC scout, or HTTPS proxy).

## License

MIT
