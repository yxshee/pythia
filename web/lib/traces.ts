/**
 * Trace loader. Reads pick JSON files written by the agent
 * (`agent/pythia/trace.py:TracePublisher`) from the repo's `traces/` directory.
 *
 * Each file has three layered sections:
 *   - `preview`: free-tier projection (safe to render unauthenticated)
 *   - `full`: paid-tier projection, gated by UnlockMarket on Arc
 *   - `canonical`: raw analyst/plan/publication for replay
 *
 * Two snapshot files under `web/data/`:
 *   - `picks-preview.json`: public bundle without `full`. Used by SSR pages.
 *   - `picks-full.json`:    private bundle with `full`. Only read by the
 *                           server-side route handler at /api/traces/[id]/full
 *                           after verifying the caller's on-chain unlock.
 *
 * `loadPicks()` / `loadPick()` never expose `full`. `loadPickFull()` returns
 * the full payload and must only be called from server-side code that has
 * already verified payment.
 */
import { readFile, readdir, stat } from "node:fs/promises";
import { existsSync } from "node:fs";
import path from "node:path";

type Decision = "BUY_YES" | "BUY_NO" | "HOLD";
type Confidence = "low" | "medium" | "high";
type Risk = "conservative" | "balanced" | "aggressive";

type TracePreview = {
  trace_id: number;
  trace_hash: string;
  market_id: string;
  question: string;
  current_implied_yes: number;
  agent_probability_yes: number;
  decision: Decision;
  confidence: Confidence;
  risk: Risk;
  model: string;
  generated_at: string;
  end_date_iso: string;
};

export type TraceFull = TracePreview & {
  edge_bps: number;
  expected_value_pct: number;
  suggested_size_usdc: number;
  suggested_size_by_profile: { conservative: number; balanced: number; aggressive: number };
  reasoning: { kind: string; text: string }[];
  sources: unknown[];
  risk_factors: unknown[];
  market_url: string;
  copy_trade_url?: string;
  market_volume_24h_usd: number;
  market_liquidity_usd: number;
};

export type TraceOnchain = {
  tx_hash: string;
  block_number: number;
  trace_id: number;
  publisher: string;
  contract: string;
  chain_id: number;
};

export type Trace = {
  trace_id: number;
  generated_at: string;
  model: string;
  builder_code: string;
  theme: string;
  vault: string | null;
  onchain?: TraceOnchain;
  preview: TracePreview;
  // `full` is optional at the type level: SSR pages load via
  // `loadPicks()` (preview-only bundle). The full payload is only
  // present when a server-side route handler returns it after an
  // on-chain unlock check.
  full?: TraceFull;
};

function tracesDir(): string {
  // When `next dev` runs from web/, the repo's traces/ is one level up.
  return path.resolve(process.cwd(), "..", "traces");
}

function previewSnapshotPath(): string {
  return path.resolve(process.cwd(), "data", "picks-preview.json");
}

function fullSnapshotPath(): string {
  return path.resolve(process.cwd(), "data", "picks-full.json");
}

async function loadFromDir(dir: string): Promise<Trace[]> {
  const entries = await readdir(dir);
  const traceFiles = entries.filter((f) => /^trace-\d+\.json$/.test(f)).sort();
  const out: Trace[] = [];
  for (const f of traceFiles) {
    const raw = await readFile(path.join(dir, f), "utf-8");
    try {
      const parsed = JSON.parse(raw) as Trace;
      if (parsed.preview) {
        // Strip `full` so the in-memory cache used by pages never holds it.
        const { full: _drop, ...preview } = parsed;
        out.push(preview as Trace);
      }
    } catch {
      // Skip malformed files; the agent writes atomically but partial reads can happen.
    }
  }
  return out;
}

async function loadFromSnapshot(file: string): Promise<Trace[]> {
  const raw = await readFile(file, "utf-8");
  return JSON.parse(raw) as Trace[];
}

let cached: { at: number; traces: Trace[] } | null = null;
const TTL_MS = 30_000;

/** Load all picks, newest first. Cached for 30s. */
export async function loadPicks(): Promise<Trace[]> {
  if (cached && Date.now() - cached.at < TTL_MS) return cached.traces;

  const dir = tracesDir();
  let traces: Trace[] = [];
  if (existsSync(dir)) {
    try {
      const s = await stat(dir);
      if (s.isDirectory()) traces = await loadFromDir(dir);
    } catch {
      // Fall through to snapshot.
    }
  }

  if (traces.length === 0 && existsSync(previewSnapshotPath())) {
    traces = await loadFromSnapshot(previewSnapshotPath());
  }

  // Defense in depth: even if a future snapshot accidentally ships with
  // `full`, strip it before caching so the SSR layer never sees it.
  traces = traces.map((t) => {
    if (t.full) {
      const { full: _drop, ...rest } = t;
      return rest as Trace;
    }
    return t;
  });

  traces.sort((a, b) => b.trace_id - a.trace_id);
  cached = { at: Date.now(), traces };
  return traces;
}

export async function loadPick(traceId: number | string): Promise<Trace | null> {
  const id = Number(traceId);
  if (!Number.isFinite(id)) return null;
  const all = await loadPicks();
  return all.find((t) => t.trace_id === id) ?? null;
}

/**
 * Load the full payload for a single trace from the server-only bundle.
 * MUST NOT be called from client components or rendered into SSR HTML.
 * The /api/traces/[id]/full route handler calls this AFTER verifying the
 * caller's on-chain unlock via UnlockMarket.isUnlocked.
 */
export async function loadPickFull(
  traceId: number | string,
): Promise<Trace | null> {
  const id = Number(traceId);
  if (!Number.isFinite(id)) return null;

  // Prefer the per-trace JSON on disk (dev). Fall back to the full snapshot
  // (Vercel: only this bundle is included in the API route's function
  // bundle thanks to the explicit path.resolve call below).
  const dir = tracesDir();
  if (existsSync(dir)) {
    try {
      const s = await stat(dir);
      if (s.isDirectory()) {
        const padded = String(id).padStart(6, "0");
        const file = path.join(dir, `trace-${padded}.json`);
        if (existsSync(file)) {
          const raw = await readFile(file, "utf-8");
          return JSON.parse(raw) as Trace;
        }
      }
    } catch {
      // fall through
    }
  }

  if (existsSync(fullSnapshotPath())) {
    const all = await loadFromSnapshot(fullSnapshotPath());
    return all.find((t) => t.trace_id === id) ?? null;
  }

  return null;
}

export function shortHash(hash: string, head = 6, tail = 4): string {
  if (!hash) return "";
  if (hash.length <= head + tail + 1) return hash;
  return `${hash.slice(0, head)}…${hash.slice(-tail)}`;
}

export function fmtProb(p: number): string {
  return `${(p * 100).toFixed(1)}%`;
}
