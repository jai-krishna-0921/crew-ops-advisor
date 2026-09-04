"use client";

/**
 * Paging for the lists that outgrew the screen.
 *
 * The brief on a bad date raises fourteen alerts, a Tier 1 flight query
 * returns a hundred and forty seven rows, and one Tier 3 answer produced
 * fifty nine facts in the evidence panel. All three were rendered in full and
 * all three turned into a scroll with no bottom, which costs the reader the
 * one thing a list is for: knowing how much of it there is.
 *
 * Two decisions worth naming.
 *
 * **A count, not just arrows.** "1 to 8 of 14" is the useful half. Arrows on
 * their own tell a reader they are somewhere in something, which they already
 * knew.
 *
 * **It disappears below the threshold.** Seven rules on one page get no
 * controls at all. Paging chrome around a list that fits is furniture.
 *
 * Nothing here filters, sorts or aggregates. It slices a list the caller
 * already has, which keeps it away from anything the verifier attests.
 */

import { useMemo, useState, type RefObject } from "react";
import { CaretLeftIcon, CaretRightIcon } from "@phosphor-icons/react/dist/ssr";

import { grouped } from "@/lib/format";
import { cx } from "@/components/ui/tone";

export interface Paged<T> {
  /** The current page, one based and already clamped. */
  page: number;
  /** How many pages there are. At least 1, even for an empty list. */
  pages: number;
  /** The items on the current page. */
  slice: T[];
  setPage: (page: number) => void;
  total: number;
  /** One based index of the first item shown, or 0 when there are none. */
  from: number;
  /** One based index of the last item shown. */
  to: number;
}

/**
 * Slice a list into pages.
 *
 * `resetKey` is what the list is *of*: a date, a filter, a table's title.
 * Change it and the reader goes back to page one, because staying on page 4
 * of a list that has just become 2 pages long is how a filter appears to
 * return nothing.
 */
export function usePaged<T>(
  items: readonly T[],
  perPage: number,
  resetKey: string = "",
): Paged<T> {
  // The key is held IN the state rather than watched by an effect. Resetting
  // from an effect would paint one frame of the old page against the new list
  // and then correct it, which is a visible flicker on a list of tall cards,
  // and it is the cascading render React tells you not to write. Comparing
  // during render is the documented way to adjust state when an input changes.
  const [state, setState] = useState({ page: 1, key: resetKey });
  if (state.key !== resetKey) setState({ page: 1, key: resetKey });

  const pages = Math.max(1, Math.ceil(items.length / perPage));

  // Clamped on read, so a list that shrinks under the reader cannot strand
  // them past its end.
  const current = Math.min(Math.max(1, state.page), pages);
  const setPage = (page: number) => setState({ page, key: resetKey });

  const slice = useMemo(
    () => items.slice((current - 1) * perPage, current * perPage),
    [items, current, perPage],
  );

  return {
    page: current,
    pages,
    slice,
    setPage,
    total: items.length,
    from: items.length === 0 ? 0 : (current - 1) * perPage + 1,
    to: Math.min(current * perPage, items.length),
  };
}

/** Sentinel for a gap in the page numbers. */
const GAP = -1;

/**
 * Which page numbers to draw.
 *
 * Always the first and the last, always the current one and its neighbours,
 * and a gap for everything else. The window is fixed width so the control does
 * not resize as the reader moves through it, which is what makes the Next
 * button stay under the cursor.
 */
function pageWindow(page: number, pages: number): number[] {
  if (pages <= 7) return Array.from({ length: pages }, (_, i) => i + 1);

  const near = [page - 1, page, page + 1].filter((n) => n > 1 && n < pages);
  const out: number[] = [1];
  if (near[0] > 2) out.push(GAP);
  out.push(...near);
  if (near[near.length - 1] < pages - 1) out.push(GAP);
  out.push(pages);
  return out;
}

export function Pagination<T>({
  paged,
  label,
  unit,
  scrollTo,
}: {
  paged: Paged<T>;
  /** Names the control for a screen reader: "Brief alerts", "Rulebook". */
  label: string;
  /** What is being counted, singular. "alert", "row", "fact". */
  unit: string;
  /**
   * Brought back into view on a page change. Without it, paging a list of
   * tall cards leaves the reader at the bottom of the previous page looking
   * at the middle of the new one.
   */
  scrollTo?: RefObject<HTMLElement | null>;
}) {
  const { page, pages, from, to, total, setPage } = paged;
  if (pages <= 1) return null;

  const go = (next: number) => {
    setPage(Math.min(Math.max(1, next), pages));
    scrollTo?.current?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  };

  return (
    <nav
      aria-label={label}
      className="flex flex-wrap items-center gap-2 pt-1"
      onKeyDown={(event) => {
        if (event.key === "ArrowLeft") go(page - 1);
        if (event.key === "ArrowRight") go(page + 1);
      }}
    >
      <p className="num text-xs text-ink-3">
        {grouped(from)} to {grouped(to)} of {grouped(total)} {unit}
        {total === 1 ? "" : "s"}
      </p>

      <div className="ml-auto flex items-center gap-0.5 rounded-full bg-inset p-0.5">
        <Step
          label="Previous page"
          disabled={page === 1}
          onClick={() => go(page - 1)}
        >
          <CaretLeftIcon size={12} weight="bold" aria-hidden />
        </Step>

        {pageWindow(page, pages).map((value, index) =>
          value === GAP ? (
            <span
              key={`gap-${index}`}
              aria-hidden
              className="px-1 text-xs text-ink-3"
            >
              &hellip;
            </span>
          ) : (
            <button
              key={value}
              type="button"
              onClick={() => go(value)}
              aria-label={`Page ${value}`}
              aria-current={value === page ? "page" : undefined}
              className={cx(
                "num min-w-6 rounded-full px-2 py-1 text-xs font-medium",
                value === page
                  ? "bg-surface text-ink hairline"
                  : "text-ink-3 hover:text-ink-2",
              )}
            >
              {value}
            </button>
          ),
        )}

        <Step
          label="Next page"
          disabled={page === pages}
          onClick={() => go(page + 1)}
        >
          <CaretRightIcon size={12} weight="bold" aria-hidden />
        </Step>
      </div>
    </nav>
  );
}

function Step({
  label,
  disabled,
  onClick,
  children,
}: {
  label: string;
  disabled: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      aria-label={label}
      disabled={disabled}
      onClick={onClick}
      className="grid size-6 place-items-center rounded-full text-ink-2 hover:bg-surface hover:text-ink disabled:cursor-default disabled:text-ink-3 disabled:opacity-40 disabled:hover:bg-transparent"
    >
      {children}
    </button>
  );
}
