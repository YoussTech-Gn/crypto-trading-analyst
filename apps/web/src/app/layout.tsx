import React from "react";

export const metadata = {
  title: "AI Crypto Trading Analyst — Milestone 1 Foundation",
  description:
    "Evidence-driven Binance Spot USDT LONG swing trading analysis & decision-support platform",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body
        style={{
          margin: 0,
          fontFamily: "system-ui, -apple-system, BlinkMacSystemFont, sans-serif",
          backgroundColor: "#0b0f17",
          color: "#e2e8f0",
        }}
      >
        {children}
      </body>
    </html>
  );
}
