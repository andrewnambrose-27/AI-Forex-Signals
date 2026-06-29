import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "AI Forex Signals",
  description: "Private forex signal dashboard"
};

export default function RootLayout({
  children
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
