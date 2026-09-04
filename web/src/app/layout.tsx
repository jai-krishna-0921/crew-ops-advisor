import type { Metadata, Viewport } from "next";
import localFont from "next/font/local";
import { IBM_Plex_Mono } from "next/font/google";

import "./globals.css";
import { AppShell } from "@/components/shell/app-shell";

/**
 * Clash Grotesk for display, Cabinet Grotesk for text, IBM Plex Mono for
 * machine strings.
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
 * Clash Grotesk is a display face and behaves like one: flat terminals, a
 * narrow set, and real presence at 700 where a headline has to land in one
 * glance. Cabinet Grotesk carries the text, and it is the right partner
 * because it is a different problem solved by the same hand: a tall x-height
 * and open counters that survive 13px in a dense table, with enough warmth in
 * the round shapes that a page of it does not read as a form. They differ the
 * way two faces have to differ to look chosen rather than defaulted to.
 *
 * BOTH ARE VARIABLE, ONE FILE EACH. A variable face carries its whole weight
 * range in a single request, so the three static cuts this used to load are
 * now one, and the weights in between are available for free if a heading
 * ever wants 620.
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
  src: "./fonts/ClashGrotesk-Variable.woff2",
  weight: "200 700",
});

const sans = localFont({
  variable: "--font-app-sans",
  display: "swap",
  src: "./fonts/CabinetGrotesk-Variable.woff2",
  weight: "100 900",
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
    /*
     * THE FONT VARIABLES GO ON `<html>`, NOT ON `<body>`, and this was the
     * whole reason four typefaces in a row "did not change anything".
     *
     * `next/font` puts `--font-app-sans` and friends on whatever element
     * carries `.variable`. They were on `<body>`. `globals.css` then builds
     * `--font-display` and `--font-sans` from them on `:root`, which is
     * `<html>`, the PARENT. Custom properties inherit downward and never up,
     * so at `:root` the reference was to an undefined variable, the whole
     * declaration became invalid at computed-value time, and both tokens
     * resolved to the empty string. `body { font-family: var(--font-sans) }`
     * then fell through to the browser's default stack.
     *
     * Nothing errored and the woff2 files were requested and served, which is
     * exactly what made it survive four attempts: every check confirmed the
     * font had been DELIVERED, and none of them confirmed it was being USED.
     * The check that finds this is `getComputedStyle(document.body).fontFamily`.
     */
    <html
      lang="en"
      className={`${display.variable} ${sans.variable} ${mono.variable}`}
    >
      <body>
        <AppShell>{children}</AppShell>
      </body>
    </html>
  );
}
