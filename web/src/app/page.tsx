import { Suspense } from "react";

import { AdvisorConsole } from "@/components/chat/advisor-console";
import { Skeleton } from "@/components/ui/primitives";

export default function AdvisorPage() {
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
