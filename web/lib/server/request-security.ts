import "server-only";

const DEFAULT_SITE_URL = "https://agoraalpha.vercel.app";
const HOST_RE =
  /^(?:localhost|(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)*[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?|\d{1,3}(?:\.\d{1,3}){3}|\[[0-9a-f:.]+\])(?::\d{1,5})?$/i;

function normalizeHost(raw: string | null): string | null {
  const host = raw?.trim().toLowerCase() ?? "";
  if (!host || host.length > 253 || host.includes(",") || !HOST_RE.test(host)) {
    return null;
  }
  return host;
}

function hostFromUrl(raw: string | undefined): string | null {
  if (!raw) return null;
  try {
    return normalizeHost(new URL(raw).host);
  } catch {
    return null;
  }
}

function allowedProductionHosts(): Set<string> {
  const out = new Set<string>();
  const canonical = hostFromUrl(process.env.NEXT_PUBLIC_SITE_URL ?? DEFAULT_SITE_URL);
  if (canonical) out.add(canonical);

  for (const raw of (process.env.PAYWALL_ALLOWED_HOSTS ?? "").split(",")) {
    const host = normalizeHost(raw);
    if (host) out.add(host);
  }
  return out;
}

/**
 * Return a request host that is safe to bind into signed paywall messages.
 * In production we only accept the canonical site host (plus explicit
 * PAYWALL_ALLOWED_HOSTS) instead of trusting arbitrary Host/X-Forwarded-Host
 * input as a security boundary.
 */
export function trustedRequestHost(req: Request): string | null {
  const host = normalizeHost(req.headers.get("host"));
  if (!host) return null;

  if (process.env.VERCEL_ENV !== "production") {
    return host;
  }

  return allowedProductionHosts().has(host) ? host : null;
}

export function utf8ByteLength(value: string): number {
  return Buffer.byteLength(value, "utf8");
}
