/**
 * Arc testnet chain definition (viem-only).
 *
 * Extracted from `lib/wagmi-config.ts` so server-side code (Next.js
 * route handlers, edge runtime) can import the chain object without
 * pulling in wagmi / React / connectors. The wagmi config re-exports
 * this for the client provider.
 */
import { defineChain } from "viem";

const chainId = Number(process.env.NEXT_PUBLIC_ARC_CHAIN_ID ?? 5042002);
const explorerUrl =
  process.env.NEXT_PUBLIC_ARC_EXPLORER_URL ?? "https://testnet.arcscan.app";

export const arc = defineChain({
  id: chainId,
  name: "Arc Testnet",
  network: "arc-testnet",
  nativeCurrency: { name: "USDC", symbol: "USDC", decimals: 6 },
  // Client-side: empty so viem falls back to the wallet's injected provider.
  // Server-side: route handlers pass an explicit `transport: http(ARC_RPC_URL)`
  // when calling createPublicClient, so this empty default is fine.
  rpcUrls: { default: { http: [] } },
  blockExplorers: { default: { name: "Arcscan", url: explorerUrl } },
  testnet: true,
});
