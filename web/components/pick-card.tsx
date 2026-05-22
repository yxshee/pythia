import Link from "next/link";
import type { Trace } from "@/lib/traces";
import { fmtProb, shortHash } from "@/lib/traces";

type Props = { trace: Trace; index?: number };

const decisionLabel: Record<Trace["preview"]["decision"], string> = {
  BUY_YES: "BUY YES",
  BUY_NO: "BUY NO",
  HOLD: "HOLD",
};

const confidenceLabel: Record<Trace["preview"]["confidence"], string> = {
  low: "low conf",
  medium: "med conf",
  high: "high conf",
};

const riskLabel: Record<Trace["preview"]["risk"], string> = {
  conservative: "conservative",
  balanced: "balanced",
  aggressive: "aggressive",
};

export function PickCard({ trace, index = 0 }: Props) {
  const p = trace.preview;
  const delta = p.agent_probability_yes - p.current_implied_yes;
  const direction =
    p.decision === "BUY_YES" ? "yes" : p.decision === "BUY_NO" ? "no" : "hold";
  const directionColor =
    direction === "yes" ? "text-laurel" : direction === "no" ? "text-oxblood" : "text-ink-soft";

  return (
    <Link
      href={`/pick/${p.trace_id}`}
      className="rise group relative flex flex-col gap-5 rounded-md border border-ink/10 bg-marble/80 p-6 shadow-[0_1px_0_rgba(15,14,12,0.04)] transition hover:border-ink/30 hover:shadow-[0_8px_24px_-8px_rgba(15,14,12,0.18)]"
      style={{ animationDelay: `${Math.min(index, 8) * 60}ms` }}
    >
      <header className="flex items-start justify-between gap-3">
        <span className="mono text-[10px] uppercase tracking-[0.28em] text-ink-faint">
          Pick #{String(p.trace_id).padStart(3, "0")} · {p.model}
        </span>
        <span className={`mono text-[10px] uppercase tracking-[0.22em] ${directionColor}`}>
          {decisionLabel[p.decision]}
        </span>
      </header>

      <h2 className="font-display text-[22px] leading-[1.15] tracking-tight text-ink">
        {p.question}
      </h2>

      <div className="grid grid-cols-3 gap-4 border-y border-ink/10 py-4">
        <Cell label="Market implied" value={fmtProb(p.current_implied_yes)} dim />
        <Cell
          label="Agent fair"
          value={fmtProb(p.agent_probability_yes)}
          accent={direction === "yes" ? "text-laurel" : direction === "no" ? "text-oxblood" : undefined}
        />
        <Cell
          label="Delta"
          value={`${delta >= 0 ? "+" : ""}${(delta * 100).toFixed(1)}pp`}
          dim
        />
      </div>

      <div className="flex flex-wrap gap-2">
        <Chip>{confidenceLabel[p.confidence]}</Chip>
        <Chip tone={p.risk === "aggressive" ? "warn" : "neutral"}>{riskLabel[p.risk]}</Chip>
        <Chip tone="ink">arc · {shortHash(p.trace_hash)}</Chip>
      </div>

      <footer className="mt-auto flex items-baseline justify-between">
        <span className="mono text-[11px] text-ink-faint">
          resolves {new Date(p.end_date_iso).toLocaleDateString(undefined, { dateStyle: "medium" })}
        </span>
        <span className="mono text-[11px] uppercase tracking-[0.22em] text-oxblood transition group-hover:text-oxblood-bright">
          Unlock 0.10 DevUSDC →
        </span>
      </footer>
    </Link>
  );
}

function Cell({
  label,
  value,
  dim,
  accent,
}: {
  label: string;
  value: string;
  dim?: boolean;
  accent?: string;
}) {
  return (
    <div className="flex flex-col gap-1">
      <span className="mono text-[9px] uppercase tracking-[0.28em] text-ink-faint">{label}</span>
      <span
        className={`mono text-2xl font-medium tabular-nums ${
          accent ?? (dim ? "text-ink-soft" : "text-ink")
        }`}
      >
        {value}
      </span>
    </div>
  );
}

function Chip({
  children,
  tone = "neutral",
}: {
  children: React.ReactNode;
  tone?: "neutral" | "warn" | "ink";
}) {
  const styles = {
    neutral: "border-ink/15 text-ink-soft",
    warn: "border-oxblood/30 text-oxblood",
    ink: "border-ink/30 text-ink",
  }[tone];
  return (
    <span
      className={`mono inline-flex items-center rounded-full border ${styles} px-2 py-[3px] text-[10px] uppercase tracking-[0.16em]`}
    >
      {children}
    </span>
  );
}
