import type { Metadata, Viewport } from "next";
import { Figtree, IBM_Plex_Mono } from "next/font/google";

import "./globals.css";
import { AppShell } from "@/components/shell/app-shell";

/**
 * One family, two roles, and one machine face.
 *
 * This has been wrong three times, in three different directions. It started
 * as two grotesques of almost identical width and skeleton (Bricolage
 * Grotesque over Plus Jakarta Sans), which is not a pairing: at the 13 to 22px
 * this product lives at, the eye reads two near-identical faces as one face
 * rendering inconsistently. The correction was a serif, which IS a real
 * pairing and is also a different product: an editorial voice belongs on
 * something you read for pleasure, not on a page whose job is to be boring and
 * correct at six in the morning. The correction to THAT was Public Sans, which
 * is right about everything except how it feels. It is drawn for government
 * service forms and it reads like one.
 *
 * Figtree is the same argument won properly. A geometric sans with a tall
 * x-height and open apertures, so it holds at 13px where the dense rows live,
 * and with enough warmth in the round shapes that a page of it does not read
 * as a compliance document. One family across five weights, display type being
 * the same face at 800 with the tracking pulled in, so a heading and the
 * paragraph under it share a skeleton and the jump reads as emphasis rather
 * than as a different document. Its figures are tabular, which is what lets
 * the numerals leave the monospace behind.
 *
 * IBM Plex Mono appears ONLY where the reader is looking at a string a machine
 * will read: a tool identifier, a payload, a rule's arithmetic. It used to
 * carry every crew id, clock time, duration and figure, which is several
 * hundred sites, and at that count a monospace stops being a register change
 * and becomes the voice: the whole surface reads as a terminal printing a
 * report rather than an interface presenting one. Column alignment was the
 * real requirement behind most of those, and `tabular-nums` is the direct way
 * to get it.
 */
const sans = Figtree({
  variable: "--font-app-sans",
  subsets: ["latin"],
  weight: ["400", "500", "600", "700", "800"],
  display: "swap",
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
      <body className={`${sans.variable} ${mono.variable}`}>
        <AppShell>{children}</AppShell>
      </body>
    </html>
  );
}
