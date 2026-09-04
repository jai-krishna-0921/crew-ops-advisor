import type { Metadata, Viewport } from "next";
import { Geist, Geist_Mono } from "next/font/google";

import "./globals.css";
import { AppShell } from "@/components/shell/app-shell";
import { ThemeScript } from "@/components/shell/theme-script";

const sans = Geist({
  variable: "--font-app-sans",
  subsets: ["latin"],
  display: "swap",
});

const mono = Geist_Mono({
  variable: "--font-app-mono",
  subsets: ["latin"],
  display: "swap",
});

export const metadata: Metadata = {
  title: {
    default: "Crew Ops Advisor",
    template: "%s · Crew Ops Advisor",
  },
  description:
    "Decision aid for the dCortex Air Crew Control desk. The model plans and explains, deterministic tools compute, and a grounding guard checks every figure.",
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#fbfbfc" },
    { media: "(prefers-color-scheme: dark)", color: "#111318" },
  ],
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <ThemeScript />
      </head>
      <body className={`${sans.variable} ${mono.variable}`}>
        <AppShell>{children}</AppShell>
      </body>
    </html>
  );
}
