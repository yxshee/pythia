import "server-only";

type BlobClient = typeof import("@vercel/blob");

let cached: BlobClient | null | undefined;

export class StateStoreUnavailableError extends Error {
  constructor() {
    super("No durable server-side state store is configured");
  }
}

export function getBlobStateClient(): BlobClient | null {
  if (cached !== undefined) return cached;
  if (!process.env.BLOB_READ_WRITE_TOKEN) {
    cached = null;
    return cached;
  }
  // Lazy require keeps Blob's server-only SDK out of any client graph.
  // eslint-disable-next-line @typescript-eslint/no-require-imports
  cached = require("@vercel/blob") as BlobClient;
  return cached;
}

export function productionRequiresDurableState(): boolean {
  return process.env.VERCEL_ENV === "production";
}

export function isStateStoreUnavailableError(err: unknown): boolean {
  return err instanceof StateStoreUnavailableError;
}

export function isBlobWriteConflict(err: unknown): boolean {
  if (!err || typeof err !== "object") return false;
  const name = "name" in err ? String((err as { name?: unknown }).name) : "";
  const message =
    "message" in err ? String((err as { message?: unknown }).message).toLowerCase() : "";
  return (
    name === "BlobPreconditionFailedError" ||
    message.includes("precondition") ||
    message.includes("already exists") ||
    message.includes("already exist")
  );
}

export async function blobStreamToText(
  stream: ReadableStream<Uint8Array>,
  maxBytes: number,
): Promise<string> {
  const reader = stream.getReader();
  const decoder = new TextDecoder();
  let out = "";
  let bytes = 0;
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      bytes += value.byteLength;
      if (bytes > maxBytes) {
        throw new Error(`blob payload exceeds ${maxBytes} bytes`);
      }
      out += decoder.decode(value, { stream: true });
    }
    out += decoder.decode();
    return out;
  } finally {
    reader.releaseLock();
  }
}
