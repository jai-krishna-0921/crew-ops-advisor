import { cleanup, render } from "@testing-library/react";
import { afterEach, expect, it } from "vitest";

import { DataTable } from "./data-table";
import type { Table } from "@/lib/contracts";

/**
 * A wide table hung outside the chat column.
 *
 * The figure carried `lg:-mx-14 xl:-mx-24`, a deliberate bleed so a wide table
 * could use the margins. The chat column is not the only thing on screen: the
 * conversations rail is resident and collapsible, and the section rail sits
 * down the right edge, so the space those negative margins reach into is not
 * always there. When it is not, the table is simply wider than the window and
 * the reader loses its right-hand columns off the edge of the page.
 *
 * The inner scroller was already correct. The fix is to let it do its job: the
 * figure stays inside the column and the table scrolls within it, which is the
 * behaviour a reader can actually discover.
 */

afterEach(cleanup);

const TABLE: Table = {
  title: "Cover options",
  columns: ["Rank", "Crew", "Base", "Cost", "Legal", "Coverage", "Reachable"],
  rows: [
    ["1", "C-3310", "BLR", "INR 18,500", "yes", "all 6 flights", "45m"],
    ["2", "C-1526", "BLR", "INR 24,000", "yes", "all 6 flights", "60m"],
  ],
  row_ids: ["C-3310", "C-1526"],
};

it("keeps the table inside the column it is rendered in", () => {
  const { container } = render(<DataTable table={TABLE} />);
  const figure = container.querySelector("figure");

  expect(figure).not.toBeNull();
  expect(figure!.className).not.toMatch(/-mx-/);
});

it("scrolls a wide table inside itself rather than off the page", () => {
  const { container } = render(<DataTable table={TABLE} />);
  const scroller = container.querySelector("figure > div");

  expect(scroller).not.toBeNull();
  expect(scroller!.className).toMatch(/overflow-x-auto/);
});

it("never lets the figure exceed its container", () => {
  const { container } = render(<DataTable table={TABLE} />);
  const figure = container.querySelector("figure");

  expect(figure!.className).toMatch(/max-w-full/);
});

it("still renders every column and row", () => {
  const { container } = render(<DataTable table={TABLE} />);

  expect(container.querySelectorAll("thead th")).toHaveLength(7);
  expect(container.querySelectorAll("tbody tr")).toHaveLength(2);
});
