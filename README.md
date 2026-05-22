# Pythia

> USDC-native marketplace for auditable AI reasoning traces.
> A non-custodial Polymarket recommendation agent. Picks are attributed via Polymarket's `builderCode`; reasoning + paper PnL are verifiable on Arc.

Built for the **Agora Agents Hackathon** (Canteen × Circle × Arc, May 11–25 2026).

## What it does

Pythia is a **recommendation agent**. It never trades its own funds and never custodies user funds. The loop is:

1. **Scout** ingests Polymarket markets from the public Gamma API (or `--mock` fixtures when geo-blocked).
2. **Analyst** scores each candidate market for +EV using LLM reasoning (Claude Sonnet 4.6; a deterministic heuristic-v1 placeholder is the fallback path).
3. **PM** sizes a *hypothetical* position against a virtual `paper_capital` balance.
4. **Publisher** emits a two-section trace: a free **preview** (thesis + edge) for the Telegram broadcast and web feed, and a paid **full** payload (sizing, alternatives, risks) gated by `UnlockMarket`. Copy-trade CTAs deep-link to Polymarket with `?builderCode=pythia`; attributed fees in USDC flow to Pythia's address.
5. **Trace** writes the full reasoning to disk and logs the canonical hash on Arc via `TraceLog`. IPFS pinning (Irys) is planned.

When a market resolves, the agent's resolver computes the paper PnL the published position would have realized and posts it on Arc via `PythiaVault.recordTrade`. The vault holds no real user capital — outsiders cannot deposit (operator-gated). It is a public, monotonic, on-chain track-record.

## Why on Arc, not on Polymarket

- **Arc is testnet-only today.** It cannot bridge real USDC to Polygon for live trades — wrong primitive for execution.
- **Arc is the right primitive for verifiable provenance.** Sub-second finality, ~$0.01 fees, USDC-denominated gas. A claimed track-record on Arc is auditable byte-by-byte; a track-record in a Google Sheet is not.

## Hackathon scoring (self-assessment)

| Axis | Weight | Pythia |
|---|---|---|
| Agentic sophistication | 30% | Real Scout → Analyst → PM → Publisher → Trace loop. Autonomous on pick, sizing, hold/exit, trace generation. |
| Traction | 30% | Telegram free tier + attributed copy-trader volume + builder fees in USDC. Non-custodial → lower friction onboarding. |
| Circle tools | 20% | USDC + Wallets + 4 Arc contracts (`PythiaVault`, `TraceLog`, `UnlockMarket`, `DevUSDC`) + EIP-3009 gasless unlock + CCTP-ready revenue bridge (Polygon → Arc). |
| Innovation | 20% | First builder-code-attributed reasoning-trace marketplace. Traces are split into free-preview / paid-full at the data-model level, not bolted on. |

## Stack

- **Contracts:** Solidity 0.8.24, Foundry, `via_ir = true`. Deployed to Arc testnet (chain ID 5042002 / 0x4cef52).
- **Agent runtime:** Python 3.13, async, uv-managed.
- **LLM:** Claude Sonnet 4.6 for the analyst; deterministic `heuristic-v1-placeholder` fallback.
- **Data sources:** Polymarket V2 Gamma + CLOB REST (`--mock` fallback when geo-blocked); Envio HyperSync for Arc state.
- **Trace storage:** local disk → IPFS via Irys (optional); CIDv1 hashes logged on Arc through `TraceLog`.
- **Bridging:** Circle CCTP — revenue-only, Polygon → Arc for accrued builder fees.
- **Bot:** python-telegram-bot 22+.
- **Web:** Next.js 16, App Router, Tailwind v4, Fraunces + JetBrains Mono. Pick feed, trace explorer, unlock CTAs.

## Repo layout

```
pythia/
├── contracts/                        # Foundry project (39 tests, via_ir)
│   ├── src/
│   │   ├── PythiaVault.sol           # ERC4626-shaped USDC vault, paper-PnL track-record
│   │   ├── TraceLog.sol              # event emitter for reasoning-trace hashes
│   │   ├── UnlockMarket.sol          # per-trace USDC unlock + EIP-3009 receipt
│   │   └── DevUSDC.sol               # EIP-3009 testnet USDC (open mint, gasless authz)
│   ├── test/                         # 12 + 6 + 13 + 8 = 39 forge tests
│   └── script/Deploy.s.sol           # deploys all 4
├── agent/                            # Python agent loop
│   └── pythia/
│       ├── config.py
│       ├── scout.py                  # Polymarket Gamma ingest (+ --mock fixtures)
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
forge test                  # expect 39/39 passing

# 3. Deploy to Arc testnet (set PRIVATE_KEY first)
export PRIVATE_KEY=0x...
forge script script/Deploy.s.sol --rpc-url "$ARC_RPC_URL" --broadcast

# 4. Run the agent loop
cd ../agent
uv sync
uv run pythia-loop --once --mock     # offline-safe demo (uses fixtures)
uv run pythia-loop --once            # live mode (Polymarket Gamma)

# 5. Run the Telegram bot
cd ../bot
uv sync
export TELEGRAM_BOT_TOKEN=...
uv run pythia-bot run
uv run pythia-bot broadcast ../traces/trace-000001.json
```

## Deployments

Arc testnet (chain ID 5042002):

| Contract       | Address                                      |
|----------------|----------------------------------------------|
| `PythiaVault`  | `0x7383dF0f0F0822b380092C5D2204258Ce4C842B5` |
| `TraceLog`     | `0x48Af95Ed6F1E4dF73Dd62CE17731084a5E98AFB4` |
| `UnlockMarket` | `0x6478370B34Dc31498C68734EB2647C99A333b6D4` |
| `DevUSDC`      | `0x6d3bda6e93dd02a1c237642C5af837796bF47511` |

Web demo: `https://agoraalpha.vercel.app` (Vercel deploy alias).

## Status

Day 12 of 15 (submission May 25). Contracts: 39 forge tests green, deployed to Arc testnet (addresses above). Web shell live at https://agoraalpha.vercel.app with fixture trace feed. Agent loop runs end-to-end against fixtures with builder-code links rendered; LLM analyst code path wired with heuristic fallback. Pick pages have a working USDC unlock flow against `UnlockMarket` on Arc (connect → approve → unlock); test USDC available via the inline `DevUSDC.mint()` faucet — note that `mint()` is open by design on testnet only, mainnet USDC has no such function.

Web env vars (all `NEXT_PUBLIC_*`, all address-shape data, none secret — see `web/.env.local.example`): `UNLOCK_MARKET_ADDRESS`, `USDC_ADDRESS_ARC`, `ARC_CHAIN_ID`, `ARC_EXPLORER_URL`. The wallet provides its own RPC once the user connects; `ARC_RPC_URL` stays server-side only (Canteen-issued token).

Open work: activate live LLM call path in `analyst.py` (needs `ANTHROPIC_API_KEY` in `.env`; heuristic is the live runtime today); resolver → `PythiaVault.recordTrade` close-out; cryptographic server-side paywall (current unlock is a visual UI gate against on-chain payment, not a SIWE-signed fetch).

Polymarket APIs are geo-blocked from this development machine — see `docs/POLYMARKET-INTEGRATION.md` for mitigations (cloud-region deploy, direct Polygon-RPC scout, or HTTPS proxy).

## License

MIT
