"use client";

/**
 * The console shell: header, command palette, and the page beneath.
 *
 * The palette lives here rather than on the Advisor page so cmd-K works from
 * the brief, the operations panels and the architecture page too. Asking a
 * question from anywhere routes back to the Advisor with the question in the
 * URL, which also makes every demo question a shareable link.
 */

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import type { SampleQuestion, ThreadSummary } from "@/lib/contracts";
import { api } from "@/lib/api";
import {
  CommandPalette,
  useCommandPalette,
} from "@/components/shell/command-palette";
import { TopBar } from "@/components/shell/top-bar";

export function AppShell({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const { open, setOpen } = useCommandPalette();
  const [questions, setQuestions] = useState<SampleQuestion[]>([]);
  const [threads, setThreads] = useState<ThreadSummary[]>([]);

  useEffect(() => {
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
  }, []);

  const ask = useCallback(
    (question: string) => {
      router.push(`/?q=${encodeURIComponent(question)}`);
    },
    [router],
  );

  const openThread = useCallback(
    (threadId: string) => {
      router.push(`/?thread=${encodeURIComponent(threadId)}`);
    },
    [router],
  );

  return (
    <div className="flex h-dvh flex-col overflow-hidden">
      <TopBar onOpenPalette={() => setOpen(true)} />
      <main className="min-h-0 flex-1 overflow-hidden">{children}</main>
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
