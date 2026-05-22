"use client";

/**
 * Client-only boundary that hosts the wagmi + tanstack-query context.
 *
 * Wrapped around `{children}` in `app/layout.tsx`. The rest of the app —
 * server components included — sits inside this provider tree, but only
 * the leaf components that actually call wagmi hooks need `"use client"`
 * themselves. Server-rendered HTML is unchanged.
 *
 * QueryClient lives in useState so it's created once per mount (not per
 * render). staleTime: 10s matches our on-chain read cadence; retry: 1
 * because wallet reads that fail twice usually fail for a reason
 * (rate-limit, disconnect) and silent retry storms hide bugs.
 */
import { useState, type ReactNode } from "react";
import { WagmiProvider } from "wagmi";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { wagmiConfig } from "@/lib/wagmi-config";

export function Providers({ children }: { children: ReactNode }) {
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: { staleTime: 10_000, retry: 1 },
        },
      }),
  );

  return (
    <WagmiProvider config={wagmiConfig}>
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    </WagmiProvider>
  );
}
