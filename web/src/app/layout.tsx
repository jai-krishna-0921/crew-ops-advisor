import type { Metadata, Viewport } from "next";
import localFont from "next/font/local";
import { IBM_Plex_Mono } from "next/font/google";

import "./globals.css";
import { AppShell } from "@/components/shell/app-shell";

/**
 * Cabinet Grotesk for display, Satoshi for text, IBM Plex Mono for machine
 * strings.
 *
 * THE PREVIOUS FOUR ATTEMPTS, AND WHY THIS ONE IS DIFFERENT. It began as two
 * grotesques of near identical width and skeleton (Bricolage over Plus
 * Jakarta), which the eye reads as one face rendering inconsistently rather
 * than as a pairing. Then a serif, which is a real pairing and the wrong
 * product: an editorial voice on a page whose job is to be correct at six in
 * the morning. Then Public Sans, then Figtree, both of which are competent
 * and neither of which has a point of view. Every one of those was a Google
 * Fonts default, and that is the actual failure: the shortlist was "what is
 * one import away", not "what should this look like".
 *
 * Cabinet Grotesk is a display grotesque with real character in the
 * terminals and a tight, confident set at 800. Satoshi is its sibling in
 * spirit and unrelated in shape: a neo-grotesque with a tall x-height and
 * genuinely open counters, so it survives 13px in a dense table and still
 * reads warm in a paragraph. Together they are a pairing, because they differ
 * in the way two faces have to differ to look chosen.
 *
 * THEY ARE SERVED FROM THIS REPOSITORY, not from a CDN. `next/font/local`
 * self-hosts, inlines the face declarations and reserves metrics, so there is
 * no third-party request, no flash of fallback text, and the whole product
 * still runs with no network. That last part is not a preference: offline
 * first is a rule this project is held to, and a typeface fetched at runtime
 * would break it for the sake of a shorter file.
 *
 * IBM Plex Mono appears ONLY where the reader is looking at a string a machine
 * will read: a tool identifier, a payload, a rule's arithmetic. It used to
 * carry every crew id, clock time and figure, which is several hundred sites,
 * and at that count a monospace stops being a register change and becomes the
 * voice: the surface reads as a terminal printing a report rather than an
 * interface presenting one. Column alignment was the real requirement behind
 * most of those, and `tabular-nums` is the direct way to get it.
 */
const display = localFont({
  variable: "--font-app-display",
  display: "swap",
  src: [
    { path: "./fonts/CabinetGrotesk-500.woff2", weight: "500", style: "normal" },
    { path: "./fonts/CabinetGrotesk-700.woff2", weight: "700", style: "normal" },
    { path: "./fonts/CabinetGrotesk-800.woff2", weight: "800", style: "normal" },
  ],
});

const sans = localFont({
  variable: "--font-app-sans",
  display: "swap",
  src: [
    { path: "./fonts/Satoshi-400.woff2", weight: "400", style: "normal" },
    { path: "./fonts/Satoshi-500.woff2", weight: "500", style: "normal" },
    { path: "./fonts/Satoshi-700.woff2", weight: "700", style: "normal" },
  ],
});

const mono = IBM_Plex_Mono({
  variable: "--font-app-mono",
  subsets: ["latin"],
  weight: ["400", "500", "600"],
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
  themeColor: "#faf8f3",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body
        className={`${display.variable} ${sans.variable} ${mono.variable}`}
      >
        <AppShell>{children}</AppShell>
      </body>
    </html>
  );
}
