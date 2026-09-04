import type { Metadata, Viewport } from "next";
import {
  Bricolage_Grotesque,
  JetBrains_Mono,
  Plus_Jakarta_Sans,
} from "next/font/google";

import "./globals.css";
import { AppShell } from "@/components/shell/app-shell";
import { ThemeScript } from "@/components/shell/theme-script";

/**
 * Three faces, each with a job.
 *
 * Bricolage Grotesque carries headlines. It has enough character to stop the
 * page reading as a default admin theme, and its tight tracking at display
 * sizes suits a headline a controller reads first and fastest.
 *
 * Plus Jakarta Sans carries everything else. It is quiet, wide enough to stay
 * legible at 13 and 14px, and does not fight the display face.
 *
 * JetBrains Mono carries identifiers, clock times, durations and money. Every
 * one of those is a value a controller compares down a column, so they need
 * tabular figures and unambiguous character shapes: a crew id misread as
 * C-3301 instead of C-3310 is a real operational error.
 */
const display = Bricolage_Grotesque({
  variable: "--font-app-display",
  subsets: ["latin"],
  display: "swap",
});

const sans = Plus_Jakarta_Sans({
  variable: "--font-app-sans",
  subsets: ["latin"],
  display: "swap",
});

const mono = JetBrains_Mono({
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
      <body className={`${display.variable} ${sans.variable} ${mono.variable}`}>
        <AppShell>{children}</AppShell>
      </body>
    </html>
  );
}
