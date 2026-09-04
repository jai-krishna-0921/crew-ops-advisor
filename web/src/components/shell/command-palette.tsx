"use client";

/**
 * Command palette, cmd-K or ctrl-K.
 *
 * Three sources in one list: the sample questions, the open threads, and the
 * console sections. A controller under pressure types four characters and
 * presses enter; they should not have to know which of the three they wanted.
 */

import { useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import {
  ArrowRightIcon,
  ChatCircleDotsIcon,
  CompassIcon,
  QuestionIcon,
} from "@phosphor-icons/react/dist/ssr";

import type { SampleQuestion, ThreadSummary } from "@/lib/contracts";
import { Kbd, ModifierKey } from "@/components/ui/primitives";
import { cx, TIER_CHIP } from "@/components/ui/tone";

type Entry =
  | { kind: "question"; id: string; label: string; tier: number; topic?: string | null }
  | { kind: "thread"; id: string; label: string; meta: string }
  | { kind: "section"; id: string; label: string; href: string };

const SECTIONS: Entry[] = [
  { kind: "section", id: "s-advisor", label: "Advisor", href: "/" },
  { kind: "section", id: "s-brief", label: "Morning brief", href: "/brief" },
  { kind: "section", id: "s-ops", label: "Operations, deterministic panels", href: "/ops" },
  { kind: "section", id: "s-arch", label: "Architecture, the boundary", href: "/architecture" },
];

export function useCommandPalette() {
  const [open, setOpen] = useState(false);
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setOpen((value) => !value);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);
  return { open, setOpen };
}

/**
 * The palette unmounts when closed rather than hiding. That is what keeps the
 * query and the cursor fresh on each open without an effect resetting them,
 * and it keeps the dialog out of the accessibility tree while it is shut.
 */
export function CommandPalette(props: {
  open: boolean;
  onClose: () => void;
  questions: SampleQuestion[];
  threads: ThreadSummary[];
  onAsk: (question: string) => void;
  onOpenThread: (threadId: string) => void;
}) {
  if (!props.open) return null;
  return <PaletteBody {...props} />;
}

function PaletteBody({
  onClose,
  questions,
  threads,
  onAsk,
  onOpenThread,
}: {
  open: boolean;
  onClose: () => void;
  questions: SampleQuestion[];
  threads: ThreadSummary[];
  onAsk: (question: string) => void;
  onOpenThread: (threadId: string) => void;
}) {
  const router = useRouter();
  const [query, setQuery] = useState("");
  const [rawCursor, setCursor] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLUListElement>(null);

  const entries = useMemo<Entry[]>(() => {
    const all: Entry[] = [
      ...questions.map<Entry>((q) => ({
        kind: "question",
        id: q.id,
        label: q.question,
        tier: q.tier,
        topic: q.topic,
      })),
      ...threads.map<Entry>((t) => ({
        kind: "thread",
        id: t.thread_id,
        label: t.title,
        meta: `${t.turn_count} turns`,
      })),
      ...SECTIONS,
    ];
    const needle = query.trim().toLowerCase();
    if (!needle) return all;
    return all.filter((entry) =>
      `${entry.label} ${"topic" in entry ? (entry.topic ?? "") : ""}`
        .toLowerCase()
        .includes(needle),
    );
  }, [questions, threads, query]);

  // Clamped rather than reset in an effect: a shrinking list must never leave
  // the highlight pointing past the end.
  const cursor = Math.min(rawCursor, Math.max(entries.length - 1, 0));

  // Focus and scroll are external systems, so they belong in effects. State
  // resets do not: the cursor is clamped at render and moved from handlers.
  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  useEffect(() => {
    const node = listRef.current?.children[cursor] as HTMLElement | undefined;
    node?.scrollIntoView({ block: "nearest" });
  }, [cursor]);

  const choose = (entry: Entry) => {
    onClose();
    if (entry.kind === "question") onAsk(entry.label);
    else if (entry.kind === "thread") onOpenThread(entry.id);
    else router.push(entry.href);
  };

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="Command palette"
      className="fixed inset-0 z-50 flex items-start justify-center bg-page/70 px-4 pt-[12vh] backdrop-blur-[2px]"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <div className="anim-fade-up w-full max-w-2xl overflow-hidden rounded-lg bg-surface shadow-[var(--shadow-pop)] hairline-strong">
        <div className="flex items-center gap-2 px-3 py-2.5">
          <CompassIcon size={14} weight="bold" aria-hidden className="text-ink-3" />
          <input
            ref={inputRef}
            value={query}
            onChange={(event) => {
              setQuery(event.target.value);
              setCursor(0);
            }}
            onKeyDown={(event) => {
              if (event.key === "Escape") {
                event.preventDefault();
                onClose();
              } else if (event.key === "ArrowDown") {
                event.preventDefault();
                setCursor((c) => Math.min(c + 1, entries.length - 1));
              } else if (event.key === "ArrowUp") {
                event.preventDefault();
                setCursor((c) => Math.max(c - 1, 0));
              } else if (event.key === "Enter") {
                event.preventDefault();
                const entry = entries[cursor];
                if (entry) choose(entry);
              }
            }}
            placeholder="Ask a sample question, open a thread, or jump to a section"
            aria-label="Search questions, threads and sections"
            className="w-full bg-transparent text-md text-ink outline-none placeholder:text-ink-3"
          />
          <Kbd>Esc</Kbd>
        </div>

        <ul ref={listRef} className="max-h-[52vh] overflow-y-auto py-1">
          {entries.length === 0 ? (
            <li className="px-3 py-6 text-center text-base text-ink-3">
              Nothing matches that. Press escape and type the question instead.
            </li>
          ) : (
            entries.map((entry, index) => (
              <li key={`${entry.kind}-${entry.id}`}>
                <button
                  type="button"
                  onMouseEnter={() => setCursor(index)}
                  onClick={() => choose(entry)}
                  className={cx(
                    "flex w-full items-center gap-2 px-3 py-1.5 text-left text-base transition-colors duration-75",
                    index === cursor ? "bg-hover text-ink" : "text-ink-2",
                  )}
                >
                  <EntryIcon entry={entry} />
                  <span className="min-w-0 flex-1 truncate">{entry.label}</span>
                  {entry.kind === "question" ? (
                    <span
                      className={cx(
                        "shrink-0 rounded-xs px-1 py-px text-2xs font-semibold uppercase",
                        TIER_CHIP[entry.tier],
                      )}
                    >
                      Tier {entry.tier}
                    </span>
                  ) : null}
                  {entry.kind === "thread" ? (
                    <span className="num shrink-0 text-2xs text-ink-3">
                      {entry.meta}
                    </span>
                  ) : null}
                  {index === cursor ? (
                    <ArrowRightIcon
                      size={11}
                      weight="bold"
                      aria-hidden
                      className="shrink-0 text-ink-3"
                    />
                  ) : null}
                </button>
              </li>
            ))
          )}
        </ul>

        <footer className="flex items-center gap-3 px-3 py-1.5 text-2xs text-ink-3">
          <span className="flex items-center gap-1">
            <Kbd>↑</Kbd>
            <Kbd>↓</Kbd> move
          </span>
          <span className="flex items-center gap-1">
            <Kbd>Enter</Kbd> run
          </span>
          <span className="flex items-center gap-1">
            <ModifierKey /> reopens
          </span>
          <span className="ml-auto">
            {entries.length} of {questions.length + threads.length + SECTIONS.length}
          </span>
        </footer>
      </div>
    </div>
  );
}

function EntryIcon({ entry }: { entry: Entry }) {
  const className = "shrink-0 text-ink-3";
  if (entry.kind === "question") {
    return <QuestionIcon size={12} weight="bold" aria-hidden className={className} />;
  }
  if (entry.kind === "thread") {
    return (
      <ChatCircleDotsIcon size={12} weight="bold" aria-hidden className={className} />
    );
  }
  return <CompassIcon size={12} weight="bold" aria-hidden className={className} />;
}
