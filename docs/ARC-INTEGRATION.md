# Arc integration

> Status: Deployed to Arc testnet. Contract addresses live in the repo `README.md` Deployments table; see [`/STATUS.md`](../STATUS.md) for the broader delivery state.

## Network

| Field | Value |
|---|---|
| Chain ID | `5042002` |
| RPC URL  | `https://rpc.testnet.arc-node.thecanteenapp.com/v1/<your-token>` |
| Native gas | USDC (no separate gas token) |
| Block explorer | `https://testnet.arcscan.app` |
| RPC token | obtained via `arc-canteen login` |

## Contracts

| Contract | Purpose | Source |
|---|---|---|
| `PythiaVault` | Paper-portfolio track-record vault (operator-gated; outsiders cannot pool USDC) | `contracts/src/PythiaVault.sol` |
| `TraceLog` | Authorized event emitter for reasoning-trace content hashes | `contracts/src/TraceLog.sol` |
| `UnlockMarket` | Pay-per-unlock for full reasoning traces (USDC on Arc) | `contracts/src/UnlockMarket.sol` |

Tests: `cd contracts && forge test`; see [`VERIFY.md`](../VERIFY.md) and CI for the current passing count.

### Deployed contract verification

| Contract | Address | Arcscan | Source verification |
|---|---|---|---|
| `TraceLog` | `0x48Af95Ed6F1E4dF73Dd62CE17731084a5E98AFB4` | https://testnet.arcscan.app/address/0x48Af95Ed6F1E4dF73Dd62CE17731084a5E98AFB4 | Source verified on 2026-05-25 via Arcscan/Blockscout. `getsourcecode` returns `ContractName=TraceLog`, compiler `v0.8.24+commit.e11b9ed9`, optimization enabled, and non-empty `SourceCode`. |
| `UnlockMarket` | `0xD8af5ebe36AC9eA736f40D749674FF1B0f4bd3cA` | https://testnet.arcscan.app/address/0xD8af5ebe36AC9eA736f40D749674FF1B0f4bd3cA | Source verified on 2026-05-25 via Arcscan/Blockscout. `getsourcecode` returns `ContractName=UnlockMarket`, compiler `v0.8.24+commit.e11b9ed9`, optimization enabled, and non-empty `SourceCode`. |
| `DevUSDC` | `0x6d3bda6e93dd02a1c237642C5af837796bF47511` | https://testnet.arcscan.app/address/0x6d3bda6e93dd02a1c237642C5af837796bF47511 | Source verified on 2026-05-25 via Arcscan/Blockscout. `getsourcecode` returns `ContractName=DevUSDC`, compiler `v0.8.24+commit.e11b9ed9`, optimization enabled, and non-empty `SourceCode`. |

Command used for the source-verification status:

```bash
curl "https://testnet.arcscan.app/api?module=contract&action=getsourcecode&address=<address>"
```

Command used for bytecode-equivalence proof:

```bash
ARC_RPC_URL=https://... python3 scripts/check_contract_bytecode.py
```

The checker strips Solidity CBOR metadata and zeroes immutable references before
comparing local Foundry artifacts with `cast code` output.

### UnlockMarket flow

```
+----------+  approve N test USDC +-------------+
|  Buyer   | ----------------> |    USDC     |
| (web app)|                   +-------------+
|          |
|          |  unlock(traceId)  +---------------+ DevUSDC   +----------+
|          | ----------------> | UnlockMarket  | --------> | Treasury |
+----------+                   |   (Arc)       |           +----------+
     |                         |               |
     |  isUnlocked?            +---------------+
     | <--------- gated private `full` payload via the web API
```

Pricing has two tiers - a flat `defaultPrice` and an optional per-trace override. Default at deploy is `0.10` in 6-decimal USDC-style base units, overridable via `UNLOCK_DEFAULT_PRICE` env. The current hackathon deploy uses `DevUSDC` on Arc testnet. `UnlockMarket` only unlocks owner-registered trace IDs, so users cannot pay for content the API cannot serve. The web app reads `priceFor(traceId)` to show the price in the unlock CTA, then verifies `isUnlocked(traceId, buyer)` before serving the full trace.

## Deployment

```bash
# 1) Authenticate the Arc CLI and grab RPC + chain config.
arc-canteen login
export ARC_RPC_URL="$(arc-canteen rpc-url)"
export ARC_CHAIN_ID=5042002

# 2) Confirm connectivity.
cast chain-id --rpc-url "$ARC_RPC_URL"   # expect 5042002

# 3) Deploy.
export PRIVATE_KEY=0x...                  # operator key (fresh for testnet)
export USDC_ADDRESS_ARC=0x...             # canonical USDC on Arc testnet (TBD - confirm with Anuhya)
cd contracts
forge script script/Deploy.s.sol \
    --rpc-url "$ARC_RPC_URL" \
    --broadcast \
    --skip-simulation
```

If `USDC_ADDRESS_ARC` is unset, `Deploy.s.sol` will spin up a `_DevUSDC` and use that. This is fine for the hackathon deploy while the canonical Arc USDC address is pending; subsequent deploys should point to canonical USDC.

After the script runs, copy the printed addresses into `.env`:

```bash
PYTHIA_VAULT_ADDRESS=0x...
TRACE_LOG_ADDRESS=0x...
USDC_ADDRESS_ARC=0x...
```

## Circle products in use

| Product | Where | Notes |
|---|---|---|
| USDC | `PythiaVault.asset` + `UnlockMarket.usdc` | USDC-denominated accounting. The current demo token is open-mint `DevUSDC` on Arc testnet; production uses canonical Circle USDC. |
| Wallets | operator + buyer EOAs | Dev-controlled wallet for the agent; user EOAs for unlocks (wagmi/viem on the web side). Circle Wallets are planned, not shipped. |
| Contracts | `PythiaVault`, `TraceLog`, `UnlockMarket` | Three Arc-native deployments. |
| App Kit | Planned | Arc App Kit can provide Send, Bridge, Swap, and Unified Balance flows; the current buyer flow is hand-wired via wagmi + viem. |
| x402 / session keys | Planned | The current paywall is `UnlockMarket` + signed EIP-191 nonce verification. x402-style paid API flows and session-key unlock/copy-trade flows are not shipped in this submission. |
| CCTP | Planned (post-submission) | Bridge accrued unlock revenue from Arc to other chains; revenue-flow demo only. |
| Paymaster | Stretch | Public Paymaster page does not list Arc; Arc already uses USDC as gas natively, so this is mostly redundant. |
| USYC | Stretch | Requires allowlist + $100k institutional minimum; out of MVP scope. |

## Why on Arc specifically

- **NAV must be on Arc** so vault accounting + decision provenance share one chain. The trace event and the trade record live on the same ledger.
- **Sub-second finality** means deposits and redemptions reprice instantly. No "pending" state for users.
- **USDC-as-gas** means there are no native-token UX traps. The vault holds and spends one asset.
- **~$0.01 fees** make publishing a trace event per decision economical. On a higher-fee chain, anchoring reasoning would eat into PnL.

## Open items (post-submission)

- DevUSDC is the deployed USDC for the hackathon demo; migrating to canonical USDC on Arc testnet is post-submission work.
- Run `arc-canteen update-product` to push our first product update.
- Wire `viem` / `web3.py` event listener for `TraceLog.Trace` to power the live feed (today the feed is statically baked from on-disk trace JSON).
