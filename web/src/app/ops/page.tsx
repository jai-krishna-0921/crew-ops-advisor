import type { Metadata } from "next";

import { OpsView } from "@/components/ops/ops-view";

export const metadata: Metadata = {
  title: "Operations",
  description:
    "The deterministic side of the system: the seven rules as shipped, a legality checker, cover search and disruption simulation. No model is invoked on this page.",
};

export default function OpsPage() {
  return <OpsView />;
}
