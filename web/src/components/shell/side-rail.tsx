"use client";

/**
 * The conversations rail.
 *
 * ONE LINE PER THREAD, AND THE LINE IS THE NAME. It carried a second line
 * under every row with the turn count and a relative time, which is three
 * facts per row on a list whose only job is "get me back to the one I was
 * reading". Both are still there on hover, where somebody who wants them can
 * ask.
 *
 * THE NAME COMES FROM THE ANSWER, NOT THE QUESTION. Listing by first question
 * meant six rows that all began "Captain C-1042 is out for pairing P-2291
 * (15-16 Sep). Produce ranked..." and truncated identically. The server names
 * a thread from its first answer's headline instead, which is a line written
 * to be read at a glance, and anybody can type their own over it.
 *
 * Renaming happens in place. A dialog for one short string is a modal to type
 * six words into, and the row already knows how wide it is.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import {
  CheckIcon,
  DotsThreeIcon,
  PencilSimpleIcon,
  PlusIcon,
  SidebarSimpleIcon,
  TrashIcon,
  XIcon,
} from "@phosphor-icons/react/dist/ssr";

import type { ThreadSummary } from "@/lib/contracts";
import { ago, plural } from "@/lib/format";
import { cx } from "@/components/ui/tone";

export function SideRail({
  threads,
  activeThreadId,
  onNewThread,
  onOpenThread,
  onCollapse,
  onRename,
  onDelete,
}: {
  threads: ThreadSummary[];
  activeThreadId: string | null;
  onNewThread: () => void;
  onOpenThread: (threadId: string) => void;
  onCollapse?: () => void;
  onRename?: (threadId: string, title: string) => void;
  onDelete?: (threadId: string) => void;
}) {
  const [editing, setEditing] = useState<string | null>(null);
  const [confirming, setConfirming] = useState<string | null>(null);
  // Lifted out of the row, for two reasons. Only one menu should be open at a
  // time, and the ROW has to know, because the list item is what needs to be
  // raised above its siblings while the menu is open. See the z-index below.
  const [menuFor, setMenuFor] = useState<string | null>(null);

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
          threads.map((thread, index) => (
            <li
              key={thread.thread_id}
              // `anim-stagger` animates transform and opacity, which gives
              // every row its own stacking context. A menu absolutely
              // positioned inside one is therefore trapped in it, and the
              // rows below, being later siblings, painted straight over it:
              // the menu was visible and the top item was not clickable,
              // because the next row was in front of it. Raising the row
              // itself while its menu is open is the fix, and it has to
              // happen here because the row does not own the list item.
              className={cx(
                "anim-stagger",
                menuFor === thread.thread_id && "relative z-40",
              )}
              style={{ "--i": Math.min(index, 12) } as React.CSSProperties}
            >
              {editing === thread.thread_id ? (
                <RenameField
                  initial={thread.title}
                  onCancel={() => setEditing(null)}
                  onCommit={(title) => {
                    setEditing(null);
                    if (title !== thread.title) onRename?.(thread.thread_id, title);
                  }}
                />
              ) : confirming === thread.thread_id ? (
                <ConfirmDelete
                  onCancel={() => setConfirming(null)}
                  onConfirm={() => {
                    setConfirming(null);
                    onDelete?.(thread.thread_id);
                  }}
                />
              ) : (
                <Row
                  thread={thread}
                  active={thread.thread_id === activeThreadId}
                  menuOpen={menuFor === thread.thread_id}
                  onToggleMenu={(open) =>
                    setMenuFor(open ? thread.thread_id : null)
                  }
                  onOpen={() => onOpenThread(thread.thread_id)}
                  onRename={onRename ? () => setEditing(thread.thread_id) : undefined}
                  onDelete={onDelete ? () => setConfirming(thread.thread_id) : undefined}
                />
              )}
            </li>
          ))
        )}
      </ul>
    </div>
  );
}

function Row({
  thread,
  active,
  menuOpen,
  onToggleMenu,
  onOpen,
  onRename,
  onDelete,
}: {
  thread: ThreadSummary;
  active: boolean;
  menuOpen: boolean;
  onToggleMenu: (open: boolean) => void;
  onOpen: () => void;
  onRename?: () => void;
  onDelete?: () => void;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const dismiss = useCallback(() => onToggleMenu(false), [onToggleMenu]);
  useDismiss(menuOpen, ref, dismiss, { escape: true });

  return (
    <div
      ref={ref}
      className={cx(
        "group relative flex items-center rounded-sm",
        active ? "bg-hover-2" : "hover:bg-hover",
      )}
    >
      <button
        type="button"
        onClick={onOpen}
        aria-current={active ? "true" : undefined}
        title={`${plural(thread.turn_count, "turn")}, ${ago(thread.updated_at)}`}
        className={cx(
          "min-w-0 flex-1 truncate px-2 py-1.5 text-left text-base",
          active ? "font-medium text-ink" : "text-ink-2 group-hover:text-ink",
        )}
      >
        {thread.title}
      </button>

      {onRename || onDelete ? (
        <>
          <button
            type="button"
            onClick={() => onToggleMenu(!menuOpen)}
            aria-label={`Actions for ${thread.title}`}
            aria-expanded={menuOpen}
            className={cx(
              "mr-1 inline-flex size-6 shrink-0 items-center justify-center rounded-xs text-ink-3 hover:bg-hover-2 hover:text-ink",
              // Hidden until the row is hovered or the menu is open, so a
              // list of twelve is twelve names rather than twelve names and
              // twelve buttons. It stays reachable by keyboard.
              menuOpen
                ? "opacity-100"
                : "opacity-0 group-hover:opacity-100 focus:opacity-100",
            )}
          >
            <DotsThreeIcon size={16} weight="bold" aria-hidden />
          </button>

          {menuOpen ? (
            <>
              {/* NO INVISIBLE BACKDROP. Dismissal used to be a full-viewport
                  transparent button behind the menu, which is the usual trick
                  and which swallowed the click on the menu item every time:
                  the menu opened, "Rename" did nothing, and the menu closed,
                  so from the outside the feature simply was not there. An
                  outside-click listener has no hit area of its own and cannot
                  come between a pointer and the thing it is aimed at. */}
              <div className="anim-fade-up absolute top-full right-1 z-40 mt-0.5 w-36 overflow-hidden rounded-sm bg-surface py-1 shadow-pop">
                {onRename ? (
                  <MenuItem
                    icon={<PencilSimpleIcon size={13} weight="bold" aria-hidden />}
                    label="Rename"
                    onClick={() => {
                      onToggleMenu(false);
                      onRename();
                    }}
                  />
                ) : null}
                {onDelete ? (
                  <MenuItem
                    icon={<TrashIcon size={13} weight="bold" aria-hidden />}
                    label="Delete"
                    tone="breach"
                    onClick={() => {
                      onToggleMenu(false);
                      onDelete();
                    }}
                  />
                ) : null}
              </div>
            </>
          ) : null}
        </>
      ) : null}
    </div>
  );
}

/**
 * Run `onDismiss` when a press lands outside `ref`.
 *
 * `escape` is opt-in because the two callers want opposite things from that
 * key. A menu should close on Escape, which is the same as dismissing it. A
 * rename field should ABANDON on Escape, which is the opposite of the
 * click-away behaviour, so it handles the key itself and this hook stays out
 * of the way.
 */
function useDismiss(
  active: boolean,
  ref: React.RefObject<HTMLElement | null>,
  onDismiss: () => void,
  { escape = false }: { escape?: boolean } = {},
) {
  useEffect(() => {
    if (!active) return;
    const onPointer = (event: PointerEvent) => {
      const node = ref.current;
      if (node && !node.contains(event.target as Node)) onDismiss();
    };
    // `pointerdown` rather than `click`, so a press that starts outside
    // resolves before the click lands anywhere unexpected.
    document.addEventListener("pointerdown", onPointer);
    if (!escape) {
      return () => document.removeEventListener("pointerdown", onPointer);
    }
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onDismiss();
    };
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("pointerdown", onPointer);
      document.removeEventListener("keydown", onKey);
    };
  }, [active, ref, onDismiss, escape]);
}

function MenuItem({
  icon,
  label,
  onClick,
  tone,
}: {
  icon: React.ReactNode;
  label: string;
  onClick: () => void;
  tone?: "breach";
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cx(
        "flex w-full items-center gap-2 px-2.5 py-1.5 text-left text-base",
        tone === "breach"
          ? "text-breach hover:bg-breach-wash"
          : "text-ink-2 hover:bg-hover hover:text-ink",
      )}
    >
      {icon}
      {label}
    </button>
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
  const box = useRef<HTMLDivElement>(null);

  useEffect(() => {
    /*
     * FOCUS AFTER THE CLICK THAT OPENED THIS HAS FINISHED, not during it.
     *
     * The field mounts from a click on a menu item. Focusing synchronously in
     * this effect puts the caret in the input and then the browser finishes
     * handling that same click, which moves focus off the element it just
     * unmounted and takes the caret with it. The field then sits there
     * looking editable and silently discarding every keystroke, which is
     * exactly what it did: "Rename" opened a box you could not type in.
     *
     * A zero timeout runs after the click has fully resolved, so the focus
     * this sets is the last word. `select()` follows `focus()` because
     * selecting an unfocused field is not reliably a focusing act.
     */
    const id = window.setTimeout(() => {
      input.current?.focus();
      input.current?.select();
    }, 0);
    return () => window.clearTimeout(id);
  }, []);

  const commit = useCallback(() => {
    const tidy = value.trim();
    // An empty name is a rejected rename, not a nameless conversation.
    if (tidy) onCommit(tidy);
    else onCancel();
  }, [value, onCommit, onCancel]);

  /**
   * CLICKING AWAY SAVES, AND IT IS NOT DONE WITH `onBlur`.
   *
   * It was, and the field was unusable. The field mounts from a click on a
   * menu item, so the browser is still resolving focus from that click when
   * the mount happens: the effect focused the input, the click's own focus
   * handling then moved focus off the element it had just unmounted, the
   * input blurred, `onBlur` committed a value nobody had touched, and the
   * field closed in the same frame. From the outside "Rename" simply did
   * nothing. No field, no rename, no error.
   *
   * An outside pointerdown is the same intent expressed in a way that has
   * nothing to do with focus, so it cannot race with the click that opened
   * the field.
   */
  useDismiss(true, box, commit);

  return (
    <div
      ref={box}
      className="flex items-center gap-1 rounded-sm bg-surface px-1 py-0.5 flat"
    >
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
        className="inline-flex size-6 shrink-0 items-center justify-center rounded-xs text-ink-3 hover:text-ink"
      >
        <CheckIcon size={13} weight="bold" aria-hidden />
      </button>
    </div>
  );
}

/**
 * Confirmation, in the row rather than in a dialog.
 *
 * Deleting a conversation removes an audit trail and cannot be undone, so it
 * asks. It asks in place because a modal over the whole page for one row is
 * heavier than the decision, and because the row itself is the clearest
 * possible statement of which conversation is about to go.
 */
function ConfirmDelete({
  onConfirm,
  onCancel,
}: {
  onConfirm: () => void;
  onCancel: () => void;
}) {
  return (
    <div className="flex items-center gap-1 rounded-sm bg-breach-wash px-2 py-1.5">
      <span className="min-w-0 flex-1 text-base text-ink">Delete this?</span>
      <button
        type="button"
        onClick={onConfirm}
        className="rounded-xs px-1.5 py-0.5 text-base font-medium text-breach hover:bg-breach-tint"
      >
        Yes
      </button>
      <button
        type="button"
        onClick={onCancel}
        aria-label="Keep this conversation"
        className="inline-flex size-6 shrink-0 items-center justify-center rounded-xs text-ink-3 hover:text-ink"
      >
        <XIcon size={13} weight="bold" aria-hidden />
      </button>
    </div>
  );
}
