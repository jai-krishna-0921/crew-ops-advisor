import type { Metadata } from "next";

import { ArchitectureView } from "@/components/architecture/architecture-view";

export const metadata: Metadata = {
  title: "Architecture",
  description:
    "Where the language model stops and deterministic code starts, drawn as a live diagram rather than a picture.",
};

export default function ArchitecturePage() {
  return <ArchitectureView />;
}
