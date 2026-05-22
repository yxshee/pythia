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
const siteUrl =
  process.env.NEXT_PUBLIC_SITE_URL ?? "https://agoraalpha.vercel.app";
const rpcProxyUrl = `${siteUrl}/api/rpc`;

export const arc = defineChain({
  id: chainId,
  name: "Arc Testnet",
  network: "arc-testnet",
  nativeCurrency: { name: "USDC", symbol: "USDC", decimals: 6 },
  // Client points at our same-origin /api/rpc proxy — a thin pass-through
  // to ARC_RPC_URL (server-only, token-bearing Canteen endpoint). viem's
  // http() transport needs a real URL or all post-connect reads fail
  // silently, and MetaMask's wallet_addEthereumChain rejects an empty
  // rpcUrls array. Server-side route handlers that want to bypass the
  // proxy hop can build their own viem client with transport(ARC_RPC_URL).
  rpcUrls: { default: { http: [rpcProxyUrl] } },
  blockExplorers: { default: { name: "Arcscan", url: explorerUrl } },
  testnet: true,
});
