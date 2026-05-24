#!/usr/bin/env node
/**
 * One-command wallet-equivalent flow for the paid unlock path.
 *
 * Mirrors the browser flow in web/components/unlock-button.tsx without a
 * UI: mint DevUSDC (if needed) -> approve UnlockMarket -> unlock(traceId)
 * -> GET nonce -> sign EIP-191 message -> POST gated payload -> replay
 * and assert the nonce is consumed. The output is a clean transcript that
 * can be pasted verbatim into VERIFY.md section 5.
 *
 * Usage (from repo root):
 *   PRIVATE_KEY=0xREPLACE_WITH_64_HEX  ARC_RPC_URL=https://REPLACE_WITH_ARC_RPC_URL  \
 *     node scripts/cli-unlock.mjs --base=https://agoraalpha.vercel.app --trace-id=24
 *
 * Required environment:
 *   PRIVATE_KEY   0x + 64 hex chars. NEVER use a production key.
 *   ARC_RPC_URL   Arc testnet RPC endpoint (or pass --rpc instead). The
 *                 deploy's /api/rpc proxy is read-only; tx submission
 *                 requires a real RPC URL with eth_sendRawTransaction.
 *
 * Flags:
 *   --base <url>      Deploy base URL (default https://agoraalpha.vercel.app).
 *   --trace-id <n>    Trace ID to unlock (default 24).
 *   --rpc <url>       Arc RPC URL override (else ARC_RPC_URL env).
 *   --dry-run         Stop after step 4 (price read); no tx sent.
 *   --help            Print this message.
 *
 * Exit codes:
 *   0  full transcript completed; replay rejected with nonce-used.
 *   1  uncaught error (viem revert, network failure, etc).
 *   2  missing/invalid required env or flags.
 *   4  nonce GET returned non-200.
 *   5  unlock POST returned non-200.
 *   6  replay POST returned 200 (gate is broken; investigate).
 */
import { parseArgs } from "node:util";
import {
  createPublicClient,
  createWalletClient,
  defineChain,
  formatUnits,
  http,
  parseAbi,
} from "viem";
import { privateKeyToAccount } from "viem/accounts";

const UNLOCK_MARKET = "0xD8af5ebe36AC9eA736f40D749674FF1B0f4bd3cA";
const USDC = "0x6d3bda6e93dd02a1c237642C5af837796bF47511";
const CHAIN_ID = 5042002;

const unlockMarketAbi = parseAbi([
  "function priceFor(uint256 traceId) view returns (uint256)",
  "function isUnlocked(uint256 traceId, address buyer) view returns (bool)",
  "function unlock(uint256 traceId) returns (uint256 pricePaid)",
]);
const erc20Abi = parseAbi([
  "function balanceOf(address owner) view returns (uint256)",
  "function allowance(address owner, address spender) view returns (uint256)",
  "function approve(address spender, uint256 amount) returns (bool)",
]);
const devUsdcMintAbi = parseAbi(["function mint(address to, uint256 amount)"]);

const arc = defineChain({
  id: CHAIN_ID,
  name: "Arc Testnet",
  network: "arc-testnet",
  nativeCurrency: { name: "USDC", symbol: "USDC", decimals: 6 },
  rpcUrls: { default: { http: ["http://localhost:0"] } },
  testnet: true,
});

function fmt(amount) {
  return `${formatUnits(amount, 6)} USDC`;
}

function maskUrl(url) {
  try {
    const u = new URL(url);
    return `${u.protocol}//${u.host}${u.pathname.length > 1 ? "/…" : ""}`;
  } catch {
    return "(unparseable)";
  }
}

function printHelp() {
  console.log(
    `Usage: PRIVATE_KEY=0x… ARC_RPC_URL=https://… node scripts/cli-unlock.mjs [options]

Options:
  --base <url>      Deploy base URL (default https://agoraalpha.vercel.app)
  --trace-id <n>    Trace ID to unlock (default 24)
  --rpc <url>       Arc RPC URL (else ARC_RPC_URL env)
  --dry-run         Stop after step 4 (price read); no tx sent
  --help            This message

The script mirrors web/components/unlock-button.tsx end to end:
  1-3 setup, 4 read price, 5 mint (if needed), 6 approve (if needed),
  7 unlock, 8 GET nonce, 9 sign, 10 POST, 11 replay (expect nonce-used).
`,
  );
}

function parseCli() {
  let parsed;
  try {
    parsed = parseArgs({
      options: {
        base: { type: "string", default: "https://agoraalpha.vercel.app" },
        "trace-id": { type: "string", default: "24" },
        rpc: { type: "string" },
        "dry-run": { type: "boolean", default: false },
        help: { type: "boolean", default: false },
      },
      strict: true,
    });
  } catch (err) {
    console.error(`bad flag: ${err.message}`);
    printHelp();
    process.exit(2);
  }
  if (parsed.values.help) {
    printHelp();
    process.exit(0);
  }
  let traceId;
  try {
    traceId = BigInt(parsed.values["trace-id"]);
  } catch {
    console.error(`--trace-id must be an integer; got ${parsed.values["trace-id"]}`);
    process.exit(2);
  }
  const base = parsed.values.base.replace(/\/+$/, "");
  const rpc = parsed.values.rpc ?? process.env.ARC_RPC_URL;
  return { base, traceId, rpc, dryRun: parsed.values["dry-run"] };
}

function loadPrivateKey() {
  const key = process.env.PRIVATE_KEY;
  if (!key) {
    console.error("PRIVATE_KEY environment variable is required.");
    console.error("Use a fresh testnet key; never reuse a production key.");
    process.exit(2);
  }
  if (!/^0x[0-9a-fA-F]{64}$/.test(key)) {
    console.error("PRIVATE_KEY must be 0x followed by exactly 64 hex characters.");
    process.exit(2);
  }
  return key;
}

async function readJsonOrText(res) {
  const text = await res.text();
  try {
    return { json: JSON.parse(text), text };
  } catch {
    return { json: null, text };
  }
}

async function main() {
  const { base, traceId, rpc, dryRun } = parseCli();
  const privateKey = loadPrivateKey();
  const account = privateKeyToAccount(privateKey);

  if (!rpc) {
    console.error("ARC_RPC_URL (or --rpc) is required for chain reads/writes.");
    console.error("The deploy's /api/rpc proxy is read-only; writes need a full RPC URL.");
    process.exit(2);
  }

  const publicClient = createPublicClient({ chain: arc, transport: http(rpc) });
  const walletClient = createWalletClient({ account, chain: arc, transport: http(rpc) });

  console.log(`[1/11] Wallet:    ${account.address}`);
  console.log(`[2/11] Args:      base=${base}  trace-id=${traceId}  rpc=${maskUrl(rpc)}  dry-run=${dryRun}`);
  console.log(`[3/11] Clients:   viem public+wallet on chain ${CHAIN_ID}`);

  const price = await publicClient.readContract({
    address: UNLOCK_MARKET,
    abi: unlockMarketAbi,
    functionName: "priceFor",
    args: [traceId],
  });
  console.log(`[4/11] priceFor:  ${fmt(price)} (raw=${price})`);

  if (dryRun) {
    console.log(`[dry-run] stopping before any tx; exit 0`);
    process.exit(0);
  }

  const balance = await publicClient.readContract({
    address: USDC,
    abi: erc20Abi,
    functionName: "balanceOf",
    args: [account.address],
  });
  console.log(`         balance:  ${fmt(balance)}`);
  if (balance < price) {
    console.log(`[5/11] mint:      ${fmt(price * 2n)} (balance below price)`);
    const hash = await walletClient.writeContract({
      address: USDC,
      abi: devUsdcMintAbi,
      functionName: "mint",
      args: [account.address, price * 2n],
    });
    console.log(`         tx:       ${hash}`);
    const receipt = await publicClient.waitForTransactionReceipt({ hash });
    console.log(`         status:   ${receipt.status} block=${receipt.blockNumber}`);
  } else {
    console.log(`[5/11] mint:      skipped (balance >= price)`);
  }

  const allowance = await publicClient.readContract({
    address: USDC,
    abi: erc20Abi,
    functionName: "allowance",
    args: [account.address, UNLOCK_MARKET],
  });
  console.log(`         allow:    ${fmt(allowance)}`);
  if (allowance < price) {
    console.log(`[6/11] approve:   ${fmt(price)} to ${UNLOCK_MARKET}`);
    const hash = await walletClient.writeContract({
      address: USDC,
      abi: erc20Abi,
      functionName: "approve",
      args: [UNLOCK_MARKET, price],
    });
    console.log(`         tx:       ${hash}`);
    const receipt = await publicClient.waitForTransactionReceipt({ hash });
    console.log(`         status:   ${receipt.status} block=${receipt.blockNumber}`);
  } else {
    console.log(`[6/11] approve:   skipped (allowance >= price)`);
  }

  const alreadyUnlocked = await publicClient.readContract({
    address: UNLOCK_MARKET,
    abi: unlockMarketAbi,
    functionName: "isUnlocked",
    args: [traceId, account.address],
  });
  if (alreadyUnlocked) {
    console.log(`[7/11] unlock:    skipped (already unlocked on-chain)`);
  } else {
    console.log(`[7/11] unlock:    calling UnlockMarket.unlock(${traceId})`);
    const hash = await walletClient.writeContract({
      address: UNLOCK_MARKET,
      abi: unlockMarketAbi,
      functionName: "unlock",
      args: [traceId],
    });
    console.log(`         tx:       ${hash}`);
    const receipt = await publicClient.waitForTransactionReceipt({ hash });
    console.log(`         status:   ${receipt.status} block=${receipt.blockNumber}`);
  }

  const nonceUrl = `${base}/api/traces/${traceId}/full?address=${encodeURIComponent(account.address)}`;
  console.log(`[8/11] GET:       ${nonceUrl}`);
  const nonceRes = await fetch(nonceUrl, {
    method: "GET",
    headers: { accept: "application/json" },
  });
  const { json: noncePayload, text: nonceText } = await readJsonOrText(nonceRes);
  if (!nonceRes.ok || !noncePayload) {
    console.error(`         HTTP ${nonceRes.status}: ${nonceText.slice(0, 200)}`);
    console.error(`nonce GET failed; aborting before sign.`);
    process.exit(4);
  }
  console.log(`         nonce:    ${noncePayload.nonce}`);
  console.log(`         issued:   ${noncePayload.issuedAt}`);
  console.log(`         expires:  ${noncePayload.expiresAt}`);

  console.log(`[9/11] sign:      EIP-191 message (${noncePayload.message.length} chars)`);
  const signature = await account.signMessage({ message: noncePayload.message });
  console.log(`         sig:      ${signature.slice(0, 18)}…${signature.slice(-4)}`);

  const postUrl = `${base}/api/traces/${traceId}/full`;
  const postBody = JSON.stringify({
    address: account.address,
    nonce: noncePayload.nonce,
    signature,
    message: noncePayload.message,
  });
  console.log(`[10/11] POST:     ${postUrl}`);
  const postRes = await fetch(postUrl, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: postBody,
  });
  const { json: postJson, text: postText } = await readJsonOrText(postRes);
  console.log(`         HTTP ${postRes.status}: ${postText.slice(0, 240)}${postText.length > 240 ? "…" : ""}`);
  if (!postRes.ok) {
    console.error(`unlock POST failed (expected 200).`);
    process.exit(5);
  }
  if (!postJson) {
    console.error(`unlock POST returned 200 but body is not JSON.`);
    process.exit(5);
  }

  console.log(`[11/11] replay:   POST same body again (expect 401 nonce-used)`);
  const replayRes = await fetch(postUrl, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: postBody,
  });
  const { text: replayText } = await readJsonOrText(replayRes);
  console.log(`         HTTP ${replayRes.status}: ${replayText.slice(0, 200)}`);
  if (replayRes.ok) {
    console.error(`replay POST returned 200; paywall replay-guard is broken.`);
    process.exit(6);
  }
  if (!/nonce-used/.test(replayText)) {
    console.error(`replay rejected but body does not say nonce-used; investigate.`);
    process.exit(6);
  }

  console.log(`\nDONE: 11/11 steps complete. Trace ${traceId} unlocked and replay rejected.`);
}

main().catch((err) => {
  const detail = err?.shortMessage ?? err?.message ?? String(err);
  console.error(`\nFAIL: ${detail}`);
  process.exit(1);
});
