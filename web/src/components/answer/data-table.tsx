"use client";

/**
 * Tier 1 result sets, rendered as a real table.
 *
 * Sorting is a view operation over rows the API supplied. It reorders, it
 * never aggregates, and there is no total row: a figure this component
 * invented would be a figure nobody checked.
 */

import { useMemo, useRef, useState } from "react";
import { CaretDownIcon, CaretUpDownIcon, CaretUpIcon } from "@phosphor-icons/react/dist/ssr";

import type { FactValue, Table } from "@/lib/contracts";
import { plural } from "@/lib/format";
import { Pagination, usePaged } from "@/components/ui/pagination";
import { cx } from "@/components/ui/tone";

type Direction = "asc" | "desc";

/**
 * Rows to a page.
 *
 * "Which flights operate on 2026-09-16" returns 147 of them, and 147 rows
 * inside a chat transcript pushes the next question, the sources and the
 * evidence button so far down that a reader has to scroll past a table they
 * have finished with to continue the conversation. Ten is a screenful.
 */
const ROWS_PER_PAGE = 10;

export function DataTable({ table }: { table: Table }) {
  const [sort, setSort] = useState<{ column: number; direction: Direction } | null>(
    null,
  );

  const rows = useMemo(() => {
    const indexed = table.rows.map((row, index) => ({ row, index }));
    if (!sort) return indexed;
    const { column, direction } = sort;
    const factor = direction === "asc" ? 1 : -1;
    return [...indexed].sort((a, b) => factor * compare(a.row[column], b.row[column]));
  }, [table.rows, sort]);

  // Sorting sends the reader back to page one. Re-sorting in place would keep
  // them on page 5 of a list whose page 5 is now different rows, which reads
  // as the sort having done nothing.
  const top = useRef<HTMLElement>(null);
  const paged = usePaged(
    rows,
    ROWS_PER_PAGE,
    `${table.title}|${sort?.column ?? ""}|${sort?.direction ?? ""}`,
  );

  const toggle = (column: number) => {
    setSort((current) => {
      if (!current || current.column !== column) {
        return { column, direction: "asc" };
      }
      if (current.direction === "asc") return { column, direction: "desc" };
      return null;
    });
  };

  return (
    <figure
      ref={top}
      className="anim-fade-up overflow-hidden rounded-md bg-surface hairline lg:-mx-14 xl:-mx-24"
    >
      <figcaption className="flex flex-wrap items-baseline gap-x-2 px-4 pt-3 pb-1">
        <span className="text-base font-semibold text-ink">{table.title}</span>
        <span className="text-xs text-ink-3">{plural(table.rows.length, "row")}</span>
      </figcaption>

      <div className="overflow-x-auto">
        <table className="w-full border-collapse text-base">
          <thead>
            <tr className="border-b border-line-soft">
              {table.columns.map((column, index) => {
                const active = sort?.column === index;
                const Icon = !active
                  ? CaretUpDownIcon
                  : sort.direction === "asc"
                    ? CaretUpIcon
                    : CaretDownIcon;
                return (
                  <th
                    key={column}
                    scope="col"
                    aria-sort={
                      active
                        ? sort.direction === "asc"
                          ? "ascending"
                          : "descending"
                        : "none"
                    }
                    className="p-0 text-left"
                  >
                    <button
                      type="button"
                      onClick={() => toggle(index)}
                      className="label-micro flex w-full items-center gap-1 px-4 py-2 text-left hover:bg-hover hover:text-ink-2"
                    >
                      {column}
                      <Icon
                        size={10}
                        weight="bold"
                        aria-hidden
                        className={active ? "text-accent" : "text-ink-3 opacity-50"}
                      />
                    </button>
                  </th>
                );
              })}
            </tr>
          </thead>
          <tbody>
            {paged.slice.map(({ row, index }) => (
              <tr
                key={table.row_ids[index] ?? index}
                className="border-b border-line-soft last:border-0 hover:bg-hover"
              >
                {row.map((cell, cellIndex) => (
                  <td
                    key={cellIndex}
                    className={cx(
                      "px-4 py-2 align-top whitespace-nowrap",
                      cellIndex === 0 ? "num text-ink" : "text-ink-2",
                      isNumeric(cell) && "num text-right",
                    )}
                  >
                    {render(cell)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="px-4 pb-2">
        <Pagination
          paged={paged}
          label={`${table.title} rows`}
          unit="row"
          scrollTo={top}
        />
      </div>

      {table.caption ? (
        <p className="px-4 pt-2 pb-3 text-xs text-ink-3">
          {table.caption}
        </p>
      ) : null}
    </figure>
  );
}

function render(value: FactValue): string {
  if (value === null || value === undefined) return "not recorded";
  if (typeof value === "boolean") return value ? "yes" : "no";
  return String(value);
}

function isNumeric(value: FactValue): boolean {
  return typeof value === "number";
}

function compare(a: FactValue, b: FactValue): number {
  if (a === null || a === undefined) return 1;
  if (b === null || b === undefined) return -1;
  if (typeof a === "number" && typeof b === "number") return a - b;
  return String(a).localeCompare(String(b), undefined, { numeric: true });
}
