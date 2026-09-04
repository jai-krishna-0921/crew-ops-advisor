import type { Metadata } from "next";

import { BriefView } from "@/components/brief/brief-view";

export const metadata: Metadata = {
  title: "Morning brief",
  description:
    "The proactive 6 a.m. watchlist: what is about to go wrong, by severity, with the question that investigates it.",
};

export default function BriefPage() {
  return <BriefView />;
}
