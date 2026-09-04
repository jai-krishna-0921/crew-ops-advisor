"use client";

/**
 * The conversations rail.
 *
 * GROUPED BY DAY. A flat list of forty rows is a list you scroll rather than
 * one you scan, and "the one from this morning" is how anybody actually looks
 * for a conversation. Today, Yesterday, then the week, then everything older.
 *
 * ONE LINE PER THREAD, AND THE LINE IS THE NAME. It carried a second line with
 * the turn count and a relative time, which is three facts per row on a list
 * whose only job is "get me back to the one I was reading". Both are on hover.
 *
 * THE NAME COMES FROM THE ANSWER, NOT THE QUESTION. Listing by first question
 * meant six rows that all began "Captain C-1042 is out for pairing P-2291
 * (15-16 Sep). Produce ranked..." and truncated identically. The server names
 * a thread from its first answer's headline, and anybody can type over it.
 *
 * The menu and both confirmations are Radix. The hand-rolled versions cost
 * three bugs: a menu trapped in its own animation's stacking context, an
 * invisible backdrop that ate the clicks meant for it, and a field that
 * focused inside the click that opened it and lost the caret on the way out.
 */

import { useEffect, useMemo, useRef, useState } from "react";
import {
  CheckIcon,
  DotsThreeIcon,
  PencilSimpleIcon,
  PlusIcon,
  SidebarSimpleIcon,
  TrashIcon,
} from "@phosphor-icons/react/dist/ssr";

import type { ThreadSummary } from "@/lib/contracts";
import { ago, plural, shortDate } from "@/lib/format";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { cx } from "@/components/ui/tone";

/**
 * Which day bucket a timestamp falls in.
 *
 * Compared on local calendar days rather than on elapsed hours, because
 * "yesterday" means the previous date, not twenty-five hours ago. A
 * conversation from 11pm is still yesterday's at 1am.
 */
function bucketOf(iso: string): { key: string; label: string } {
  const then = new Date(iso.endsWith("Z") || /[+-]\d{2}:?\d{2}$/.test(iso) ? iso : `${iso}Z`);
  if (Number.isNaN(then.getTime())) return { key: "older", label: "Earlier" };

  const startOfToday = new Date();
  startOfToday.setHours(0, 0, 0, 0);
  const days = Math.floor((startOfToday.getTime() - then.getTime()) / 86_400_000) + 1;

  if (days <= 1) return { key: "today", label: "Today" };
  if (days === 2) return { key: "yesterday", label: "Yesterday" };
  if (days <= 7) return { key: "week", label: "Previous 7 days" };
  if (days <= 30) return { key: "month", label: "Previous 30 days" };
  return { key: "older", label: "Earlier" };
}

export function SideRail({
  threads,
  activeThreadId,
  onNewThread,
  onOpenThread,
  onCollapse,
  onRename,
  onDelete,
  onDeleteAll,
}: {
  threads: ThreadSummary[];
  activeThreadId: string | null;
  onNewThread: () => void;
  onOpenThread: (threadId: string) => void;
  onCollapse?: () => void;
  onRename?: (threadId: string, title: string) => void;
  onDelete?: (threadId: string) => void;
  onDeleteAll?: () => void;
}) {
  const [editing, setEditing] = useState<string | null>(null);
  const [confirming, setConfirming] = useState<ThreadSummary | null>(null);
  const [confirmingAll, setConfirmingAll] = useState(false);

  // The server already orders by most recent, so the buckets come out in
  // order without a second sort.
  const groups = useMemo(() => {
    const out: { key: string; label: string; rows: ThreadSummary[] }[] = [];
    for (const thread of threads) {
      const bucket = bucketOf(thread.updated_at);
      const last = out.at(-1);
      if (last?.key === bucket.key) last.rows.push(thread);
      else out.push({ ...bucket, rows: [thread] });
    }
    return out;
  }, [threads]);

  return (
    <div className="flex h-full min-h-0 w-full flex-col">
      <div className="flex items-center gap-1 px-3 pt-3 pb-1">
        <p className="label-micro flex-1 pl-1">Conversations</p>
        {onDeleteAll && threads.length > 0 ? (
          <button
            type="button"
            onClick={() => setConfirmingAll(true)}
            aria-label="Delete every conversation"
            title="Delete every conversation"
            className="inline-flex size-8 cursor-pointer items-center justify-center rounded-sm text-ink-3 hover:bg-hover hover:text-breach"
          >
            <TrashIcon size={17} weight="bold" aria-hidden />
          </button>
        ) : null}
        {onCollapse ? (
          <button
            type="button"
            onClick={onCollapse}
            aria-label="Hide conversations"
            title="Hide conversations"
            className="inline-flex size-8 cursor-pointer items-center justify-center rounded-sm text-ink-3 hover:bg-hover hover:text-ink"
          >
            <SidebarSimpleIcon size={18} weight="bold" aria-hidden />
          </button>
        ) : null}
      </div>

      <button
        type="button"
        onClick={onNewThread}
        className="mx-2 flex cursor-pointer items-center gap-2 rounded-sm px-2 py-2 text-base font-medium text-ink hover:bg-hover"
      >
        <PlusIcon size={14} weight="bold" aria-hidden className="text-ink-3" />
        New conversation
      </button>

      <div className="mt-1.5 min-h-0 flex-1 overflow-y-auto px-2 pb-4 [scrollbar-width:none]">
        {threads.length === 0 ? (
          <p className="px-2 py-3 text-base leading-snug text-ink-3">
            Nothing yet. Each conversation keeps its own memory of the crew and
            pairings it is about.
          </p>
        ) : (
          groups.map((group) => (
            <section key={group.key} className="mb-1">
              <p className="label-micro px-2 pt-3 pb-1">{group.label}</p>
              <ul>
                {group.rows.map((thread, index) => (
                  <li
                    key={thread.thread_id}
                    className="anim-stagger"
                    style={{ "--i": Math.min(index, 10) } as React.CSSProperties}
                  >
                    {editing === thread.thread_id ? (
                      <RenameField
                        initial={thread.title}
                        onCancel={() => setEditing(null)}
                        onCommit={(title) => {
                          setEditing(null);
                          if (title !== thread.title) {
                            onRename?.(thread.thread_id, title);
                          }
                        }}
                      />
                    ) : (
                      <Row
                        thread={thread}
                        active={thread.thread_id === activeThreadId}
                        onOpen={() => onOpenThread(thread.thread_id)}
                        onRename={
                          onRename ? () => setEditing(thread.thread_id) : undefined
                        }
                        onDelete={onDelete ? () => setConfirming(thread) : undefined}
                      />
                    )}
                  </li>
                ))}
              </ul>
            </section>
          ))
        )}
      </div>

      <AlertDialog
        open={confirming !== null}
        onOpenChange={(open) => {
          if (!open) setConfirming(null);
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete this conversation?</AlertDialogTitle>
            <AlertDialogDescription>
              {confirming ? `"${confirming.title}"` : ""} and every answer
              recorded on it will be removed. This is an audit trail, and it
              cannot be brought back.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Keep it</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => {
                if (confirming) onDelete?.(confirming.thread_id);
                setConfirming(null);
              }}
            >
              Delete
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <AlertDialog open={confirmingAll} onOpenChange={setConfirmingAll}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete every conversation?</AlertDialogTitle>
            <AlertDialogDescription>
              All {threads.length} conversations and every answer recorded on
              them will be removed. This is the whole audit trail, and it cannot
              be brought back.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Keep them</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => {
                onDeleteAll?.();
                setConfirmingAll(false);
              }}
            >
              Delete all
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}

function Row({
  thread,
  active,
  onOpen,
  onRename,
  onDelete,
}: {
  thread: ThreadSummary;
  active: boolean;
  onOpen: () => void;
  onRename?: () => void;
  onDelete?: () => void;
}) {
  return (
    <div
      className={cx(
        "group relative flex items-center rounded-sm transition-colors duration-150",
        active ? "bg-hover-2" : "hover:bg-hover",
      )}
    >
      <button
        type="button"
        onClick={onOpen}
        aria-current={active ? "true" : undefined}
        title={`${plural(thread.turn_count, "turn")}, ${ago(thread.updated_at)}, ${shortDate(thread.updated_at)}`}
        className={cx(
          "min-w-0 flex-1 cursor-pointer truncate px-2 py-1.5 text-left text-base",
          active ? "font-medium text-ink" : "text-ink-2 group-hover:text-ink",
        )}
      >
        {thread.title}
      </button>

      {onRename || onDelete ? (
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <button
              type="button"
              aria-label={`Actions for ${thread.title}`}
              className={cx(
                "mr-1 inline-flex size-6 shrink-0 cursor-pointer items-center justify-center rounded-xs text-ink-3",
                "hover:bg-hover-2 hover:text-ink",
                // Hidden until the row is hovered, so a list of twelve is
                // twelve names rather than twelve names and twelve buttons.
                // It stays reachable by keyboard, and Radix keeps it visible
                // while its own menu is open.
                "opacity-0 group-hover:opacity-100 focus-visible:opacity-100 data-[state=open]:opacity-100",
              )}
            >
              <DotsThreeIcon size={16} weight="bold" aria-hidden />
            </button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            {onRename ? (
              <DropdownMenuItem onSelect={onRename}>
                <PencilSimpleIcon size={13} weight="bold" aria-hidden />
                Rename
              </DropdownMenuItem>
            ) : null}
            {onDelete ? (
              <DropdownMenuItem tone="breach" onSelect={onDelete}>
                <TrashIcon size={13} weight="bold" aria-hidden />
                Delete
              </DropdownMenuItem>
            ) : null}
          </DropdownMenuContent>
        </DropdownMenu>
      ) : null}
    </div>
  );
}

function RenameField({
  initial,
  onCommit,
  onCancel,
}: {
  initial: string;
  onCommit: (title: string) => void;
  onCancel: () => void;
}) {
  const [value, setValue] = useState(initial);
  const input = useRef<HTMLInputElement>(null);

  useEffect(() => {
    /*
     * FOCUS AFTER THE INTERACTION THAT OPENED THIS HAS FINISHED.
     *
     * Focusing synchronously in this effect put the caret in the input and
     * then the browser finished handling the click that mounted it, moving
     * focus off the element it had just unmounted and taking the caret with
     * it. The field sat there looking editable and silently discarding every
     * keystroke, so "Rename" opened a box you could not type in. A zero
     * timeout runs after that has resolved, so this focus is the last word.
     */
    const id = window.setTimeout(() => {
      input.current?.focus();
      input.current?.select();
    }, 0);
    return () => window.clearTimeout(id);
  }, []);

  const commit = () => {
    const tidy = value.trim();
    // An empty name is a rejected rename, not a nameless conversation.
    if (tidy) onCommit(tidy);
    else onCancel();
  };

  return (
    <div className="flex items-center gap-1 rounded-sm bg-surface px-1 py-0.5 flat">
      <input
        ref={input}
        value={value}
        onChange={(event) => setValue(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === "Enter") commit();
          if (event.key === "Escape") onCancel();
        }}
        aria-label="Conversation name"
        maxLength={200}
        className="min-w-0 flex-1 bg-transparent px-1.5 py-1 text-base text-ink focus:outline-none"
      />
      <button
        type="button"
        onClick={commit}
        aria-label="Save name"
        className="inline-flex size-6 shrink-0 cursor-pointer items-center justify-center rounded-xs text-ink-3 hover:text-ink"
      >
        <CheckIcon size={13} weight="bold" aria-hidden />
      </button>
    </div>
  );
}
