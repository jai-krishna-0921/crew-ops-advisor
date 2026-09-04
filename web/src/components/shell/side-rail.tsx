"use client";

/**
 * The conversations rail.
 *
 * ONE LINE PER THREAD, AND THE LINE IS THE TITLE. It carried a second line
 * under every row with the turn count and a relative time, which is three
 * facts per row on a list whose only job is "get me back to the one I was
 * reading". Twelve rows of that is thirty six facts to scan past, and the
 * titles, which are the only thing anybody recognises a conversation by, were
 * the smallest thing on it. Both facts are still there on hover, where
 * somebody who wants them can ask.
 *
 * It is resident rather than summoned, which was a reversal. The argument for
 * hiding it was that a chat which keeps a menu open beside it is a dashboard.
 * That argument is wrong about this particular menu: the thread list is the
 * conversation's own history, not a navigation tree, and every chat surface
 * worth copying keeps it in view for the same reason a browser keeps its tabs
 * in view. Hiding it also made "which conversation am I in" a click away, on a
 * product whose one known bug was answering in the wrong conversation. It can
 * still be collapsed, because a demo sometimes wants the width.
 */

import { PlusIcon, SidebarSimpleIcon } from "@phosphor-icons/react/dist/ssr";

import type { ThreadSummary } from "@/lib/contracts";
import { ago, plural } from "@/lib/format";
import { cx } from "@/components/ui/tone";

export function SideRail({
  threads,
  activeThreadId,
  onNewThread,
  onOpenThread,
  onCollapse,
}: {
  threads: ThreadSummary[];
  activeThreadId: string | null;
  onNewThread: () => void;
  onOpenThread: (threadId: string) => void;
  onCollapse?: () => void;
}) {
  return (
    <div className="flex h-full min-h-0 w-64 flex-col">
      <div className="flex items-center gap-1 px-3 pt-3 pb-1">
        <p className="label-micro flex-1 pl-1">Conversations</p>
        {onCollapse ? (
          <button
            type="button"
            onClick={onCollapse}
            aria-label="Hide conversations"
            title="Hide conversations"
            className="inline-flex size-7 items-center justify-center rounded-sm text-ink-3 hover:bg-hover hover:text-ink"
          >
            <SidebarSimpleIcon size={15} weight="bold" aria-hidden />
          </button>
        ) : null}
      </div>

      <button
        type="button"
        onClick={onNewThread}
        className="mx-2 flex items-center gap-2 rounded-sm px-2 py-2 text-base font-medium text-ink hover:bg-hover"
      >
        <PlusIcon size={14} weight="bold" aria-hidden className="text-ink-3" />
        New conversation
      </button>

      <ul className="mt-1.5 min-h-0 flex-1 overflow-y-auto px-2 pb-4 [scrollbar-width:none]">
        {threads.length === 0 ? (
          <li className="px-2 py-3 text-base leading-snug text-ink-3">
            Nothing yet. Each conversation keeps its own memory of the crew and
            pairings it is about.
          </li>
        ) : (
          threads.map((thread, index) => {
            const active = thread.thread_id === activeThreadId;
            return (
              <li
                key={thread.thread_id}
                className="anim-stagger"
                style={{ "--i": Math.min(index, 12) } as React.CSSProperties}
              >
                <button
                  type="button"
                  onClick={() => onOpenThread(thread.thread_id)}
                  aria-current={active ? "true" : undefined}
                  title={`${plural(thread.turn_count, "turn")}, ${ago(thread.updated_at)}`}
                  className={cx(
                    "block w-full truncate rounded-sm px-2 py-1.5 text-left text-base",
                    active
                      ? "bg-hover-2 font-medium text-ink"
                      : "text-ink-2 hover:bg-hover hover:text-ink",
                  )}
                >
                  {thread.title}
                </button>
              </li>
            );
          })
        )}
      </ul>
    </div>
  );
}
