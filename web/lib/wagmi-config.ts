/**
 * Wagmi + viem client config for Arc testnet.
 *
 * Notes:
 * - Arc uses USDC as the native gas token (6 decimals, not 18).
 * - `rpcUrls.default.http` is intentionally empty: ARC_RPC_URL is a
 *   server-side secret (Canteen-issued token). viem falls back to the
 *   wallet's injected provider for both reads and writes once the user
 *   is connected. Pre-connect, there is nothing to read.
 * - Connector is `injected({ shimDisconnect: true })` only: covers
 *   MetaMask, Rabby, Brave Wallet, Coinbase ext. WalletConnect / Reown
 *   would require a projectId + much heavier bundle for marginal gain
 *   in a hackathon demo.
 * - `ssr: true` so Next.js App Router renders happily; the wagmi state
 *   hydrates client-side after the Providers boundary mounts.
 */
import { createConfig, http } from "wagmi";
import { defineChain } from "viem";
import { injected } from "wagmi/connectors";

const chainId = Number(process.env.NEXT_PUBLIC_ARC_CHAIN_ID ?? 5042002);
const explorerUrl =
  process.env.NEXT_PUBLIC_ARC_EXPLORER_URL ?? "https://testnet.arcscan.app";

export const arc = defineChain({
  id: chainId,
  name: "Arc Testnet",
  network: "arc-testnet",
  nativeCurrency: { name: "USDC", symbol: "USDC", decimals: 6 },
  rpcUrls: { default: { http: [] } },
  blockExplorers: { default: { name: "Arcscan", url: explorerUrl } },
  testnet: true,
});

export const wagmiConfig = createConfig({
  chains: [arc],
  connectors: [injected({ shimDisconnect: true })],
  transports: { [arc.id]: http() },
  ssr: true,
});

declare module "wagmi" {
  interface Register {
    config: typeof wagmiConfig;
  }
}
