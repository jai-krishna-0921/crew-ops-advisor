/**
 * The advisor, at `/ask`.
 *
 * It was at `/` until the landing page took that route. Every link that
 * carried a question in the URL still works: `/?q=...` and `/?thread=...`
 * forward to here from the landing, which is what keeps the demo links in the
 * README, the brief and the command palette from going dead.
 */

import type { Metadata } from "next";
import { Suspense } from "react";

import { AdvisorConsole } from "@/components/chat/advisor-console";
import { Skeleton } from "@/components/ui/primitives";

export const metadata: Metadata = {
  title: "Ask",
  description:
    "Ask about crew, flights, pairings, rosters, duty and flight hour limits, certifications, reserve cover or the impact of a disruption.",
};

export default function AskPage() {
  return (
    <Suspense fallback={<ConsoleFallback />}>
      <AdvisorConsole />
    </Suspense>
  );
}

function ConsoleFallback() {
  return (
    <div className="mx-auto w-full max-w-[var(--measure)] space-y-3 px-6 pt-20">
      <Skeleton className="w-1/3" />
      <Skeleton className="w-2/3" />
      <Skeleton className="w-1/2" />
    </div>
  );
}
