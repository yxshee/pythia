import { ImageResponse } from "next/og";

export const alt = "Agora Alpha — auditable AI reasoning, paid in USDC on Arc";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

export default function Image() {
  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          background: "#f5f1e7",
          display: "flex",
          flexDirection: "column",
          justifyContent: "space-between",
          padding: "72px 88px",
          color: "#1c1a16",
          fontFamily: "Georgia, 'Times New Roman', serif",
        }}
      >
        <div
          style={{
            display: "flex",
            alignItems: "baseline",
            justifyContent: "space-between",
            fontSize: 18,
            letterSpacing: 6,
            textTransform: "uppercase",
            color: "#6b6457",
          }}
        >
          <span>Agora · Alpha</span>
          <span>USDC · Arc testnet</span>
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: 28 }}>
          <div
            style={{
              fontSize: 84,
              fontWeight: 300,
              lineHeight: 1.02,
              letterSpacing: -1.4,
              maxWidth: 1000,
              display: "flex",
            }}
          >
            Auditable AI reasoning,
            <br />
            paid in USDC on Arc.
          </div>
          <div
            style={{
              fontSize: 26,
              color: "#3b3833",
              lineHeight: 1.35,
              maxWidth: 900,
              display: "flex",
            }}
          >
            An autonomous prediction-market analyst that publishes paid,
            on-chain-verifiable market calls.
          </div>
        </div>

        <div
          style={{
            display: "flex",
            alignItems: "baseline",
            justifyContent: "space-between",
            fontSize: 18,
            letterSpacing: 4,
            textTransform: "uppercase",
            color: "#6b6457",
          }}
        >
          <span>Built for the Agora Agents Hackathon · Canteen × Circle × Arc</span>
          <span>agoraalpha.vercel.app</span>
        </div>
      </div>
    ),
    { ...size },
  );
}
