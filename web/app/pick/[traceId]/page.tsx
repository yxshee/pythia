import Link from "next/link";
import { notFound } from "next/navigation";
import { Header } from "@/components/header";
import { fmtProb, loadPick, shortHash } from "@/lib/traces";

export const revalidate = 30;

type Props = { params: Promise<{ traceId: string }> };

export default async function PickPage({ params }: Props) {
  const { traceId } = await params;
  const trace = await loadPick(traceId);
  if (!trace) notFound();

  const p = trace.preview;
  const delta = p.agent_probability_yes - p.current_implied_yes;
  const lockedSteps = trace.full.reasoning.length;
  const direction =
    p.decision === "BUY_YES" ? "yes" : p.decision === "BUY_NO" ? "no" : "hold";
  const directionAccent =
    direction === "yes" ? "text-laurel" : direction === "no" ? "text-oxblood" : "text-ink-soft";

  return (
    <>
      <Header />

      <main className="mx-auto max-w-3xl px-6 pb-24 pt-12">
        <Link
          href="/"
          className="mono text-[11px] uppercase tracking-[0.28em] text-ink-soft hover:text-ink"
        >
          ← back to picks
        </Link>

        <article className="rise mt-8">
          <header className="flex flex-wrap items-baseline justify-between gap-3 border-b border-ink/10 pb-5">
            <p className="mono text-[10px] uppercase tracking-[0.32em] text-ink-faint">
              Pick #{String(p.trace_id).padStart(3, "0")} · {p.model}
            </p>
            <p className="mono text-[10px] uppercase tracking-[0.28em] text-ink-faint">
              {new Date(p.generated_at).toLocaleString(undefined, {
                dateStyle: "medium",
                timeStyle: "short",
              })}
            </p>
          </header>

          <h1 className="mt-6 font-display text-[34px] font-light leading-[1.05] tracking-[-0.02em] text-ink md:text-[44px]">
            {p.question}
          </h1>

          <div className={`mt-5 mono text-[12px] uppercase tracking-[0.22em] ${directionAccent}`}>
            decision · {p.decision.replace("_", " ")}
          </div>

          <section className="mt-10 grid grid-cols-1 gap-5 sm:grid-cols-3">
            <Stat label="Market implied YES" value={fmtProb(p.current_implied_yes)} />
            <Stat
              label="Agent fair YES"
              value={fmtProb(p.agent_probability_yes)}
              accent={direction === "yes" ? "text-laurel" : direction === "no" ? "text-oxblood" : undefined}
            />
            <Stat
              label="Delta"
              value={`${delta >= 0 ? "+" : ""}${(delta * 100).toFixed(1)}pp`}
            />
          </section>

          <section className="mt-12">
            <div className="flex items-baseline justify-between border-b border-ink/15 pb-3">
              <h2 className="mono text-[12px] uppercase tracking-[0.32em] text-ink">
                Free signal
              </h2>
              <span className="mono text-[10px] uppercase tracking-[0.22em] text-ink-faint">
                Always public
              </span>
            </div>

            <dl className="mt-6 grid grid-cols-1 gap-4 sm:grid-cols-2">
              <FreeRow term="Confidence" desc={p.confidence} />
              <FreeRow term="Risk band" desc={p.risk} />
              <FreeRow term="Resolves" desc={new Date(p.end_date_iso).toLocaleDateString()} />
              <FreeRow term="Builder code" desc={trace.builder_code} mono />
              <FreeRow
                term="Arc trace hash"
                desc={shortHash(p.trace_hash, 10, 6)}
                mono
                tooltip={p.trace_hash}
              />
              <FreeRow term="Theme" desc={trace.theme} mono />
            </dl>
          </section>

          {trace.onchain && (
            <section className="mt-14">
              <div className="flex items-baseline justify-between border-b border-ink/15 pb-3">
                <h2 className="mono text-[12px] uppercase tracking-[0.32em] text-ink">
                  On-chain anchor
                </h2>
                <span className="mono text-[10px] uppercase tracking-[0.22em] text-laurel">
                  Arc · chain {trace.onchain.chain_id}
                </span>
              </div>
              <dl className="mt-6 grid grid-cols-1 gap-4 sm:grid-cols-2">
                <FreeRow
                  term="Tx hash"
                  mono
                  tooltip={trace.onchain.tx_hash}
                  desc={
                    <a
                      href={`https://testnet.arcscan.app/tx/${trace.onchain.tx_hash}`}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="underline decoration-ink/30 hover:decoration-ink"
                    >
                      {shortHash(trace.onchain.tx_hash, 10, 6)}
                    </a>
                  }
                />
                <FreeRow term="Block" mono desc={String(trace.onchain.block_number)} />
                <FreeRow
                  term="Contract"
                  mono
                  tooltip={trace.onchain.contract}
                  desc={
                    <a
                      href={`https://testnet.arcscan.app/address/${trace.onchain.contract}`}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="underline decoration-ink/30 hover:decoration-ink"
                    >
                      {shortHash(trace.onchain.contract, 8, 6)}
                    </a>
                  }
                />
                <FreeRow
                  term="On-chain trace #"
                  mono
                  desc={`#${String(trace.onchain.trace_id).padStart(3, "0")}`}
                />
              </dl>
            </section>
          )}

          <section className="mt-14">
            <div className="flex items-baseline justify-between border-b border-ink/15 pb-3">
              <h2 className="mono text-[12px] uppercase tracking-[0.32em] text-ink">
                Behind the paywall
              </h2>
              <span className="mono text-[10px] uppercase tracking-[0.22em] text-oxblood">
                0.10 USDC · Arc
              </span>
            </div>

            <div className="relative mt-6 overflow-hidden rounded-md border border-ink/15 bg-marble/70 p-6">
              <div className="pointer-events-none absolute inset-0 bg-gradient-to-b from-marble/0 via-parchment-warm/60 to-parchment" />

              <ul className="relative space-y-3 font-display text-[15px] leading-[1.45] text-ink-soft">
                {[
                  `${lockedSteps} step reasoning chain`,
                  "Suggested USDC size for conservative / balanced / aggressive profiles",
                  "Explicit “why the agent may be wrong” section",
                  "Expected value math + edge in basis points",
                  "Source citations with weighted credibility",
                ].map((row) => (
                  <li key={row} className="flex items-baseline gap-3">
                    <span aria-hidden className="mono text-ink-faint">▸</span>
                    <span>{row}</span>
                  </li>
                ))}
              </ul>

              <div className="relative mt-7 flex flex-wrap items-center gap-4">
                <button
                  type="button"
                  className="group inline-flex items-center gap-3 rounded-md bg-ink px-5 py-3 mono text-[12px] uppercase tracking-[0.22em] text-marble shadow-[0_2px_0_rgba(15,14,12,0.4)] transition hover:bg-oxblood disabled:cursor-not-allowed disabled:opacity-60"
                  disabled
                  aria-label="Unlock the full trace - wallet flow coming soon"
                >
                  Unlock 0.10 USDC
                  <span aria-hidden className="transition group-hover:translate-x-0.5">→</span>
                </button>
                <span className="mono text-[10px] uppercase tracking-[0.22em] text-ink-faint">
                  Wallet flow lands <span className="text-ink">soon</span>
                </span>
              </div>
            </div>
          </section>
        </article>
      </main>
    </>
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
    <div className="flex flex-col gap-2 rounded-md border border-ink/10 bg-marble/70 p-5">
      <span className="mono text-[10px] uppercase tracking-[0.28em] text-ink-faint">{label}</span>
      <span className={`mono text-[34px] font-medium tabular-nums ${accent ?? "text-ink"}`}>
        {value}
      </span>
    </div>
  );
}

function FreeRow({
  term,
  desc,
  mono,
  tooltip,
}: {
  term: string;
  desc: React.ReactNode;
  mono?: boolean;
  tooltip?: string;
}) {
  return (
    <div className="flex items-baseline justify-between gap-4 border-b border-ink/5 py-2">
      <dt className="mono text-[10px] uppercase tracking-[0.28em] text-ink-faint">{term}</dt>
      <dd
        className={`text-right text-ink ${mono ? "mono text-[13px]" : "font-display text-[15px] capitalize"}`}
        title={tooltip}
      >
        {desc}
      </dd>
    </div>
  );
}
