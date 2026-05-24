# Polymarket V2 integration

> Status: Pythia is publish-only and never places its own orders. See [`/STATUS.md`](../STATUS.md) for the broader delivery state.

## What Pythia does on Polymarket

**Nothing directly.** The agent never connects a wallet to Polymarket. Instead it:

1. Reads market data (questions, prices, volume, resolution) from the public Gamma + CLOB endpoints.
2. Publishes each BUY pick to its own Telegram + web feed with a **builder-code placeholder deep-link**.
3. Followers click the link, open Polymarket on their own account, and place the order themselves. The current URL parameter is a recommendation deep-link only; it is not verified order-level attribution.
4. Production fee attribution requires a registered Polymarket V2 bytes32 `builderCode` attached to the submitted order object. Until that is implemented and verified, Pythia does not claim builder-fee revenue.
5. A planned resolver will compute the **paper** PnL the published position would have realized and record it on Arc via `PythiaVault.recordTrade` after the underlying question resolves. The resolver close-out path is post-submission work; see [`/STATUS.md`](../STATUS.md).

Production flow is **follower's wallet -> Polymarket -> attributed builder-fee receiver address**, after order-level builder attribution is registered and verified. Pythia never custodies user funds.

## Why Polymarket

- **CLOB V2 went production 2026-04-28**; builder codes are live and attributable per-order.
- **Deepest US-accessible prediction-market venue.** Wide thematic coverage (macro, politics, crypto, sports).
- **Public read APIs** (Gamma for market metadata, CLOB for order books) require no auth.

## Builder-code mechanics

> Verified against Polymarket's Order Attribution docs. Update this section if the exact registration flow changes.

Polymarket attributes fee shares via a `builderCode` field on each order. The field is included on V2 orders via the official `py-clob-client-v2` SDK and is propagated through the CLOB fill stream so Polymarket can settle attributed fees to the registered builder address.

Current implemented attribution is partial:

- **Implemented:** recommendation links can carry a placeholder `?builderCode=<code>` query parameter and a `side=yes|no` UI hint for BUY decisions.
- **Not verified:** the Polymarket frontend honoring that URL parameter and attaching it to orders.
- **Required for production:** registered bytes32 builder code attached in the order object, then verified through builder trades / fee records.

## The pUSD wrap

Polymarket V2 uses **pUSD** as the trading collateral on Polygon, not raw USDC. The Polymarket frontend wraps deposits automatically, so followers don't notice. For our **paper-portfolio PnL accounting**, this is invisible - the agent treats every position as denominated in USDC and reads the resolved outcome price directly from the CLOB API.

## Minimums (verified live)

- Deposit minimum on Polymarket: **$2 USDC** (Polygon).
- Order minimum on CLOB V2: typically **$5** (market-dependent; check the `minimumOrderSize` field on each market).

These thresholds matter only for **followers** - Pythia itself never sends an order.

## The deep-link Pythia generates

```
https://polymarket.com/event/<slug>?builderCode=<bytes32-placeholder>&side=<yes|no>
```

- `<slug>` comes from the Polymarket Gamma payload's `slug` field.
- `builderCode=<bytes32-placeholder>` (configurable via `POLYMARKET_BUILDER_CODE`).
- `side=yes|no` is a UI hint so the order ticket pre-selects the right outcome.
- HOLD recommendations do not get a copy-trade link.

## Open verifications

Pending Polymarket builder-portal registration. The URL-parameter copy-trade
link is a placeholder until the bytes32 builder code is registered against the
canonical V2 SDK. See [`/STATUS.md`](../STATUS.md) for the live delivery state.

- Confirm whether Polymarket's frontend honors any builder-code query parameter at all. If not, remove it from links and rely only on SDK/order-object attribution.
- Confirm whether `pythia` is reserved or arbitrary. If reserved, register via Polymarket's builder portal or contact their team in the Polymarket Discord.
- Confirm builder-fee receiver address binding (per-code vs per-order). Most likely per-code, set on registration.

## Known issue: geo-block from India

**Verified May 14, 2026:** All Polymarket endpoints return HTTP 000 (connection refused at TCP/TLS level) from this machine, including:

- `https://gamma-api.polymarket.com`
- `https://clob.polymarket.com`
- `https://polymarket.com`

This is a known Polymarket geographic restriction. The Pythia agent has four paths to keep working:

1. **Run from a non-blocked network** (deploy the agent to a cloud region where Polymarket is accessible: AWS us-east-1, GCP us-central1 are typically fine).
2. **Import a live Gamma export** with `uv run python -m pythia.scripts.publish_live_feed --target 8 --gamma-json <file>`. This is the final-packaging fallback used when direct local Gamma access is blocked; the file must still be live Polymarket data, not fixtures.
3. **Use Polygon RPC + Envio HyperSync directly.** Polymarket's market state is on-chain on Polygon. We can read `ConditionalTokens`, `CTFExchange`, and orderbook events directly without touching the geo-blocked HTTP APIs. This is the more robust path long-term.
4. **Reverse-proxy via a non-blocked VPS.** Quick fix; not durable.

For local development only, the bundled `--mock` flag keeps the pipeline runnable:

```bash
uv run pythia-loop --once --mock
```

The mock fixtures live in `agent/pythia/fixtures.py` and mirror real Gamma payload shapes. They are not acceptable for the final public feed; the release gate is `uv run python -m pythia.scripts.publish_live_feed --target 8` against live Gamma data, either directly or through `--gamma-json`. **The geo-block does not affect copy-trading followers** - they reach Polymarket directly from their own browsers/wallets.

## Why this hits the rubric

- **Agency (30%):** Pythia autonomously chooses what to publish, when, and at what hypothetical size.
- **Traction (30%):** Web/Telegram distribution and Arc unlock proof today; external paid-user traction and attributed order proof remain future evidence.
- **Circle tools (20%):** Arc testnet DevUSDC unlocks today; CCTP/Gateway revenue integrations later.
- **Innovation (20%):** Paid reasoning traces with on-Arc provenance. A resolved-market paper-portfolio track record is planned but not claimed in this submission.
