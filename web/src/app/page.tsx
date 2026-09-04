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
    <div className="flex h-full">
      <div className="hidden w-[17rem] shrink-0 space-y-2 border-r border-line p-3 lg:block">
        <Skeleton className="w-1/2" />
        <Skeleton className="w-full" />
        <Skeleton className="w-4/5" />
      </div>
      <div className="flex-1 space-y-3 p-6">
        <Skeleton className="w-1/3" />
        <Skeleton className="w-2/3" />
        <Skeleton className="w-1/2" />
      </div>
    </div>
  );
}
