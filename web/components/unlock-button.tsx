"use client";

/**
 * Wallet flow integration — connect → (optional faucet) → approve →
 * unlock → sign → fetch.
 *
 * Owns the full state machine for the per-trace USDC unlock against
 * `UnlockMarket` on Arc testnet. State is derived from on-chain reads
 * (priceFor / isUnlocked / balanceOf / allowance) plus the lifecycle of
 * the three write hooks. No useEffect timers; no race conditions.
 *
 * 2-tx flow: approve(UnlockMarket, price) then unlock(traceId). Exact
 * amount on the approve — not MaxUint256. Re-approval on subsequent
 * unlocks is fine; the demo is one trace per visitor.
 *
 * After each tx receipt confirms, we invalidate the affected tanstack
 * queries — the next render reads fresh on-chain state and advances
 * the state machine. Once isUnlocked flips true, the visitor signs a
 * domain-bound message and the client POSTs to /api/traces/[id]/full;
 * the server verifies the signature + on-chain unlock before returning
 * the gated payload. UnlockedContent renders that fetched payload.
 *
 * Honest scope: the public SSR HTML carries preview + on-chain anchor
 * only; the full reasoning/sizing payload only ever reaches the wire
 * via the authenticated fetch — never embedded in the page bundle.
 */

import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import {
  useAccount,
  useChainId,
  useConnect,
  useDisconnect,
  useReadContract,
  useSignMessage,
  useSwitchChain,
  useWaitForTransactionReceipt,
  useWriteContract,
} from "wagmi";
import { useQueryClient } from "@tanstack/react-query";

import { arc } from "@/lib/wagmi-config";
import {
  DEFAULT_UNLOCK_PRICE,
  UNLOCK_MARKET,
  USDC,
  devUsdcMintAbi,
  erc20Abi,
  unlockMarketAbi,
} from "@/lib/contracts";
import type { TraceFull } from "@/lib/traces";
import { UnlockedContent } from "@/components/unlocked-content";

type Props = {
  traceId: number;
};

type UiState =
  | "disconnected"
  | "wrong-chain"
  | "loading"
  | "unlocked"
  | "needs-funds"
  | "minting"
  | "needs-approve"
  | "approving"
  | "ready"
  | "unlocking"
  | "error";

function prettyError(err: unknown): string | null {
  if (!err) return null;
  const msg = err instanceof Error ? err.message : String(err);
  if (/user (rejected|denied)|reject(ed)?|denied/i.test(msg)) {
    return "Cancelled in wallet.";
  }
  // Strip wagmi/viem stack prefix; show the first sentence.
  const first = msg.split(/[.\n]/)[0];
  return first.slice(0, 220);
}

function isSignatureRejection(msg: string): boolean {
  return /cancelled in wallet|user (rejected|denied)/i.test(msg);
}

function fmtUsdc(base: bigint): string {
  // 6 decimals. We never display more than 2 fractional digits in the UI.
  const whole = Number(base) / 1_000_000;
  return whole.toFixed(whole < 1 ? 2 : 2);
}

export function UnlockButton({ traceId }: Props) {
  const traceIdBig = useMemo(() => BigInt(traceId), [traceId]);
  const queryClient = useQueryClient();

  const { address, isConnected } = useAccount();
  const chainId = useChainId();
  const onArc = chainId === arc.id;

  const { connect, connectors, isPending: isConnecting, error: connectError } = useConnect();
  const { disconnect } = useDisconnect();
  const { switchChain, isPending: isSwitching, error: switchError } = useSwitchChain();
  const { signMessageAsync, isPending: isSigning } = useSignMessage();

  // Full payload comes from the authenticated /api fetch — never SSR.
  const [fetchedFull, setFetchedFull] = useState<TraceFull | null>(null);
  const [isFetching, setIsFetching] = useState(false);
  const [fetchError, setFetchError] = useState<string | null>(null);

  const readsEnabled = Boolean(isConnected && onArc && address);

  // Reads
  const priceQuery = useReadContract({
    address: UNLOCK_MARKET,
    abi: unlockMarketAbi,
    functionName: "priceFor",
    args: [traceIdBig],
    query: { enabled: readsEnabled },
  });
  const isUnlockedQuery = useReadContract({
    address: UNLOCK_MARKET,
    abi: unlockMarketAbi,
    functionName: "isUnlocked",
    args: address ? [traceIdBig, address] : undefined,
    query: { enabled: readsEnabled },
  });
  const balanceQuery = useReadContract({
    address: USDC,
    abi: erc20Abi,
    functionName: "balanceOf",
    args: address ? [address] : undefined,
    query: { enabled: readsEnabled },
  });
  const allowanceQuery = useReadContract({
    address: USDC,
    abi: erc20Abi,
    functionName: "allowance",
    args: address ? [address, UNLOCK_MARKET] : undefined,
    query: { enabled: readsEnabled },
  });

  const price = (priceQuery.data as bigint | undefined) ?? DEFAULT_UNLOCK_PRICE;
  const isUnlocked = (isUnlockedQuery.data as boolean | undefined) ?? false;
  const balance = (balanceQuery.data as bigint | undefined) ?? 0n;
  const allowance = (allowanceQuery.data as bigint | undefined) ?? 0n;

  // Writes — three independent hooks so each has its own loading state.
  const mintWrite = useWriteContract();
  const approveWrite = useWriteContract();
  const unlockWrite = useWriteContract();

  const mintReceipt = useWaitForTransactionReceipt({ hash: mintWrite.data });
  const approveReceipt = useWaitForTransactionReceipt({ hash: approveWrite.data });
  const unlockReceipt = useWaitForTransactionReceipt({ hash: unlockWrite.data });

  // After each receipt confirms, invalidate the affected read queries so
  // the component re-renders with fresh on-chain state.
  useEffect(() => {
    if (mintReceipt.isSuccess) {
      queryClient.invalidateQueries({ queryKey: balanceQuery.queryKey });
    }
  }, [mintReceipt.isSuccess, queryClient, balanceQuery.queryKey]);

  useEffect(() => {
    if (approveReceipt.isSuccess) {
      queryClient.invalidateQueries({ queryKey: allowanceQuery.queryKey });
    }
  }, [approveReceipt.isSuccess, queryClient, allowanceQuery.queryKey]);

  useEffect(() => {
    if (unlockReceipt.isSuccess) {
      queryClient.invalidateQueries({ queryKey: isUnlockedQuery.queryKey });
      queryClient.invalidateQueries({ queryKey: balanceQuery.queryKey });
      queryClient.invalidateQueries({ queryKey: allowanceQuery.queryKey });
    }
  }, [
    unlockReceipt.isSuccess,
    queryClient,
    isUnlockedQuery.queryKey,
    balanceQuery.queryKey,
    allowanceQuery.queryKey,
  ]);

  // Sign a domain-bound message and exchange it for the gated payload.
  // The route handler at /api/traces/[id]/full verifies (a) signature
  // via viem, (b) UnlockMarket.isUnlocked(traceId, address) on Arc. We
  // never reach this code path without the on-chain unlock landing
  // first; the server check is the source of truth.
  const requestFullPayload = useCallback(async () => {
    if (!address) return;
    setIsFetching(true);
    setFetchError(null);
    try {
      const issued = new Date().toISOString();
      const message =
        "agoraalpha.vercel.app — unlock trace\n" +
        `Trace ID: ${traceId}\n` +
        `Address: ${address.toLowerCase()}\n` +
        `Issued: ${issued}`;
      const signature = await signMessageAsync({ message });
      const res = await fetch(`/api/traces/${traceId}/full`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ address, signature, message }),
      });
      if (!res.ok) {
        let detail = `HTTP ${res.status}`;
        try {
          const body = (await res.json()) as { error?: string };
          if (body?.error) detail = body.error;
        } catch {
          // ignore parse failures; default to status code
        }
        throw new Error(detail);
      }
      const payload = (await res.json()) as TraceFull;
      setFetchedFull(payload);
    } catch (err) {
      setFetchError(prettyError(err) ?? "fetch-failed");
    } finally {
      setIsFetching(false);
    }
  }, [address, signMessageAsync, traceId]);

  // Auto-fetch when on-chain unlock is true (either fresh from this
  // session or a returning visitor who already paid). Guard against
  // duplicate firing — `isFetching` and `fetchedFull` both gate.
  useEffect(() => {
    if (!isUnlocked) return;
    if (fetchedFull) return;
    if (isFetching) return;
    if (fetchError) return; // don't auto-retry on user rejection
    if (!address) return;
    void requestFullPayload();
  }, [isUnlocked, fetchedFull, isFetching, fetchError, address, requestFullPayload]);

  // Derived state.
  const writeError =
    mintWrite.error ?? approveWrite.error ?? unlockWrite.error ?? null;
  const receiptError =
    (mintReceipt.error ??
      approveReceipt.error ??
      unlockReceipt.error) ?? null;
  const errorMessage = prettyError(
    connectError ?? switchError ?? writeError ?? receiptError,
  );

  const state: UiState = (() => {
    if (!isConnected) return "disconnected";
    if (!onArc) return "wrong-chain";
    if (
      priceQuery.isLoading ||
      isUnlockedQuery.isLoading ||
      balanceQuery.isLoading ||
      allowanceQuery.isLoading
    ) {
      return "loading";
    }
    if (isUnlocked) return "unlocked";
    if (unlockWrite.isPending || unlockReceipt.isLoading) return "unlocking";
    if (approveWrite.isPending || approveReceipt.isLoading) return "approving";
    if (mintWrite.isPending || mintReceipt.isLoading) return "minting";
    if (balance < price) return "needs-funds";
    if (allowance < price) return "needs-approve";
    return "ready";
  })();

  // Action handlers.
  const onConnect = () => {
    if (typeof window !== "undefined" && !(window as { ethereum?: unknown }).ethereum) {
      // No injected provider — point the user at MetaMask install. We
      // don't try to silently fail or display a confusing modal.
      window.open("https://metamask.io/download", "_blank", "noopener,noreferrer");
      return;
    }
    // Use the connector instance wagmi already registered in wagmiConfig.
    // Constructing a fresh injected({...}) per click breaks wagmi v2's
    // state machine (it keys connection by registered-instance reference)
    // and silently disables shimDisconnect's autoConnect across reloads.
    const connector = connectors[0];
    if (!connector) return;
    connect({ connector });
  };

  const onSwitch = () => switchChain({ chainId: arc.id });

  const onMint = () => {
    if (!address) return;
    mintWrite.writeContract({
      address: USDC,
      abi: devUsdcMintAbi,
      functionName: "mint",
      args: [address, price],
      chainId: arc.id,
    });
  };

  const onApprove = () => {
    approveWrite.writeContract({
      address: USDC,
      abi: erc20Abi,
      functionName: "approve",
      args: [UNLOCK_MARKET, price],
      chainId: arc.id,
    });
  };

  const onUnlock = () => {
    unlockWrite.writeContract({
      address: UNLOCK_MARKET,
      abi: unlockMarketAbi,
      functionName: "unlock",
      args: [traceIdBig],
      chainId: arc.id,
    });
  };

  return (
    <>
      <section className="mt-14">
        <div className="flex items-baseline justify-between border-b border-ink/15 pb-3">
          <h2 className="mono text-[12px] uppercase tracking-[0.32em] text-ink">
            {isUnlocked ? "Unlocked" : "Behind the paywall"}
          </h2>
          <span
            className={`mono text-[10px] uppercase tracking-[0.22em] ${
              isUnlocked ? "text-laurel" : "text-oxblood"
            }`}
          >
            {isUnlocked ? "Paid · on Arc" : `${fmtUsdc(price)} USDC · Arc`}
          </span>
        </div>

        {isUnlocked && (isSigning || isFetching || fetchError) && (
          <div className="mt-6 rounded-md border border-ink/15 bg-marble/70 p-5">
            {fetchError ? (
              <div className="flex flex-wrap items-center justify-between gap-3">
                <p className="mono text-[11px] uppercase tracking-[0.18em] text-oxblood">
                  {isSignatureRejection(fetchError)
                    ? "Signature required to reveal the full payload."
                    : `Could not fetch payload: ${fetchError}`}
                </p>
                <button
                  type="button"
                  onClick={() => {
                    setFetchError(null);
                    void requestFullPayload();
                  }}
                  className="rounded bg-ink px-3 py-1.5 mono text-[10px] uppercase tracking-[0.18em] text-marble hover:bg-oxblood"
                >
                  Sign &amp; reveal
                </button>
              </div>
            ) : (
              <p className="mono text-[11px] uppercase tracking-[0.18em] text-ink-faint">
                {isSigning ? "Sign in your wallet to reveal…" : "Verifying on-chain unlock…"}
              </p>
            )}
          </div>
        )}

        {!isUnlocked && (
          <div className="relative mt-6 overflow-hidden rounded-md border border-ink/15 bg-marble/70 p-6">
            <div className="pointer-events-none absolute inset-0 bg-gradient-to-b from-marble/0 via-parchment-warm/60 to-parchment" />

            <ul className="relative space-y-3 font-display text-[15px] leading-[1.45] text-ink-soft">
              {[
                "Multi-step reasoning chain",
                "Suggested USDC size for conservative / balanced / aggressive profiles",
                "Expected value + edge in basis points",
                "Builder-code link to copy the trade on Polymarket",
                "Market liquidity + 24h volume context",
              ].map((row) => (
                <li key={row} className="flex items-baseline gap-3">
                  <span aria-hidden className="mono text-ink-faint">▸</span>
                  <span>{row}</span>
                </li>
              ))}
            </ul>

            <ActionRow
              state={state}
              price={price}
              balance={balance}
              isConnecting={isConnecting}
              isSwitching={isSwitching}
              onConnect={onConnect}
              onSwitch={onSwitch}
              onMint={onMint}
              onApprove={onApprove}
              onUnlock={onUnlock}
            />

            {state === "needs-funds" && (
              <p className="relative mt-4 mono text-[10px] uppercase tracking-[0.22em] text-ink-faint">
                DevUSDC on Arc testnet has an open <span className="text-ink">mint()</span> for demo
                purposes. Mainnet USDC has no such function — fund via Circle Mint or a bridge.
              </p>
            )}

            {errorMessage && (
              <p className="relative mt-4 rounded border border-oxblood/40 bg-oxblood/5 p-3 mono text-[11px] uppercase tracking-[0.18em] text-oxblood">
                {errorMessage}
              </p>
            )}

            {address && (
              <p className="relative mt-5 mono text-[10px] uppercase tracking-[0.22em] text-ink-faint">
                Connected · {address.slice(0, 6)}…{address.slice(-4)}{" "}
                <button
                  type="button"
                  onClick={() => disconnect()}
                  className="ml-2 underline decoration-ink-faint/40 hover:text-ink hover:decoration-ink"
                >
                  Disconnect
                </button>
              </p>
            )}
          </div>
        )}
      </section>

      <UnlockedContent full={fetchedFull} isUnlocked={isUnlocked} />
    </>
  );
}

function ActionRow({
  state,
  price,
  balance,
  isConnecting,
  isSwitching,
  onConnect,
  onSwitch,
  onMint,
  onApprove,
  onUnlock,
}: {
  state: UiState;
  price: bigint;
  balance: bigint;
  isConnecting: boolean;
  isSwitching: boolean;
  onConnect: () => void;
  onSwitch: () => void;
  onMint: () => void;
  onApprove: () => void;
  onUnlock: () => void;
}) {
  let label: ReactNode;
  let onClick: (() => void) | undefined;
  let disabled = false;

  switch (state) {
    case "disconnected":
      label = isConnecting ? "Connecting…" : "Connect wallet";
      onClick = onConnect;
      disabled = isConnecting;
      break;
    case "wrong-chain":
      label = isSwitching ? "Switching…" : "Switch to Arc";
      onClick = onSwitch;
      disabled = isSwitching;
      break;
    case "loading":
      label = "Reading on-chain state…";
      disabled = true;
      break;
    case "needs-funds":
      label = `Get ${fmtUsdc(price)} test USDC`;
      onClick = onMint;
      break;
    case "minting":
      label = "Minting test USDC…";
      disabled = true;
      break;
    case "needs-approve":
      label = `Approve ${fmtUsdc(price)} USDC`;
      onClick = onApprove;
      break;
    case "approving":
      label = "Approving…";
      disabled = true;
      break;
    case "ready":
      label = `Pay ${fmtUsdc(price)} USDC to unlock`;
      onClick = onUnlock;
      break;
    case "unlocking":
      label = "Unlocking…";
      disabled = true;
      break;
    case "unlocked":
      // Section header handles this case; ActionRow not rendered.
      return null;
    case "error":
      label = "Retry";
      onClick = onUnlock;
      break;
  }

  return (
    <div className="relative mt-7 flex flex-wrap items-center gap-4">
      <button
        type="button"
        onClick={onClick}
        disabled={disabled}
        className="group inline-flex items-center gap-3 rounded-md bg-ink px-5 py-3 mono text-[12px] uppercase tracking-[0.22em] text-marble shadow-[0_2px_0_rgba(15,14,12,0.4)] transition hover:bg-oxblood disabled:cursor-not-allowed disabled:opacity-60"
      >
        {label}
        {!disabled && (
          <span aria-hidden className="transition group-hover:translate-x-0.5">
            →
          </span>
        )}
      </button>
      {state === "needs-funds" && balance > 0n && (
        <span className="mono text-[10px] uppercase tracking-[0.22em] text-ink-faint">
          Balance: {fmtUsdc(balance)} USDC
        </span>
      )}
    </div>
  );
}
