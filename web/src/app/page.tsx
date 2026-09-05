import type { Metadata } from "next";
import { redirect } from "next/navigation";

import { Landing } from "@/components/landing/landing";

export const metadata: Metadata = {
  title: "Crew Ops Advisor",
  description:
    "A crew desk advisor that never guesses. The model plans and explains, deterministic code computes, and a guard checks every figure in the answer against what the tools returned.",
};

/**
 * The landing page, and the forwarder for every link that used to point here.
 *
 * The advisor lived at `/` until this page took the route, and a good deal of
 * this repository points at `/?q=...`: the brief's suggested questions, the
 * command palette, the demo links in the README, and anything anybody has
 * already shared. Forwarding on the server means those arrive at the console
 * with the question intact and never render the landing first, so there is no
 * flash of the wrong page on the way through.
 */
export default async function Page({
  searchParams,
}: {
  searchParams: Promise<{ [key: string]: string | string[] | undefined }>;
}) {
  const params = await searchParams;
  const one = (value: string | string[] | undefined) =>
    typeof value === "string" && value.length > 0 ? value : null;

  const question = one(params.q);
  if (question) redirect(`/ask?q=${encodeURIComponent(question)}`);

  const thread = one(params.thread);
  if (thread) redirect(`/ask?thread=${encodeURIComponent(thread)}`);

  return <Landing />;
}
