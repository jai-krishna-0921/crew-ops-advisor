"use client";

import { useEffect, useId, useState, type ReactNode } from "react";
import { CaretRightIcon } from "@phosphor-icons/react/dist/ssr";

import type { Tone } from "@/lib/format";
import { cx, TONE } from "@/components/ui/tone";

/* ------------------------------------------------------------------ pill */

export function Pill({
  tone = "na",
  children,
  title,
  className,
}: {
  tone?: Tone;
  children: ReactNode;
  title?: string;
  className?: string;
}) {
  return (
    <span
      title={title}
      className={cx(
        "inline-flex shrink-0 items-center gap-1 rounded-full px-2 py-0.5 text-2xs font-semibold tracking-wider uppercase",
        TONE[tone].chip,
        className,
      )}
    >
      {children}
    </span>
  );
}

/**
 * An identifier: a crew id, a flight number, a pairing, a rule id.
 *
 * THIS USED TO BE A MONOSPACE CHIP with a tinted ground and a ring, and it
 * appears several hundred times across an answer. At that count it was not
 * marking identifiers, it was tiling the page with small grey rectangles, and
 * the monospace made every one of them read as a code sample.
 *
 * What the treatment actually has to do is make `C-3310` read as a token
 * rather than as a word, so it is not skimmed as prose and cannot be misread
 * as `C-3301`. Weight, tabular figures and a hair of tracking do that inside
 * the body face, and the identifier then sits in the sentence it belongs to
 * instead of interrupting it.
 */
export function Token({
  children,
  className,
  title,
}: {
  children: ReactNode;
  className?: string;
  title?: string;
}) {
  return (
    <span title={title} className={cx("ident", className)}>
      {children}
    </span>
  );
}

/** A genuine machine string: a tool name, a payload, a rule's arithmetic. */
export function Mono({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return <span className={cx("mono", className)}>{children}</span>;
}

/* ----------------------------------------------------------------- panel */

export function Panel({
  children,
  className,
  as: Tag = "section",
}: {
  children: ReactNode;
  className?: string;
  as?: "section" | "div" | "article" | "aside";
}) {
  return (
    <Tag className={cx("overflow-hidden rounded-md bg-surface hairline", className)}>
      {children}
    </Tag>
  );
}

/**
 * A panel's heading.
 *
 * No rule under it and no tinted ground behind it. The space below the title
 * separates it from the body perfectly well, and a filled bar with a line
 * under it is the single most reliable way to make a panel look like a
 * table widget from 2011.
 */
export function PanelHead({
  title,
  meta,
  actions,
  icon,
}: {
  title: ReactNode;
  meta?: ReactNode;
  actions?: ReactNode;
  icon?: ReactNode;
}) {
  return (
    <header className="flex items-center gap-2 px-4 pt-3 pb-1.5">
      {icon ? <span className="text-ink-3">{icon}</span> : null}
      <h3 className="text-base font-semibold text-ink">{title}</h3>
      {meta ? <span className="text-xs text-ink-3">{meta}</span> : null}
      {actions ? <div className="ml-auto flex items-center gap-1">{actions}</div> : null}
    </header>
  );
}

/* ------------------------------------------------------------ disclosure */

export function Disclosure({
  summary,
  count,
  children,
  defaultOpen = false,
  tone,
}: {
  summary: ReactNode;
  count?: ReactNode;
  children: ReactNode;
  defaultOpen?: boolean;
  tone?: Tone;
}) {
  const [open, setOpen] = useState(defaultOpen);
  const id = useId();
  return (
    <div>
      <button
        type="button"
        aria-expanded={open}
        aria-controls={id}
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center gap-1.5 rounded-sm px-2 py-1.5 text-left text-base text-ink-2 hover:bg-hover hover:text-ink"
      >
        <CaretRightIcon
          size={12}
          weight="bold"
          aria-hidden
          className={cx(
            "shrink-0 transition-transform duration-200 ease-out-quint",
            open && "rotate-90",
          )}
        />
        <span className="font-medium">{summary}</span>
        {count !== undefined ? (
          <span
            className={cx(
              "num ml-1 rounded-full px-1.5 text-2xs font-semibold",
              tone ? TONE[tone].chip : "bg-na-tint text-ink-3",
            )}
          >
            {count}
          </span>
        ) : null}
      </button>
      <div id={id} hidden={!open} className="anim-fade-up pt-1">
        {children}
      </div>
    </div>
  );
}

/* ------------------------------------------------------------- segmented */

export function Segmented<T extends string>({
  options,
  value,
  onChange,
  label,
}: {
  options: { value: T; label: string; count?: number }[];
  value: T;
  onChange: (value: T) => void;
  label: string;
}) {
  return (
    <div
      role="tablist"
      aria-label={label}
      className="inline-flex items-center gap-0.5 rounded-full bg-inset p-0.5"
    >
      {options.map((option) => {
        const active = option.value === value;
        return (
          <button
            key={option.value}
            role="tab"
            aria-selected={active}
            type="button"
            onClick={() => onChange(option.value)}
            className={cx(
              "rounded-full px-2.5 py-1 text-xs font-medium",
              active ? "bg-surface text-ink hairline" : "text-ink-3 hover:text-ink-2",
            )}
          >
            {option.label}
            {option.count !== undefined ? (
              <span className="num ml-1 text-2xs text-ink-3">{option.count}</span>
            ) : null}
          </button>
        );
      })}
    </div>
  );
}

/* ----------------------------------------------------------------- gauge */

/**
 * Margin against a limit, drawn as a signed bar around a zero line.
 *
 * This is not a progress bar and deliberately does not look like one. The
 * question a controller asks is "how much room is left, or how far over am I",
 * and the sign is the thing they read first.
 */
export function MarginGauge({
  margin,
  limit,
  tone,
  label,
}: {
  margin: number;
  limit: number | null | undefined;
  tone: Tone;
  label: string;
}) {
  const span = limit && limit > 0 ? limit : Math.abs(margin) * 2 || 1;
  const ratio = Math.min(1, Math.abs(margin) / span);
  const width = `${Math.max(2, ratio * 50)}%`;
  const over = margin < 0;
  return (
    <div
      className="flex h-1.5 w-full items-stretch overflow-hidden rounded-full bg-inset"
      role="img"
      aria-label={label}
    >
      <div className="flex w-1/2 justify-end">
        {over ? (
          <span
            className={cx("block h-full rounded-l-full", TONE[tone].fill)}
            style={{ width }}
          />
        ) : null}
      </div>
      <span className="w-px shrink-0 bg-line-strong" aria-hidden />
      <div className="flex w-1/2 justify-start">
        {!over ? (
          <span
            className={cx("block h-full rounded-r-full", TONE[tone].fill)}
            style={{ width }}
          />
        ) : null}
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ misc */

export function Kbd({ children }: { children: ReactNode }) {
  return (
    <kbd className="rounded-xs bg-inset px-1.5 py-px text-2xs text-ink-3">
      {children}
    </kbd>
  );
}

/**
 * The platform's modifier key, as a word somebody can act on.
 *
 * The binding has always accepted both `metaKey` and `ctrlKey`. The hint said
 * "⌘K", which on a Linux or Windows keyboard names a key that is not there, so
 * a shortcut that worked everywhere read as Mac-only to everybody who was not
 * on a Mac.
 *
 * Resolved after mount, because the server has no `navigator` and a guess
 * baked into the HTML would disagree with the client on half of all loads.
 * The initial value is the non-Mac one, which is the majority case and the
 * safer thing to render for a moment.
 */
export function ModifierKey() {
  const [mac, setMac] = useState(false);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- reads navigator, which exists only after mount
    setMac(/Mac|iPhone|iPad/.test(navigator.userAgent));
  }, []);

  return <Kbd>{mac ? "\u2318 K" : "Ctrl K"}</Kbd>;
}

export function IconButton({
  label,
  onClick,
  children,
  active,
  className,
}: {
  label: string;
  onClick?: () => void;
  children: ReactNode;
  active?: boolean;
  className?: string;
}) {
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      aria-pressed={active}
      onClick={onClick}
      className={cx(
        "inline-flex size-9 cursor-pointer items-center justify-center rounded-full",
        active ? "bg-accent-tint text-accent-ink" : "text-ink-3 hover:bg-hover hover:text-ink",
        className,
      )}
    >
      {children}
    </button>
  );
}

export function EmptyState({
  title,
  detail,
  action,
}: {
  title: string;
  detail: string;
  action?: ReactNode;
}) {
  return (
    <div className="flex flex-col items-start gap-2 rounded-md bg-inset px-4 py-6">
      <p className="text-base font-medium text-ink-2">{title}</p>
      <p className="max-w-prose text-base text-ink-3">{detail}</p>
      {action}
    </div>
  );
}

export function Skeleton({ className }: { className?: string }) {
  return <div aria-hidden className={cx("provisional h-3 rounded-xs bg-inset", className)} />;
}

/** Section eyebrow. Used only for column groups and panel sub headings. */
export function Eyebrow({ children }: { children: ReactNode }) {
  return <p className="label-micro">{children}</p>;
}
