import { Header } from "@/components/header";
import { PickCard } from "@/components/pick-card";
import { TractionStrip } from "@/components/traction-strip";
import { filterHomeFeed, loadPicks } from "@/lib/traces";

export const revalidate = 30;

export default async function HomePage() {
  const allPicks = await loadPicks();
  const picks = filterHomeFeed(allPicks);

  return (
    <>
      <Header />

      <main className="mx-auto max-w-6xl px-6 pb-24 pt-16">
        <section className="rise grid grid-cols-1 gap-12 md:grid-cols-[1.4fr_1fr] md:items-end">
          <div>
            <p className="mono text-[11px] uppercase tracking-[0.32em] text-oxblood">
              Agora · Alpha · Pythia
            </p>
            <h1 className="mt-5 font-display text-[44px] font-light leading-[0.98] tracking-[-0.02em] text-ink md:text-[64px]">
              The first <em className="text-oxblood not-italic">USDC-native</em> marketplace
              for <span className="underline decoration-gold/70 decoration-[3px] underline-offset-[6px]">auditable</span> AI reasoning traces.
            </h1>
            <p className="mt-7 max-w-xl font-display text-[17px] leading-[1.55] text-ink-soft md:text-[19px]">
              Pythia is an autonomous prediction-market analyst. It scans markets, records its
              source bundle, estimates the fair probability, sizes the call, and publishes a paid
              reasoning trace. Every trace is hashed on{" "}
              <a
                href="https://docs.arc.network"
                target="_blank"
                rel="noopener"
                className="text-ink underline underline-offset-[3px] decoration-ink/30 hover:decoration-ink"
              >
                Arc
              </a>
              . Unlock with 0.10 DevUSDC on Arc testnet.
            </p>
            <p className="mt-4 mono max-w-xl text-[10px] uppercase tracking-[0.22em] text-ink-faint">
              Demo research tool · not financial advice · testnet unlocks only
            </p>
          </div>

          <aside className="rounded-md border border-ink/10 bg-marble/70 p-5 md:p-6">
            <p className="mono text-[10px] uppercase tracking-[0.28em] text-ink-faint">
              Agent decisions per cycle
            </p>
            <ol className="mt-3 space-y-2 font-display text-[15px] leading-[1.3] text-ink">
              {[
                "Which markets to analyze",
                "Which market data and source bundle to trust",
                "What probability to assign",
                "Whether the edge is worth publishing",
                "What size + risk label per profile",
              ].map((row, i) => (
                <li key={row} className="flex items-baseline gap-3">
                  <span className="mono text-[10px] text-oxblood">0{i + 1}</span>
                  <span>{row}</span>
                </li>
              ))}
            </ol>
          </aside>
        </section>

        <TractionStrip />

        <section className="mt-20">
          <div className="flex items-baseline justify-between border-b border-ink/15 pb-3">
            <h2 className="mono text-[12px] uppercase tracking-[0.32em] text-ink">
              Today&rsquo;s picks &middot; {picks.length}
            </h2>
            <span className="mono text-[10px] uppercase tracking-[0.28em] text-ink-faint">
              cached 30s · Arc trace
            </span>
          </div>

          {picks.length === 0 ? (
            <Empty />
          ) : (
            <div className="mt-8 grid grid-cols-1 gap-6 md:grid-cols-2">
              {picks.map((trace, i) => (
                <PickCard key={trace.trace_id} trace={trace} index={i} />
              ))}
            </div>
          )}
        </section>

        <Footer />
      </main>
    </>
  );
}

function Empty() {
  return (
    <div className="mt-10 rounded-md border border-dashed border-ink/20 bg-marble/40 p-10 text-center">
      <p className="font-display text-lg text-ink">No picks yet today.</p>
      <p className="mono mt-3 text-[11px] uppercase tracking-[0.22em] text-ink-faint">
        Awaiting live market publish.
      </p>
    </div>
  );
}

function Footer() {
  return (
    <footer className="mt-24 flex flex-col items-start justify-between gap-3 border-t border-ink/10 pt-6 md:flex-row md:items-center">
      <p className="mono text-[10px] uppercase tracking-[0.32em] text-ink-faint">
        Agora Alpha · Canteen × Circle × Arc · 2026
      </p>
      <p className="mono text-[10px] uppercase tracking-[0.32em] text-ink-faint">
        chain 5042002 · DevUSDC testnet · builder-code placeholder <span className="text-ink">pythia</span>
      </p>
    </footer>
  );
}
