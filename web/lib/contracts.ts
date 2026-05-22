/**
 * Address constants + minimal ABIs for the wallet unlock flow.
 *
 * Addresses come from NEXT_PUBLIC_* env vars so deploy environments can
 * override without code changes. Defaults are the live Arc testnet
 * deploy (see README Deployments table). All four constants are
 * address-shape data — none are secret.
 *
 * ABIs are hand-curated to the four functions we actually call, plus
 * one event. Keeping them tight makes the bundle smaller and the
 * tool-call surface easier to audit.
 */

export const UNLOCK_MARKET = (process.env.NEXT_PUBLIC_UNLOCK_MARKET_ADDRESS ??
  "0xD8af5ebe36AC9eA736f40D749674FF1B0f4bd3cA") as `0x${string}`;

export const USDC = (process.env.NEXT_PUBLIC_USDC_ADDRESS_ARC ??
  "0x6d3bda6e93dd02a1c237642C5af837796bF47511") as `0x${string}`;

/** USDC price in base units (6 decimals). 100000 = 0.10 USDC. */
export const DEFAULT_UNLOCK_PRICE = 100_000n;

export const erc20Abi = [
  {
    type: "function",
    name: "balanceOf",
    stateMutability: "view",
    inputs: [{ name: "owner", type: "address" }],
    outputs: [{ type: "uint256" }],
  },
  {
    type: "function",
    name: "allowance",
    stateMutability: "view",
    inputs: [
      { name: "owner", type: "address" },
      { name: "spender", type: "address" },
    ],
    outputs: [{ type: "uint256" }],
  },
  {
    type: "function",
    name: "approve",
    stateMutability: "nonpayable",
    inputs: [
      { name: "spender", type: "address" },
      { name: "amount", type: "uint256" },
    ],
    outputs: [{ type: "bool" }],
  },
] as const;

export const unlockMarketAbi = [
  {
    type: "function",
    name: "unlock",
    stateMutability: "nonpayable",
    inputs: [{ name: "traceId", type: "uint256" }],
    outputs: [{ name: "pricePaid", type: "uint256" }],
  },
  {
    type: "function",
    name: "priceFor",
    stateMutability: "view",
    inputs: [{ name: "traceId", type: "uint256" }],
    outputs: [{ type: "uint256" }],
  },
  {
    type: "function",
    name: "isUnlocked",
    stateMutability: "view",
    inputs: [
      { name: "traceId", type: "uint256" },
      { name: "buyer", type: "address" },
    ],
    outputs: [{ type: "bool" }],
  },
  {
    type: "event",
    name: "Unlocked",
    inputs: [
      { indexed: true, name: "traceId", type: "uint256" },
      { indexed: true, name: "buyer", type: "address" },
      { indexed: false, name: "price", type: "uint256" },
    ],
  },
] as const;

/**
 * DevUSDC has an open mint() — anyone can mint testnet USDC to any
 * address. This powers the inline "Get test USDC" faucet in the
 * unlock card. Mainnet USDC would never expose this; on the live
 * Arc-testnet deploy we deploy DevUSDC specifically so the demo
 * works for any visitor.
 */
export const devUsdcMintAbi = [
  {
    type: "function",
    name: "mint",
    stateMutability: "nonpayable",
    inputs: [
      { name: "to", type: "address" },
      { name: "amount", type: "uint256" },
    ],
    outputs: [],
  },
] as const;
