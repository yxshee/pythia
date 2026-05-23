/**
 * Traction strip. Server-rendered honest snapshot of what the agent has
 * actually published on Arc, derived deterministically at build time from
 * `web/data/metrics.json` (which is itself derived from the private full snapshot,
 * which is itself derived from the trace JSONs on disk).
 *
 * No live RPC reads, no client JS, no secret env vars in the build context.
 * Paid-unlock counts are deliberately omitted in this version — they require
 * a live `UnlockMarket.unlockCount(traceId)` read and are honestly surfaced
 * via the arcscan link in the footnote instead of being faked here.
 *
 * The footnote separates the two on-chain surfaces:
 * - `TraceLog` (the `contract` field in metrics.json) is where trace
 *   hashes are anchored. Counts on the strip above are derived from
 *   `TraceLog.Published` events.
 * - `UnlockMarket` is where 0.10 DevUSDC/testnet unlock txs land. Counts of
 *   live paid unlocks are not surfaced on the strip; the arcscan link
 *   to the UnlockMarket address is the verifiable surface.
 */
import metrics from "@/data/metrics.json";
import { UNLOCK_MARKET } from "@/lib/contracts";
import { shortHash } from "@/lib/traces";

export function TractionStrip() {
  const explorer = metrics.explorer_url;
  const txUrl = metrics.latest_tx_hash
    ? `${explorer}/tx/${metrics.latest_tx_hash}`
    : null;
  const traceLogUrl = `${explorer}/address/${metrics.contract}`;
  const unlockMarketUrl = `${explorer}/address/${UNLOCK_MARKET}`;

  return (
    <section className="mt-20">
      <div className="flex items-baseline justify-between border-b border-ink/15 pb-3">
        <h2 className="mono text-[12px] uppercase tracking-[0.32em] text-ink">
          Traction
        </h2>
        <span className="mono text-[10px] uppercase tracking-[0.28em] text-ink-faint">
          on-chain · arc testnet
        </span>
      </div>

      <dl className="mt-6 grid grid-cols-1 gap-4 sm:grid-cols-2 md:grid-cols-4">
        <Card label="Published">
          <span className="mono text-[28px] font-medium tabular-nums text-ink">
            {metrics.published}
          </span>
          <span className="mono text-[10px] uppercase tracking-[0.22em] text-ink-faint">
            on-chain traces
          </span>
        </Card>

        <Card label="Paper volume">
          <span className="mono text-[28px] font-medium tabular-nums text-ink">
            ${metrics.paper_volume_usdc.toFixed(2)}
          </span>
          <span className="mono text-[10px] uppercase tracking-[0.22em] text-ink-faint">
            paper USDC · cumulative
          </span>
        </Card>

        <Card label="Latest publish">
          {txUrl ? (
            <a
              href={txUrl}
              target="_blank"
              rel="noopener noreferrer"
              title={metrics.latest_tx_hash ?? undefined}
              className="mono text-[18px] font-medium tabular-nums text-ink underline decoration-laurel/40 underline-offset-[3px] hover:decoration-ink"
            >
              {shortHash(metrics.latest_tx_hash ?? "", 10, 6)}
            </a>
          ) : (
            <span className="mono text-[18px] font-medium tabular-nums text-ink-faint">
              none yet
            </span>
          )}
          <span className="mono text-[10px] uppercase tracking-[0.22em] text-ink-faint">
            {metrics.latest_block
              ? `block ${metrics.latest_block.toLocaleString()}`
              : "awaiting publish"}
          </span>
        </Card>

        <Card label="Chain">
          <span className="mono text-[20px] font-medium tabular-nums text-ink">
            Arc · {metrics.chain_id}
          </span>
          <span className="mono text-[10px] uppercase tracking-[0.22em] text-laurel">
            USDC-native gas · sub-second finality
          </span>
        </Card>
      </dl>

      <p className="mt-5 mono text-[10px] uppercase tracking-[0.22em] text-ink-faint">
        Trace anchors:{" "}
        <a
          href={traceLogUrl}
          target="_blank"
          rel="noopener noreferrer"
          title={metrics.contract}
          className="text-ink underline decoration-ink/30 underline-offset-[3px] hover:decoration-ink"
        >
          TraceLog on Arcscan
        </a>
        {" · "}Paid unlocks:{" "}
        <a
          href={unlockMarketUrl}
          target="_blank"
          rel="noopener noreferrer"
          title={UNLOCK_MARKET}
          className="text-ink underline decoration-ink/30 underline-offset-[3px] hover:decoration-ink"
        >
          UnlockMarket on Arcscan
        </a>
        .
      </p>

      <p className="mt-2 mono text-[10px] tracking-[0.18em] text-ink-faint">
        Demo build — paper sizing only, no live capital and no user telemetry
        collected yet. The two on-chain surfaces above are the only metrics
        we will assert.
      </p>
    </section>
  );
}

function Card({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-2 rounded-md border border-ink/10 bg-marble/70 p-5">
      <dt className="mono text-[10px] uppercase tracking-[0.28em] text-ink-faint">
        {label}
      </dt>
      <dd className="flex flex-col gap-1">{children}</dd>
    </div>
  );
}
