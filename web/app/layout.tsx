import type { Metadata } from "next";
import { Fraunces, JetBrains_Mono } from "next/font/google";
import "./globals.css";
import { Providers } from "@/components/providers";

const display = Fraunces({
  subsets: ["latin"],
  variable: "--font-display",
  axes: ["SOFT", "WONK", "opsz"],
  display: "swap",
});

const mono = JetBrains_Mono({
  subsets: ["latin"],
  variable: "--font-mono",
  weight: ["400", "500", "700"],
  display: "swap",
});

export const metadata: Metadata = {
  title: "Agora Alpha — auditable AI reasoning, paid in USDC on Arc",
  description:
    "An autonomous prediction-market analyst prototype that publishes paid, on-chain-verifiable market calls. Built for the Agora Agents Hackathon (Canteen x Circle x Arc).",
  metadataBase: new URL("https://agoraalpha.vercel.app"),
  openGraph: {
    title: "Agora Alpha",
    description: "USDC-native marketplace prototype for AI reasoning traces. Settled on Arc.",
    type: "website",
  },
  twitter: {
    card: "summary_large_image",
    title: "Agora Alpha",
    description: "USDC-native marketplace prototype for AI reasoning traces. Settled on Arc.",
  },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${display.variable} ${mono.variable}`}>
      <body className="min-h-screen text-ink">
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
