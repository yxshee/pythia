/**
 * Trace loader. Reads pick JSON files written by the agent
 * (`agent/pythia/trace.py:TracePublisher`) from the repo's `traces/` directory.
 *
 * Each file has three layered sections:
 *   - `preview`: free-tier projection (safe to render unauthenticated)
 *   - `full`: paid-tier projection, gated by UnlockMarket on Arc
 *   - `canonical`: raw analyst/plan/publication for replay
 *
 * On Vercel / static builds where `../traces/` isn't shipped, we fall back to a
 * snapshot under `web/data/picks.json` if present. A future iteration may
 * swap the directory read for an indexer over Arc TraceLog events.
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

type TraceFull = TracePreview & {
  edge_bps: number;
  expected_value_pct: number;
  suggested_size_usdc: number;
  suggested_size_by_profile: { conservative: number; balanced: number; aggressive: number };
  reasoning: { kind: string; text: string }[];
  sources: unknown[];
  risk_factors: unknown[];
  market_url: string;
  market_volume_24h_usd: number;
  market_liquidity_usd: number;
};

export type Trace = {
  trace_id: number;
  generated_at: string;
  model: string;
  builder_code: string;
  theme: string;
  vault: string | null;
  preview: TracePreview;
  full: TraceFull;
};

function tracesDir(): string {
  // When `next dev` runs from web/, the repo's traces/ is one level up.
  return path.resolve(process.cwd(), "..", "traces");
}

function snapshotPath(): string {
  return path.resolve(process.cwd(), "data", "picks.json");
}

async function loadFromDir(dir: string): Promise<Trace[]> {
  const entries = await readdir(dir);
  const traceFiles = entries.filter((f) => /^trace-\d+\.json$/.test(f)).sort();
  const out: Trace[] = [];
  for (const f of traceFiles) {
    const raw = await readFile(path.join(dir, f), "utf-8");
    try {
      const parsed = JSON.parse(raw) as Trace;
      if (parsed.preview && parsed.full) out.push(parsed);
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

  if (traces.length === 0 && existsSync(snapshotPath())) {
    traces = await loadFromSnapshot(snapshotPath());
  }

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

export function shortHash(hash: string, head = 6, tail = 4): string {
  if (!hash) return "";
  if (hash.length <= head + tail + 1) return hash;
  return `${hash.slice(0, head)}…${hash.slice(-tail)}`;
}

export function fmtProb(p: number): string {
  return `${(p * 100).toFixed(1)}%`;
}
