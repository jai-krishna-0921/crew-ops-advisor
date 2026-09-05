"use client";

/**
 * The console shell: the page, and a section rail down its right edge.
 *
 * There is no header. A full-width bar cut a horizontal line across every page
 * and made the content under it the second band of a stacked layout, which is
 * what an admin template looks like. Moving the four destinations to a
 * vertical rail costs 56px of a very wide axis instead of 48px of the short
 * one, and gives the conversation the entire height of the window.
 *
 * The palette lives here rather than on the Advisor page so cmd-K works from
 * the brief, the operations panels and the architecture page too. Asking a
 * question from anywhere routes back to the Advisor with the question in the
 * URL, which also makes every demo question a shareable link.
 */

import { useCallback, useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";

import type { SampleQuestion, ThreadSummary } from "@/lib/contracts";
import { api } from "@/lib/api";
import {
  CommandPalette,
  useCommandPalette,
} from "@/components/shell/command-palette";
import { SectionRail } from "@/components/shell/section-rail";

export function AppShell({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const { open, setOpen } = useCommandPalette();

  /**
   * THE LANDING PAGE IS NOT IN THE CONSOLE. It is the page somebody arrives
   * on before they are a user of anything, it carries its own floating
   * navigation, and it scrolls as one document rather than filling a fixed
   * viewport. Wrapping it in the section rail would put a product's chrome
   * around a page whose job is to explain what the product is.
   *
   * A route check rather than a second root layout, because the two would
   * then have to keep the fonts, the palette and the metadata in sync, and
   * the only thing that actually differs is whether the rail is drawn.
   */
  const bare = pathname === "/";
  const [questions, setQuestions] = useState<SampleQuestion[]>([]);
  const [threads, setThreads] = useState<ThreadSummary[]>([]);

  useEffect(() => {
    // THE LANDING PAGE TALKS TO NOTHING. This effect loads what the command
    // palette searches, and the palette is not mounted on `/`, so on the one
    // page a stranger arrives at first it was making two API calls whose
    // results had nowhere to go. Worse, it made the landing page's console
    // depend on the API being up, which is exactly backwards: a page that
    // explains the product should render when the product is not running.
    if (bare) return;

    let cancelled = false;
    Promise.all([api.questions(), api.threads()])
      .then(([q, t]) => {
        if (cancelled) return;
        setQuestions(q);
        setThreads(t);
      })
      .catch(() => {
        // The palette degrades to sections only. The console still works.
      });
    return () => {
      cancelled = true;
    };
  }, [bare]);

  const ask = useCallback(
    (question: string) => {
      router.push(`/ask?q=${encodeURIComponent(question)}`);
    },
    [router],
  );

  const openThread = useCallback(
    (threadId: string) => {
      router.push(`/ask?thread=${encodeURIComponent(threadId)}`);
    },
    [router],
  );

  if (bare) return <>{children}</>;

  return (
    <div className="flex h-dvh overflow-hidden">
      <main className="min-w-0 flex-1 overflow-hidden">{children}</main>
      <SectionRail onOpenPalette={() => setOpen(true)} />
      <CommandPalette
        open={open}
        onClose={() => setOpen(false)}
        questions={questions}
        threads={threads}
        onAsk={ask}
        onOpenThread={openThread}
      />
    </div>
  );
}
