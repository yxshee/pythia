"use client";

/**
 * Gated content card. Renders the full reasoning + sizing payload only
 * after the visitor has paid 0.10 USDC and the on-chain `isUnlocked`
 * read returns true.
 *
 * Honest scope note: the gate is visual. The server-rendered HTML still
 * contains `trace.full` because the pick page is a server component that
 * pre-renders everything; we hide the content in the DOM tree based on
 * client wallet state. A cryptographic server-side paywall (SIWE-signed
 * fetch) is a v2 stretch — far more code, marginal demo gain.
 *
 * When `isUnlocked` is false this component returns null, so the home
 * page and the locked state of the pick page remain unaffected.
 */
import type { Trace } from "@/lib/traces";

type Props = {
  full: Trace["full"];
  isUnlocked: boolean;
};

export function UnlockedContent({ full, isUnlocked }: Props) {
  if (!isUnlocked) return null;

  const sizing = full.suggested_size_by_profile;
  const evPct = full.expected_value_pct;
  const edgeBps = full.edge_bps;
  const decisionAccent =
    full.decision === "BUY_YES"
      ? "text-laurel"
      : full.decision === "BUY_NO"
        ? "text-oxblood"
        : "text-ink-soft";

  return (
    <section className="mt-10">
      <div className="flex items-baseline justify-between border-b border-laurel/40 pb-3">
        <h2 className="mono text-[12px] uppercase tracking-[0.32em] text-ink">
          Full trace
        </h2>
        <span className="mono text-[10px] uppercase tracking-[0.22em] text-laurel">
          Unlocked · on-chain
        </span>
      </div>

      <div className="mt-6 grid grid-cols-1 gap-4 sm:grid-cols-3">
        <Stat label="Decision" value={full.decision.replace("_", " ")} accent={decisionAccent} />
        <Stat label="Expected value" value={`${evPct >= 0 ? "+" : ""}${evPct.toFixed(2)}%`} />
        <Stat label="Edge" value={`${edgeBps >= 0 ? "+" : ""}${edgeBps} bps`} />
      </div>

      <div className="mt-6">
        <p className="mono text-[10px] uppercase tracking-[0.28em] text-ink-faint">
          Suggested USDC size — paper portfolio
        </p>
        <dl className="mt-3 grid grid-cols-3 gap-3">
          <SizeRow label="Conservative" value={sizing.conservative} />
          <SizeRow label="Balanced" value={sizing.balanced} />
          <SizeRow label="Aggressive" value={sizing.aggressive} />
        </dl>
      </div>

      <div className="mt-8">
        <p className="mono text-[10px] uppercase tracking-[0.28em] text-ink-faint">
          Reasoning chain
        </p>
        <ol className="mt-4 space-y-3">
          {full.reasoning.map((step, i) => (
            <li key={i} className="flex gap-3 font-display text-[15px] leading-[1.45] text-ink">
              <span className="mono w-6 shrink-0 text-[11px] uppercase tracking-[0.22em] text-ink-faint">
                {String(i + 1).padStart(2, "0")}
              </span>
              <div className="flex-1">
                <span className="mono mr-2 text-[10px] uppercase tracking-[0.22em] text-ink-faint">
                  {step.kind}
                </span>
                <span>{step.text}</span>
              </div>
            </li>
          ))}
        </ol>
      </div>

      <div className="mt-8 grid grid-cols-1 gap-4 sm:grid-cols-2">
        <Stat label="24h volume" value={`$${full.market_volume_24h_usd.toLocaleString()}`} />
        <Stat label="Liquidity" value={`$${full.market_liquidity_usd.toLocaleString()}`} />
      </div>

      <div className="mt-8 rounded-md border border-laurel/30 bg-marble/50 p-5">
        <p className="mono text-[10px] uppercase tracking-[0.28em] text-ink-faint">
          Copy the trade
        </p>
        <a
          href={full.market_url}
          target="_blank"
          rel="noopener noreferrer"
          className="mt-3 inline-flex items-baseline gap-2 font-display text-[16px] text-ink underline decoration-laurel/40 hover:decoration-ink"
        >
          Open on Polymarket
          <span aria-hidden className="mono text-[12px]">↗</span>
        </a>
        <p className="mt-2 mono text-[10px] uppercase tracking-[0.22em] text-ink-faint">
          Builder-code attributed to Pythia. Copy-trade fees in USDC flow to the agent.
        </p>
      </div>
    </section>
  );
}

function Stat({
  label,
  value,
  accent,
}: {
  label: string;
  value: string;
  accent?: string;
}) {
  return (
    <div className="flex flex-col gap-2 rounded-md border border-laurel/30 bg-marble/60 p-4">
      <span className="mono text-[10px] uppercase tracking-[0.28em] text-ink-faint">{label}</span>
      <span className={`mono text-[20px] font-medium tabular-nums ${accent ?? "text-ink"}`}>
        {value}
      </span>
    </div>
  );
}

function SizeRow({ label, value }: { label: string; value: number }) {
  return (
    <div className="flex flex-col gap-1 rounded-md border border-ink/10 bg-marble/40 p-3">
      <span className="mono text-[9px] uppercase tracking-[0.24em] text-ink-faint">{label}</span>
      <span className="mono text-[15px] font-medium tabular-nums text-ink">
        {value.toFixed(2)} <span className="text-[10px] text-ink-faint">USDC</span>
      </span>
    </div>
  );
}
