"use client";

/**
 * The left rail: threads, and a demo launcher over the sample question bank.
 *
 * The launcher exists because a judge has a few minutes and should be able to
 * fire a Tier 1, a Tier 2 and a Tier 3 question without typing. Filtering by
 * tier is the whole interaction, so it is a segmented control at the top
 * rather than a menu.
 */

import { useMemo, useState } from "react";
import { PlusIcon } from "@phosphor-icons/react/dist/ssr";

import type { SampleQuestion, ThreadSummary } from "@/lib/contracts";
import { shortDate } from "@/lib/format";
import { Eyebrow, Segmented } from "@/components/ui/primitives";
import { cx, TIER_CHIP } from "@/components/ui/tone";

type TierFilter = "all" | "1" | "2" | "3";

export function SideRail({
  threads,
  activeThreadId,
  questions,
  onNewThread,
  onOpenThread,
  onAsk,
}: {
  threads: ThreadSummary[];
  activeThreadId: string | null;
  questions: SampleQuestion[];
  onNewThread: () => void;
  onOpenThread: (threadId: string) => void;
  onAsk: (question: string) => void;
}) {
  const [tier, setTier] = useState<TierFilter>("all");

  const counts = useMemo(() => {
    const by = { 1: 0, 2: 0, 3: 0 } as Record<1 | 2 | 3, number>;
    for (const question of questions) by[question.tier] += 1;
    return by;
  }, [questions]);

  const visible = useMemo(
    () =>
      tier === "all"
        ? questions
        : questions.filter((question) => String(question.tier) === tier),
    [questions, tier],
  );

  return (
    <div className="flex h-full min-h-0 flex-col bg-canvas">
      <div className="flex items-center gap-2 border-b border-line px-3 py-2">
        <h2 className="text-base font-semibold text-ink">Threads</h2>
        <button
          type="button"
          onClick={onNewThread}
          className="ml-auto inline-flex items-center gap-1 rounded-sm bg-inset px-1.5 py-1 text-xs text-ink-2 ring-1 ring-line transition-colors duration-100 hover:bg-hover hover:text-ink"
        >
          <PlusIcon size={11} weight="bold" aria-hidden />
          New
        </button>
      </div>

      <ul className="max-h-56 shrink-0 overflow-y-auto border-b border-line">
        {threads.length === 0 ? (
          <li className="px-3 py-3 text-base text-ink-3">
            No saved threads. Memory is per thread and survives a restart.
          </li>
        ) : (
          threads.map((thread) => {
            const active = thread.thread_id === activeThreadId;
            return (
              <li key={thread.thread_id}>
                <button
                  type="button"
                  onClick={() => onOpenThread(thread.thread_id)}
                  aria-current={active ? "true" : undefined}
                  className={cx(
                    "w-full px-3 py-2 text-left transition-colors duration-100",
                    active ? "bg-accent-tint" : "hover:bg-hover",
                  )}
                >
                  <span className="flex items-center gap-1.5">
                    <span className="min-w-0 flex-1 truncate text-base text-ink">
                      {thread.title}
                    </span>
                    {thread.tier ? (
                      <span
                        className={cx(
                          "shrink-0 rounded-xs px-1 text-2xs font-semibold uppercase",
                          TIER_CHIP[thread.tier],
                        )}
                      >
                        T{thread.tier}
                      </span>
                    ) : null}
                  </span>
                  <span className="num mt-0.5 block text-2xs text-ink-3">
                    {shortDate(thread.updated_at)} · {thread.turn_count} turns
                  </span>
                </button>
              </li>
            );
          })
        )}
      </ul>

      <div className="border-b border-line px-3 py-2">
        <Eyebrow>Sample questions</Eyebrow>
        <div className="mt-1.5">
          <Segmented
            label="Filter by tier"
            value={tier}
            onChange={setTier}
            options={[
              { value: "all", label: "All", count: questions.length },
              { value: "1", label: "T1", count: counts[1] },
              { value: "2", label: "T2", count: counts[2] },
              { value: "3", label: "T3", count: counts[3] },
            ]}
          />
        </div>
      </div>

      <ul className="min-h-0 flex-1 overflow-y-auto">
        {visible.map((question) => (
          <li key={question.id}>
            <button
              type="button"
              onClick={() => onAsk(question.question)}
              className="w-full px-3 py-2 text-left transition-colors duration-100 hover:bg-hover"
            >
              <span className="flex items-start gap-1.5">
                <span
                  className={cx(
                    "num mt-px shrink-0 rounded-xs px-1 text-2xs font-semibold",
                    TIER_CHIP[question.tier],
                  )}
                >
                  T{question.tier}
                </span>
                <span className="min-w-0 flex-1 text-base leading-snug text-ink-2">
                  {question.question}
                </span>
              </span>
              {question.topic ? (
                <span className="label-micro mt-1 block pl-6">{question.topic}</span>
              ) : null}
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
