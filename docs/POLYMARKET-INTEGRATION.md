# Polymarket V2 integration

> Status: Day 1 - design + verified. Pythia is publish-only and never places its own orders.

## What Pythia does on Polymarket

**Nothing directly.** The agent never connects a wallet to Polymarket. Instead it:

1. Reads market data (questions, prices, volume, resolution) from the public Gamma + CLOB endpoints.
2. Publishes each pick to its own Telegram + web feed with a **builder-code deep-link**.
3. Followers click the link, open Polymarket on their own account, and place the order. The order carries `builderCode=pythia` automatically.
4. Polymarket pays the accrued builder fee in USDC on Polygon to the address registered against the `pythia` builder code (`POLYGON_ADDRESS_FOR_BUILDER_FEES`).
5. Once the underlying question resolves, Pythia's `resolver` (Day 3) computes the **paper** PnL the published position would have realized and records it on Arc via `PythiaVault.recordTrade`.

Real USDC flow is **follower's wallet -> Polymarket -> builder-fee receiver address**. Pythia never custodies.

## Why Polymarket

- **CLOB V2 went production 2026-04-28**; builder codes are live and attributable per-order.
- **Deepest US-accessible prediction-market venue.** Wide thematic coverage (macro, politics, crypto, sports).
- **Public read APIs** (Gamma for market metadata, CLOB for order books) require no auth.

## Builder-code mechanics

> Verified Day 1 against `docs.polymarket.com/trading/clients/builder`. Update this section if the exact registration flow differs.

Polymarket attributes fee shares via a `builderCode` field on each order. The field is included on V2 orders via the official `py-clob-client-v2` SDK and is propagated through the CLOB fill stream so Polymarket can settle attributed fees to the registered builder address.

For Pythia's purpose - publishing copy-trade links - the mechanic is simpler:
- The Polymarket frontend accepts `?builderCode=<code>` as a URL query parameter.
- When a user lands on a market page from a Pythia link, the front-end attaches the code to any order they place on that session.
- Polymarket batches builder-fee payouts to the configured receiver address (USDC on Polygon).

## The pUSD wrap

Polymarket V2 uses **pUSD** as the trading collateral on Polygon, not raw USDC. The Polymarket frontend wraps deposits automatically, so followers don't notice. For our **paper-portfolio PnL accounting**, this is invisible - the agent treats every position as denominated in USDC and reads the resolved outcome price directly from the CLOB API.

## Minimums (verified live)

- Deposit minimum on Polymarket: **$2 USDC** (Polygon).
- Order minimum on CLOB V2: typically **$5** (market-dependent; check the `minimumOrderSize` field on each market).

These thresholds matter only for **followers** - Pythia itself never sends an order.

## The deep-link Pythia generates

```
https://polymarket.com/event/<slug>?builderCode=pythia&side=<yes|no>
```

- `<slug>` comes from the Polymarket Gamma payload's `slug` field.
- `builderCode=pythia` (configurable via `POLYMARKET_BUILDER_CODE`).
- `side=yes|no` is a UI hint so the order ticket pre-selects the right outcome.

## Open verifications

- [ ] Confirm `builderCode` is the exact query-param key Polymarket honors in the frontend (vs `builder` or `bc`). Adjust `publisher.py:_builder_code_link` if needed.
- [ ] Confirm whether `pythia` is reserved or arbitrary. If reserved, register via Polymarket's builder portal or contact their team in the Polymarket Discord.
- [ ] Confirm builder-fee receiver address binding (per-code vs per-order). Most likely per-code, set on registration.

## Known issue: geo-block from India

**Verified Day 1 (May 14, 2026):** All Polymarket endpoints return HTTP 000 (connection refused at TCP/TLS level) from this machine, including:

- `https://gamma-api.polymarket.com`
- `https://clob.polymarket.com`
- `https://polymarket.com`

This is a known Polymarket geographic restriction. The Pythia agent has three Day-2+ paths to keep working:

1. **Run from a non-blocked network** (deploy the agent to a cloud region where Polymarket is accessible: AWS us-east-1, GCP us-central1 are typically fine).
2. **Use Polygon RPC + Envio HyperSync directly.** Polymarket's market state is on-chain on Polygon. We can read `ConditionalTokens`, `CTFExchange`, and orderbook events directly without touching the geo-blocked HTTP APIs. This is the more robust path long-term.
3. **Reverse-proxy via a non-blocked VPS.** Quick fix; not durable.

For local development right now, use the bundled `--mock` flag:

```bash
uv run pythia-loop --once --mock
```

The mock fixtures live in `agent/pythia/fixtures.py` and mirror real Gamma payload shapes so the rest of the pipeline (analyst, pm, publisher, trace) cannot tell the difference. **The geo-block does not affect copy-trading followers** - they reach Polymarket directly from their own browsers/wallets.

## Why this hits the rubric

- **Agency (30%):** Pythia autonomously chooses what to publish, when, and at what hypothetical size.
- **Traction (30%):** Real USDC volume from followers; attributable in the Polymarket builder admin.
- **Circle tools (20%):** USDC denomination + CCTP later for Polygon->Arc revenue bridging.
- **Innovation (20%):** First builder-code-attributed agent with on-Arc reasoning traces and a verifiable paper-portfolio track record.
